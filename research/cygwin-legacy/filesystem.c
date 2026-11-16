/* 待确认的关键需求：Win7 上的 NTFS 重命名和允许覆盖行为。
 * 歧义：旧 Cygwin 在 Windows Server 2022 上的行为需在 Win7 复测。
 * 后续研究：从 SMB 客户端验证目标已存在、并发操作及打开文件的重命名。
 * 潜在优化：按共享目录实际使用的文件系统补充测试。
 * 风险：重命名错误导致覆盖已有文件。
 * 验证重点：目录描述符、RENAME_NOREPLACE、EEXIST 和文件内容。
 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/utsname.h>
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

    bool passed = test_rename(directory);
    unlinkat(directory, "source", 0);
    unlinkat(directory, "moved", 0);
    unlinkat(directory, "target", 0);
    close(directory);
    if (rmdir(workdir) != 0) {
        perror("rmdir test directory");
        return 1;
    }
    return passed ? 0 : 1;
}
