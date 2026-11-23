# Samba Win7 服务端构建研究

目标是在 Windows 7 上运行 Samba 独立文件服务器 `smbd.exe`，将 Win7 本机目录共享给局域网客户端。以 Samba 4.25.1 和 Win7 SP1 x64 为首轮研究基线，借鉴 Notepad++ 固定构建输入、检查 Windows 产物并单独验证运行的做法。

## 当前结果

| 验证 | 状态 |
| --- | --- |
| Linux x64 文件共享对照 | Samba 4.25.1 通过强制 SMB 2.1 签名的直接共享访问、中文文件名读写和错误密码拒绝 |
| LLVM-MinGW/MSVCRT 生成 x64、x86 Windows 6.1 PE | Winsock 探针通过架构、版本字段和直接 DLL 导入检查 |
| Samba Waf 原生 Windows 交叉配置 | 实测 `_FILE_OFFSET_BITS=64` 后通过 `off_t` 大小检测。后续 `HAVE_SECURE_MKSTEMP` 需要目标系统提供运行结果 |
| Windows Server 2022 `smbd.exe` 构建 | Cygwin 3.6.12 上完成链接，`smbd.exe --version` 输出 `Version 4.25.1` |
| Cygwin 3.4.10 运行时对照 | Windows Server 2022 上通过加密、重命名和普通扩展属性探针。NTFS 拒绝带有 `:$DATA` 后缀的扩展属性名，`SCM_RIGHTS` 报文缺少文件描述符 |
| Win7 独立 `smbd.exe` | 新增 Cygwin 3.4.10 完整构建入口，编译与 Win7 运行仍待实测 |

客户端工具 `smbclient` 用于测试服务端的协议协商、认证及共享读写。服务端的验收重点是多会话身份切换、NTFS 权限隔离及监听和停止行为。

- [Win7 独立服务端研究与验收条件](docs/win7-smbd-research.md)
- [共享配置兼容性](docs/win7-smbd-research.md#共享配置兼容性)
- [通用 Windows 构建研究与 Linux 对照](docs/win7-build-research.md)
- [Win7 x64、x86 交叉配置探针](research/probe-win7.sh)
- [Cygwin 服务端构建实验](https://github.com/Grinch27/samba/actions/workflows/win7-smbd-research.yml)
- [Cygwin 3.4.10 完整服务端构建](https://github.com/Grinch27/samba/actions/workflows/win7-cygwin-legacy-smbd.yml)
- [Cygwin 3.4.10 运行时实验](https://github.com/Grinch27/samba/actions/workflows/win7-cygwin-legacy-probe.yml)
- [Linux 签名文件共享对照](https://github.com/Grinch27/samba/actions/runs/43772456895)

## SMB 2+ 兼容性目标

首版服务端协议最低 SMB2_10（SMB 2.1）、最高尝试 SMB3_11（SMB 3.1.1），强制签名。Linux 对照分别固定 SMB 2.1 和 3.1.1，覆盖认证、中文名读写及密码拒绝。Win7 原生客户端最高仍为 SMB 2.1，较新的客户端才可协商更高版本。Cygwin 3.4.10 旧 ABI 和 Win7 运行还需实际测试。

旧 ABI 工作流从 Cygwin Time Machine 下载历史包，在安装前校验固定索引 SHA-256 及各归档 SHA-512，然后离线安装；GnuTLS 和 Parse::Yapp 的额外依赖分别按固定哈希覆盖。现代 Cygwin 对照工作流不变。
