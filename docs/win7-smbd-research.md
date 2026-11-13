# Win7 上的 Samba 独立文件服务器

目标是在 Win7 主机上运行 Samba `smbd.exe`，由 `smb.conf` 定义共享，向其他机器提供本机 NTFS 目录。以 Windows 7 SP1 x64 和 Samba 4.25.1 为研究基线。初版研究普通工作组共享，验收服务启动、认证、签名、权限、并发读写和关闭。Cygwin 是当前移植候选，正式运行时与 x86 支持范围待确定。 [Samba 4.25.1 源码](https://github.com/samba-team/samba/tree/02e8e3f93f4af787bcb3389cbff9e22e74567eb2) · [smbd 手册](https://www.samba.org/samba/docs/current/man-html/smbd.8.html)

## 两条服务端路线

| 目标 | 可用实现 | 适用条件 |
| --- | --- | --- |
| Win7 本机目录通过 SMB 对外共享 | Windows `LanmanServer` 和 NTFS 权限，可通过 `NetShareAdd` 管理共享 | 系统 SMB 最高为 2.1，适合接受 SMB 2.1 和签名的客户端。配置由 Windows 管理 |
| Win7 本机运行独立 Samba 服务 | 移植上游 `smbd.exe` 和依赖，使用 `smb.conf` | 需要 Samba 本身、独立服务、SMB 3.x 或 SMB 加密时验证此路线。当前优先评估 Cygwin x64 |

两条路线最终都需要确认客户端接入端口。直接托管 SMB 使用 TCP 445。实验先在独立测试环境用回环高端口，接着核对本机 445 占用，再验收标准 UNC 路径。用户需要保留 Win7 自带共享时，应事先确定监听地址与端口安排。 [Microsoft SMB 方言表](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-smb2/a64e55aa-1152-48e4-8206-edd96444e7f7) · [NetShareAdd](https://learn.microsoft.com/en-us/windows/win32/api/lmshare/nf-lmshare-netshareadd) · [Windows 直接托管 SMB](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/direct-hosting-of-smb-over-tcpip)

## 本轮证据

| 检查 | 结果 |
| --- | --- |
| 原生 MinGW x64、x86 | 此前 Win7 PE 探针通过静态检查。Samba Waf 通过 `off_t` 检查后停在待执行的 `HAVE_SECURE_MKSTEMP` |
| `smbd` 所需 IPC 和身份语义 | `messaging_dgm` 使用 `AF_UNIX` `SOCK_DGRAM`，每个常规连接使用 `fork()`，会话权限依赖 UID/GID、组列表及身份切换。Windows 原生 `AF_UNIX` 在 Windows 10 引入。Win7 的原生端口需要实现相应的 IPC、进程和 NTFS 安全语义 |
| Cygwin 3.4.10 x64 开发包与运行时 | 从 CVUT HTTPS 镜像获得 `cygwin` 和 `cygwin-devel` 的 `3.4.10-1` 包。两包的大小与 SHA-512 均匹配历史索引。头文件包含 `sys/socket.h`、`sys/acl.h`、`sys/random.h`。`cygwin1.dll` 导出 `fork`、`seteuid`、`setgroups`、`getrandom`、`getxattr`、`mkstemp` 等符号。Win7 上的行为待实测 |
| 历史归档构建依赖 | 归档默认 GCC `11.4.0-1`、Python `3.9.16-1`、GnuTLS `3.6.9-1`，其中 `perl-Parse-Yapp` 缺失。Samba 4.25.1 要求 GnuTLS 至少 `3.6.13`，检测不到 `getrandom` 时要求至少 `3.7.2`。历史归档需补齐加密与构建依赖 |
| 新版 GnuTLS 的静态导入 | 对 Cygwin GnuTLS `3.8.13-1` 及其静态链接导入图中的 11 个 Cygwin DLL 递归检查。`cyggnutls-30.dll` 的 118 个直接导入符号和其余 11 个 DLL 直接导入 `cygwin1.dll` 的符号均可在 3.4.10 导出表找到。DLL 动态加载、系统 API、ABI 及 Win7 实际运行待验证 |
| Windows Server 2022 上的 Cygwin 对照 | Cygwin `3.6.12-1` 通过 `HAVE_SECURE_MKSTEMP`、GnuTLS 和 Waf 配置汇总检查。未修改 Samba 源码的 `smbd` 构建在 `samba-cluster-support` DLL 链接阶段因 `lp_clustering`、`smb_panic` 等符号未解析而失败。Linux 对照构建与 Win7 目标构建分别记录 |
| Linux 本地回环对照 | Samba 4.25.1 `smbd`、`smbclient`、`testparm`、`smbpasswd` 构建完成。`testparm` 接受临时共享配置，`smbd` 启动时在内部 UNIX datagram socket 收到 `EPERM`。最小 Python 探针确认当前环境禁止 `AF_UNIX`，因此共享读写待在允许该 IPC 的环境复测 |

[原生 Win7 探针运行](https://github.com/Grinch27/samba/actions/runs/43182908502) · [Cygwin 配置与链接日志](https://github.com/Grinch27/samba/actions/runs/43332194827) · [Samba 内部 IPC](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/lib/messaging/messages_dgm.c#L1044) · [连接派生进程](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/server.c#L1318) · [会话身份切换](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/uid.c#L453) · [Microsoft AF_UNIX 说明](https://devblogs.microsoft.com/commandline/af_unix-comes-to-windows/) · [Cygwin Windows 身份模拟](https://www.cygwin.com/cygwin-ug-net/ntsec.html) · [Cygwin 安装归档](https://cygwin.com/install.html#unsupported) · [CVUT 镜像](https://ftp.cvut.cz/mirrors/cygwin.com/x86_64/release/cygwin/) · [Samba GnuTLS 版本检测](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/wscript_configure_system_gnutls#L6)

首次遇到的链接目标 `samba-cluster-support` 在 Waf 中允许未定义符号。PE DLL 仍需确定符号来源。本地最小 PE 复现表明导出全部符号无法修复缺失的依赖，合并两个对象后可以链接。下一次先使用 Samba 的 `--nonshared-binary=smbd/smbd` 测试，将 Samba 内部组件链接到服务端主程序，保留外部 DLL 依赖，再依据详细链接命令修正必要的 Waf 依赖。 [Samba 链接目标](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/wscript_build#L356) · [Waf 非共享链接选项](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/buildtools/wafsamba/wscript#L129)

历史索引生成于 2024-01-31 07:12:15 UTC，文件 SHA-256 为 `4bbf34f9922a2360b6bec9a149efad59a5fda5d33de5a28990c7480286dbf46d`。历史 HTTP 索引没有可用的对应签名，包哈希比对属于归档一致性证据。本轮新版包使用签名索引验证，CVUT 镜像 `setup.xz` 的 GPG 签名用 Cygwin 站点发布的公钥验证成功。该索引与 kernel.org 镜像索引 SHA-256 一致，12 个包的大小和 SHA-512 均匹配索引。 [历史索引](http://ctm.crouchingtigerhiddenfruitbat.org/pub/cygwin/circa/64bit/2024/01/30/231215/x86_64/setup.ini) · [Cygwin 安装验证说明](https://cygwin.com/faq.html) · [GnuTLS 软件包](https://www.cygwin.com/cygwin/packages/summary/libgnutls30.html)

## 下一步与验收

1. 固定 Cygwin 3.4.10 x64 构建环境，补齐 `Parse::Yapp`，验证候选 GnuTLS 及其传递依赖的 PE 导入和运行。若新版依赖在旧运行时的加载或基本操作失败，用旧 Cygwin 工具链从源码重建兼容的 GnuTLS/Nettle 依赖集。
2. 编译 `smbd`、`testparm` 和服务端管理工具。用干净的 Win7 SP1 x64 虚拟机记录补丁级别、DLL 依赖、`--version` 和服务启动结果。通过 `testparm` 校验 `smb.conf`，验证回环高端口稳定监听和正常退出。
3. 使用独立客户端验证至少 SMB 2.1 签名和账户认证。若项目要求 SMB 3.1.1 加密，单独验证实际协商方言和加密。覆盖 Unicode 名称、大文件、读写校验、错误密码、跨用户权限拒绝、并发锁及重启后的状态一致性。
4. 核对本机 `LanmanServer` 与 TCP 445 的占用，确定监听方案。之后在隔离局域网用用户预期的客户端验证 `\\主机\共享`。正式产物验收还包括依赖许可证、对应源码和 Win7 运行说明。

| 操作 | 风险 | 批准条件与停止点 |
| --- | --- | --- |
| 在 `Grinch27/samba` 保存研究与运行公开源码构建实验 | LOW | 本任务已指定仓库。完成构建及静态检查后记录实际结果 |
| 在用户 Win7 上修改服务、监听、共享权限或防火墙 | HIGH | 先确认目标测试机和变更范围。实际监听变更留待批准 |
| 发布可安装的 Samba Windows 服务端 | HIGH | 先完成 Win7 双账号和跨机共享验证、依赖审计及发布授权 |
