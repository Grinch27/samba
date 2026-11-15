# Samba Win7 服务端构建研究

目标是在 Windows 7 上运行 Samba 独立文件服务器 `smbd.exe`，将 Win7 本机目录共享给局域网客户端。以 Samba 4.25.1 和 Win7 SP1 x64 为首轮研究基线，借鉴 Notepad++ 固定构建输入、检查 Windows 产物并单独验证运行的做法。

## 当前结果

| 验证 | 状态 |
| --- | --- |
| Linux x64 原生对照 | `smbclient`、`smbd` 已构建，两个程序的 `--version` 都输出 `Version 4.25.1` |
| LLVM-MinGW/MSVCRT 生成 x64、x86 Windows 6.1 PE | Winsock 探针通过架构、版本字段和直接 DLL 导入检查 |
| Samba Waf 原生 Windows 交叉配置 | 实测 `_FILE_OFFSET_BITS=64` 后通过 `off_t` 大小检测。后续 `HAVE_SECURE_MKSTEMP` 需要目标系统提供运行结果 |
| Cygwin 3.4.10 运行时对照 | Windows Server 2022 上，GnuTLS 3.8.13 的 HMAC-SHA256 和 AES-128-GCM 通过。普通进程间 datagram 可收发，`SCM_RIGHTS` 丢失文件描述符 |
| Win7 独立 `smbd.exe` | 当前在 Cygwin 上验证服务端构建，Win7 SP1 启动和共享验收待完成 |

客户端工具 `smbclient` 用于测试服务端的协议协商、认证及共享读写。服务端的验收重点是多会话身份切换、NTFS 权限隔离及监听和停止行为。

- [Win7 独立服务端研究与验收条件](docs/win7-smbd-research.md)
- [通用 Windows 构建研究与 Linux 对照](docs/win7-build-research.md)
- [Win7 x64、x86 交叉配置探针](research/probe-win7.sh)
- [Cygwin 服务端构建实验](https://github.com/Grinch27/samba/actions/workflows/win7-smbd-research.yml)
- [Cygwin 3.4.10 运行时实验](https://github.com/Grinch27/samba/actions/workflows/win7-cygwin-legacy-probe.yml)
