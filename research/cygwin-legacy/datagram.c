/* 待确认的关键需求：Win7 服务端是否需要 RPC 和 SMB Multichannel。
 * 歧义：在较新 Windows 上运行旧 Cygwin 不能覆盖 Win7 的行为。
 * 后续研究：在 Win7 SP1 上重复实验，并验证 NTFS ACL 和用户身份切换。
 * 潜在优化：根据 smbd 的实际运行结果增加对照用例。
 * 风险：消息字节到达时，附带的文件描述符仍可能丢失。
 * 验证重点：父子进程的具名 datagram 传输和 SCM_RIGHTS 两次独立测试。
 */
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

union ancillary_data {
    struct cmsghdr alignment;
    unsigned char bytes[CMSG_SPACE(sizeof(int))];
};

static void send_from_child(struct sockaddr_un *address, bool pass_descriptor)
{
    int sender = socket(AF_UNIX, SOCK_DGRAM, 0);
    char payload = 'D';
    struct iovec data = {&payload, 1};
    struct msghdr message = {
        .msg_name = address,
        .msg_namelen = sizeof(*address),
        .msg_iov = &data,
        .msg_iovlen = 1,
    };
    union ancillary_data control = {0};
    int ends[2];

    if (sender < 0) {
        perror("sender socket");
        _exit(1);
    }
    if (pass_descriptor) {
        if (pipe(ends) < 0 || write(ends[1], "F", 1) != 1) {
            perror("setup test pipe");
            _exit(1);
        }
        close(ends[1]);
        message.msg_control = control.bytes;
        message.msg_controllen = sizeof(control.bytes);
        struct cmsghdr *header = CMSG_FIRSTHDR(&message);
        header->cmsg_level = SOL_SOCKET;
        header->cmsg_type = SCM_RIGHTS;
        header->cmsg_len = CMSG_LEN(sizeof(int));
        memcpy(CMSG_DATA(header), &ends[0], sizeof(int));
    }
    if (sendmsg(sender, &message, MSG_DONTWAIT) != 1) {
        perror("sendmsg");
        _exit(1);
    }
    _exit(0);
}

static int receive_message(int receiver, bool pass_descriptor)
{
    struct pollfd socket_poll = {.fd = receiver, .events = POLLIN};
    int ready = poll(&socket_poll, 1, 5000);
    if (ready <= 0) {
        if (ready < 0) perror("poll");
        else fputs("No datagram received within 5 seconds.\n", stderr);
        return 1;
    }

    char payload = 0;
    struct iovec data = {&payload, 1};
    union ancillary_data control = {0};
    struct msghdr message = {
        .msg_iov = &data,
        .msg_iovlen = 1,
        .msg_control = control.bytes,
        .msg_controllen = sizeof(control.bytes),
    };
    if (recvmsg(receiver, &message, MSG_DONTWAIT) != 1 || payload != 'D') {
        fputs("recvmsg did not return the expected datagram.\n", stderr);
        return 1;
    }
    puts("Named AF_UNIX SOCK_DGRAM across fork: PASS");
    if (!pass_descriptor) return 0;

    const struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    if (header == NULL || header->cmsg_level != SOL_SOCKET ||
        header->cmsg_type != SCM_RIGHTS || header->cmsg_len != CMSG_LEN(sizeof(int))) {
        fputs("SCM_RIGHTS: datagram arrived without a file descriptor.\n", stderr);
        return 3;
    }
    int fd;
    memcpy(&fd, CMSG_DATA(header), sizeof(fd));
    struct pollfd pipe_poll = {.fd = fd, .events = POLLIN};
    bool pipe_ok = poll(&pipe_poll, 1, 1000) == 1 && read(fd, &payload, 1) == 1 && payload == 'F';
    close(fd);
    if (!pipe_ok) {
        fputs("SCM_RIGHTS: received descriptor did not read the test byte.\n", stderr);
        return 1;
    }
    puts("SCM_RIGHTS: PASS (received descriptor read the test byte)");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2 || (strcmp(argv[1], "datagram") != 0 && strcmp(argv[1], "descriptor") != 0)) {
        fputs("Usage: legacy-datagram.exe datagram|descriptor\n", stderr);
        return 2;
    }
    bool pass_descriptor = strcmp(argv[1], "descriptor") == 0;
    struct utsname runtime;
    if (uname(&runtime) != 0 || strncmp(runtime.release, "3.4.10-", 7) != 0) {
        fputs("Expected Cygwin 3.4.10.\n", stderr);
        return 2;
    }
    printf("Cygwin runtime: %s\n", runtime.release);
    fflush(stdout);

    char directory[] = "ipc.XXXXXX";
    if (mkdtemp(directory) == NULL) {
        perror("mkdtemp");
        return 1;
    }
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    snprintf(address.sun_path, sizeof(address.sun_path), "%s/listener", directory);
    int receiver = socket(AF_UNIX, SOCK_DGRAM, 0);
    int result = 1;
    if (receiver < 0 || bind(receiver, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("bind AF_UNIX SOCK_DGRAM");
    } else {
        pid_t child = fork();
        if (child == 0) {
            close(receiver);
            send_from_child(&address, pass_descriptor);
        } else if (child < 0) {
            perror("fork");
        } else {
            result = receive_message(receiver, pass_descriptor);
            int status;
            pid_t ended;
            do {
                ended = waitpid(child, &status, 0);
            } while (ended < 0 && errno == EINTR);
            if (ended != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) result = 1;
        }
    }
    if (receiver >= 0) close(receiver);
    unlink(address.sun_path);
    rmdir(directory);
    return result;
}
