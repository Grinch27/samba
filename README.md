# Samba Win7 构建研究

以 Samba 4.25.1 为基线，研究在 Windows 7 SP1 上运行 Samba 上游客户端 `smbclient.exe` 和独立文件服务器 `smbd.exe`。构建组织参考 Notepad++，按 x64、x86 分别构建和检查，固定输入版本，记录 PE 结果，再用 Win7 验证运行行为。

## 当前结果

| 验证 | 状态 |
| --- | --- |
| Linux x64 原生对照 | `smbclient`、`smbd` 已构建，两个程序的 `--version` 都输出 `Version 4.25.1` |
| LLVM-MinGW/MSVCRT 生成 x64、x86 Windows 6.1 PE | Winsock 探针通过架构、版本字段和直接 DLL 导入检查 |
| Samba Waf 原生 Windows 交叉配置 | 实测 `_FILE_OFFSET_BITS=64` 后通过 `off_t` 大小检测。后续 `HAVE_SECURE_MKSTEMP` 需要目标系统提供运行结果 |
| Windows 版 `smbclient.exe`、`smbd.exe` | 待编译及 Win7 SP1 验证 |

需要上游 Samba 客户端时，先在 Cygwin 3.4.10 x64 环境研究 `smbclient` 的可构建性。需要 Win7 本机提供共享时，先确认是否必须使用 `smbd` 和 `smb.conf`，这决定是否需要移植 Samba 的文件服务器语义。

- [技术研究、复现步骤和验收标准](docs/win7-build-research.md)
- [Win7 x64、x86 交叉配置探针](research/probe-win7.sh)
- [GitHub Actions 验证记录和探针产物](https://github.com/Grinch27/samba/actions/runs/43182908502)
