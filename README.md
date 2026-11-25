# Samba Win7 服务端构建研究

**当前正式路线：** 独立 Cygwin 3.4.10 Setup 离线安装，默认 `C:\Samba`，共享 `/smb`，默认登录名 `root`（映射至受限账户 `smbshare`，不授予系统 root 权限）。统一配置候选见 [deployment/smb.conf](deployment/smb.conf)，账户映射见 [deployment/smbusers](deployment/smbusers)，最新规范见 [管理式部署研究](docs/win7-cygwin-managed-deployment.md#首版正式规范统一配置单账户和安装根2026-11-25)。以下旧便携路线与多账户记录为研究历史，非现行部署说明。尚未完成正式安装包与运行验收。

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

旧 ABI 工作流从 Cygwin Time Machine 下载历史包，在安装前校验固定索引 SHA-256 及各归档 SHA-512，然后在隔离 Runner 目录直接解包构建依赖；此路径不代替 Windows 7 正式安装验收。GnuTLS 和 Parse::Yapp 的额外依赖分别按固定哈希覆盖。现代 Cygwin 对照工作流不变。

## 首版文件共享安全基线与交付条件（2026-11-23）

局域网服务端通过本地账户的用户名和密码认证，使用 `ntlm auth = ntlmv2-only`、`map to guest = Never`、`server signing = mandatory`、`server min protocol = SMB2_10`、`server max protocol = SMB3_11`。`server smb encrypt = if_required` 只允许协商加密而不强制文件传输加密，**认证并不等于文件内容加密**。示例配置在 [`research/cygwin-legacy/sample-smb.conf`](research/cygwin-legacy/sample-smb.conf)，实际账户和 NTFS 路径必须在 Win7 部署时替换。

首版**完整测试 Artifact**必须有 `smbd.exe`、`testparm.exe`、`smbpasswd.exe` 及各 EXE 的递归依赖 DLL、`manifest.json`、`SHA256SUMS` 和使用说明。缺少工具或依赖时打包步骤直接失败。Windows 系统 DLL 不进入包；运行时动态加载模块、Win7 系统 API、双账户 NTFS 隔离和第三方许可证仍需实机及发布前核验。**未通过 Win7 实机验收前不生成正式 GitHub Release。**

2026-11-23 的 Cygwin 3.4.10 构建 [Run 45181375098](https://github.com/Grinch27/samba/actions/runs/45181375098) 在归档校验后卡在 Windows 解包阶段，90 分钟后被取消。下一轮对归档逐项记录及设置超时，避免同类无诊断长时间占用 Runner。Linux 签名的 SMB 2.1、SMB 3.1.1 功能测试已在 [Run 45179337628](https://github.com/Grinch27/samba/actions/runs/45179337628) 通过。

## 首版便携式预发布（2026-11-24）

用户批准：Windows 7 SP1 x64 及以上独立 SMB 服务，不要求与 LanmanServer 同时运行；默认 TCP 445，冲突时报告，不自动停止系统服务。首版优先构建 ZIP，不制作 MSI/EXE 安装器，不安排 Win7 VM 验收。三个工具、递归 DLL、配置模板、隔离 PATH 启动、testparm、SHA256 和对应源码完整后，自动创建唯一 `v4.25.1-cygwin3.4.10-preview1` GitHub Pre-release；既有发布不覆盖，失败草稿不自动删除。Win7 实机与 NTFS 双用户隔离未验证，明确标为实验版本。构建使用只读权限，单独发布 Job 才使用 contents: write。对应源码缺失时禁止上传/发布二进制 ZIP，不以许可证专项审计替代对应源码义务。

上次 Run 45201772287 在 Windows 原生 tar 解包 libpkgconf4-2.1.0-1.tar.zst 失败（146/183）。改用哈希校验后的独立离线安装目录和显式等待 Cygwin Setup，原生 Python 3.14 处理已固定的额外库覆盖；尚待实跑验证。

## P0 安全要求（2026-11-24）

默认配置仅监听并允许 127.0.0.1，`hosts deny = ALL`，共享只读、禁止 Guest 和空密码、账户须显式列入 `valid users`。使用者先配置明确的服务器接口及客户端 IP，交互执行 `smbpasswd` 设置独立账户密码；不在配置、命令行或脚本内保存明文。密码数据库与共享目录须隔离并受 NTFS ACL 保护；不得设置 `force user`、`admin users` 绕过身份隔离。默认 TCP 445，端口冲突应报告，不自动停系统服务。IPv6 需按实际可信地址显式开放并单独验证。

预发布依赖同提交 Linux SMB2.1/3.1.1 功能对照：正确账户密码读写、错误密码拒绝、匿名拒绝、有效账户不在 valid users 时拒绝、真实不同来源 IP 拒绝，以及 Windows testparm 白名单语义检查。Linux 通过和 Windows testparm 通过不是 Windows 服务运行安全证明；实际 Cygwin 的认证、来源限制、NTFS 账户映射仍是目标平台 P0 测试，未验证前不能用于生产或真实私有数据。首版独立进程运行，start.cmd/stop.cmd 后续优先实现，不注册 Windows 服务；包体精简待首版后。

## 便携式账户管理（2026-11-25）

默认仅监听 IPv4/IPv6 回环 `127.0.0.1 ::1`；`hosts allow` 明确列举可信客户端，`hosts deny = ALL` 拒绝其他来源。每共享 `valid users` 独立限制身份，`read only = yes`，`write list` 明确授权写入者。分别为已存在且能被 Cygwin 解析的 Windows 本地用户设置 Samba 独立密码，禁止空密码及匿名；`unix password sync = no`。

将便携包解压到受保护的本地 NTFS 目录。管理员必须先创建 `private` 子目录并审核 NTFS ACL，仅授予实际 Samba 运行/管理身份及必要系统管理员访问权限；整个程序目录及状态目录也应防止非授权修改。不可将这些目录纳入任何共享。`passwd.cmd add user1`、`passwd.cmd change user1`、`passwd.cmd disable user1`、`passwd.cmd enable user1`；密码交互输入，不传参。`start.cmd` 前台启动，同一包根目录和 `smb.conf`，在该控制台 Ctrl+C 停止。不自动改 ACL、防火墙、服务或 Windows 原生密码。独立 stop.cmd 需验证进程身份后再实现。

通过 `%$(SAMBA_PORTABLE_ROOT)` 将 private、state、cache、lock、run、rpc 固定在便携包根下；不得直接运行 EXE 而缺失此环境变量。`smbpasswd -L` 的上游实现要求 UID 0；Windows 管理员不必然等价于 Cygwin UID 0，不绕过安全检查。构建 Job 使用独立临时数据库测试当前 Runner 用户的 Samba 密码初始化，不触及 Windows 账户密码且不打包测试数据库；失败则不发布。Linux 增加实际 IPv6 回环、IPv6 非白名单 testparm、第二账户独立密码和只读测试；仍不等于 Windows 实际访问控制或 Win7 兼容性验收。

## 2026-11-25 后续研究路线

Samba 跟踪官方最新稳定版（https://www.samba.org/samba/download/）；当前仍为 4.25.1。未来在单独版本解析 Job 获取稳定版本及 tag 对应 commit，单次 Run 锁定，Linux/Cygwin 共用；补丁、版本清单、对应源码及 Release 标签全部使用该锁定值。RC/alpha/beta 不参与，升级失败保留上一成功版本。当前发布管线尚未动态化；Cygwin 3.4.10 保持固定。

离线 Setup 使用已校验依赖闭包的显式包名及 verbose solver 日志；若 Python 仍缺失，临时 Runner 从同一固定索引、已校验的 Python 依赖归档补齐未安装包，通过 Cygwin 自身 tar（不覆盖现有文件）及实际 Python 导入测试。该补齐路径不注册为安装器事务，不用于目标机安装。记录 Cygwin UID/GID，不修改账户映射。Linux 增加非白名单 IPv6 实际连接拒绝测试，只在 Runner 回环接口上使用临时 ULA 地址并清理。Windows UID/SID 权限问题仍须独立验证。

## 2026-11-25：动态稳定版及 Win7 部署依赖

每次构建从 Samba 官方 HTTPS 下载目录的 LATEST-IS-SAMBA 标记解析稳定版本，再将 GitHub 上游 tag 解引用为 commit；旧版 Cygwin Job 和 Linux 安全对照共用同一次解析结果，现代 Cygwin 对照独立解析。解析失败、tag 移动或补丁不适用即失败。当前未进行独立 GPG 签名验证。四工具 smbd/testparm/smbpasswd/smbcontrol 同时打包；manifest、ZIP 文件名、预发布标签使用实际版本。不覆盖旧版本；沿用首个合格预发布授权，后续新版本只生成 Artifact，已有预发布时不自动创建另一个 Release。stop.cmd 仍待实例隔离验证。

已从 Run 45398538598 的 Artifact 14924519512 检查 smbd-dlls.txt：现代 Cygwin 3.6.12 的 smbd.exe 递归依赖 16 个非系统 DLL（cygwin1、cygcrypt-2、cyggnutls-30、cyggmp-10、cyghogweed-7、cygnettle-9、cygidn2-0、cygiconv-2、cygintl-8、cygp11-kit-0、cyggcc_s-seh-1、cygffi-8、cygtasn1-6、cygunistring-5、cygpopt-0、cygz）及 KERNEL32/ntdll/KERNELBASE。不是 Win7 的最终清单；目标机不应安装编译器、Python、Perl 或完整开发工具。是否需要额外系统更新、cygserver、账户映射文件或动态模块取决于最终目标平台测试。

Run 45523425534 实际补齐 Python 3.9.16 并通过导入测试，随后错误的 cygcheck -d 命令失败；已改为 -c -d。实际 Runner UID=197108、GID=197121，未证明 UID 0 账户管理可用。Linux 对照发现 private dir 不展开环境变量，已改为明确路径。部署时必须将 smb.conf 所有 @PORTABLE_ROOT@ 替换为实际 /cygdrive/盘符/目录，保持一个配置和受保护的 private 目录；启动和密码管理入口检查 private dir。Windows 构建使用独立临时配置，不将测试数据库或临时路径打入 ZIP。新代码尚待 Actions 实测。

正式部署路线已冻结为独立 Cygwin 3.4.10 Setup 管理式离线 ZIP，Samba 自定义包；旧 DLL ZIP 仅保留研究 Artifact。目标 Win7 不安装 Python（原生或 Cygwin），作为待验证的 P0 依赖边界。Python 仅构建/打包使用。详细见 [管理式部署研究](docs/win7-cygwin-managed-deployment.md)。
