/* 待确认的关键需求：Win7 上的 NTFS 重命名、DOS 属性和备用数据流。
 * 歧义：旧 Cygwin 在 Windows Server 2022 上的行为需在 Win7 复测。
 * 后续研究：从 SMB 客户端验证目标已存在、并发操作及打开文件的重命名。
 * 潜在优化：按共享目录实际使用的文件系统补充测试。
 * 风险：重命名错误导致覆盖已有文件。
 * 验证重点：RENAME_NOREPLACE 和 Samba 使用的扩展属性名。
 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/utsname.h>
#include <sys/xattr.h>
#include <unistd.h>

#include <cygwin/fs.h>

static bool create_file(int directory, const char *name, char value)
{
    int file = openat(directory, name, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (file < 0) {
        perror(name);
        return false;
    }

    bool written = write(file, &value, sizeof(value)) == sizeof(value);
    if (close(file) != 0 || !written) {
        fprintf(stderr, "Could not write test file %s.\n", name);
        return false;
    }
    return true;
}

static bool has_byte(int directory, const char *name, char expected)
{
    int file = openat(directory, name, O_RDONLY);
    if (file < 0) {
        perror(name);
        return false;
    }

    char bytes[2];
    ssize_t size = read(file, bytes, sizeof(bytes));
    close(file);
    return size == 1 && bytes[0] == expected;
}

static bool test_rename(int directory)
{
    if (!create_file(directory, "source", 'S') ||
        !create_file(directory, "target", 'T')) {
        return false;
    }

    if (renameat2(directory, "source", directory, "target", RENAME_NOREPLACE) != -1 ||
        errno != EEXIST || !has_byte(directory, "source", 'S') ||
        !has_byte(directory, "target", 'T')) {
        fputs("RENAME_NOREPLACE should reject and preserve both files.\n", stderr);
        return false;
    }
    puts("RENAME_NOREPLACE with existing target preserves both files: PASS");

    if (renameat2(directory, "source", directory, "moved", RENAME_NOREPLACE) != 0 ||
        !has_byte(directory, "moved", 'S') ||
        faccessat(directory, "source", F_OK, 0) != -1 || errno != ENOENT) {
        fputs("RENAME_NOREPLACE should move a file to an unused name.\n", stderr);
        return false;
    }
    puts("RENAME_NOREPLACE with unused target moves the file: PASS");

    if (renameat2(directory, "moved", directory, "target", 0) != 0 ||
        !has_byte(directory, "target", 'S')) {
        fputs("renameat2 with flags=0 should replace the target.\n", stderr);
        return false;
    }
    puts("renameat2 with flags=0 replaces an existing target: PASS");
    return true;
}

static bool probe_xattr(int file, const char *name, bool allow_rejection)
{
    const unsigned char payload[] = {0x53, 0x00, 0x4d, 0x42};
    unsigned char actual[sizeof(payload)];

    if (fsetxattr(file, name, payload, sizeof(payload), XATTR_CREATE) != 0) {
        int error = errno;
        fprintf(allow_rejection ? stdout : stderr,
                "EA %s write rejected: errno=%d (%s)\n",
                name, error, strerror(error));
        return allow_rejection;
    }

    ssize_t size = fgetxattr(file, name, actual, sizeof(actual));
    if (size != (ssize_t)sizeof(payload) ||
        memcmp(actual, payload, sizeof(payload)) != 0) {
        fprintf(stderr, "EA %s readback did not match.\n", name);
        return false;
    }
    printf("EA %s binary round-trip: PASS\n", name);
    return true;
}

static bool test_xattrs(int directory)
{
    int file = openat(directory, "metadata", O_RDWR | O_CREAT | O_EXCL, 0600);
    if (file < 0) {
        perror("open metadata test file");
        return false;
    }

    bool dos = probe_xattr(file, "user.DOSATTRIB", false);
    bool stream = probe_xattr(file, "user.DosStream.probe", false);
    bool stream_type = probe_xattr(file, "user.DosStream.probe:$DATA", true);
    if (close(file) != 0) {
        perror("close metadata test file");
        return false;
    }
    return dos && stream && stream_type;
}

int main(void)
{
    struct utsname runtime;
    if (uname(&runtime) != 0 || strncmp(runtime.release, "3.4.10-", 7) != 0) {
        fputs("Expected Cygwin 3.4.10.\n", stderr);
        return 2;
    }
    printf("Cygwin runtime: %s\n", runtime.release);

    char workdir[] = "rename.XXXXXX";
    if (mkdtemp(workdir) == NULL) {
        perror("mkdtemp");
        return 1;
    }
    int directory = open(workdir, O_RDONLY | O_DIRECTORY);
    if (directory < 0) {
        perror("open test directory");
        rmdir(workdir);
        return 1;
    }

    bool rename_passed = test_rename(directory);
    bool xattrs_passed = test_xattrs(directory);
    unlinkat(directory, "source", 0);
    unlinkat(directory, "moved", 0);
    unlinkat(directory, "target", 0);
    unlinkat(directory, "metadata", 0);
    close(directory);
    if (rmdir(workdir) != 0) {
        perror("rmdir test directory");
        return 1;
    }
    return rename_passed && xattrs_passed ? 0 : 1;
}
