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
| Samba 内置库静态合并 | `--nonshared-binary=smbd/smbd` 越过 `samba-cluster-support` 链接失败。延长时限后，构建在 `sysquotas_4A.c` 遇到 Cygwin `struct dqblk` 缺少 `dqb_curblocks`。使用 `--without-quotas` 后，构建进入第 2359/2374 项 `vfs_default` |
| 默认 VFS 编译 | Cygwin 的 `renameat2()` 已检测到，`RENAME_NOREPLACE` 的定义来自 `<cygwin/fs.h>`。`copy_file_range()` 不可用时，Samba 的回退函数用 `loff_t *`，和调用方的 `off_t *` 在 Cygwin 3.6.12 上类型不同。这两处使构建退出码为 1 |
| Windows Server 2022 服务端链接 | 应用默认 VFS 补丁后，Cygwin 3.6.12 对照完成 2374 项构建和链接。`smbd.exe --version` 退出码为 0，输出 `Version 4.25.1`。作业产物保存构建诊断和 DLL 依赖清单。 [成功运行](https://github.com/Grinch27/samba/actions/runs/43793004726) |
| Cygwin 3.4.10 运行时对照 | 在 Windows Server 2022 运行使用 3.4.10 SDK 与启动对象构建的 PE。GnuTLS 3.8.13、HMAC-SHA256 和 AES-128-GCM 已知答案通过。跨 `fork()` 的具名 `AF_UNIX` datagram 收发通过。`SCM_RIGHTS` 的报文到达时缺少文件描述符，探针退出码为 3 |
| Linux 文件共享对照 | 同一 Samba 4.25.1 在 Ubuntu 24.04 Runner 完成构建及功能测试。回环共享强制 SMB 2.1 签名，关闭 RPC 按需辅助进程及 Multichannel。直连共享、上传与下载 1 MiB 中文名文件、字节比对、重命名、删除和错误密码拒绝均通过 |

[原生 Win7 探针运行](https://github.com/Grinch27/samba/actions/runs/43182908502) · [Cygwin 配置与链接日志](https://github.com/Grinch27/samba/actions/runs/43332194827) · [Samba 内部 IPC](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/lib/messaging/messages_dgm.c#L1044) · [连接派生进程](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/server.c#L1318) · [会话身份切换](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/uid.c#L453) · [Microsoft AF_UNIX 说明](https://devblogs.microsoft.com/commandline/af_unix-comes-to-windows/) · [Cygwin Windows 身份模拟](https://www.cygwin.com/cygwin-ug-net/ntsec.html) · [Cygwin 安装归档](https://cygwin.com/install.html#unsupported) · [CVUT 镜像](https://ftp.cvut.cz/mirrors/cygwin.com/x86_64/release/cygwin/) · [Samba GnuTLS 版本检测](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/wscript_configure_system_gnutls#L6)

首次遇到的链接目标 `samba-cluster-support` 在 Waf 中允许未定义符号。PE DLL 仍需确定符号来源。本地最小 PE 复现表明导出全部符号无法修复缺失的依赖，合并两个对象后可以链接。`--nonshared-binary=smbd/smbd` 将 Samba 内部组件链接到服务端主程序，外部 DLL 仍由运行时加载。 [Samba 链接目标](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/wscript_build#L356) · [Waf 非共享链接选项](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/buildtools/wafsamba/wscript#L129) · [延长时限后的配额编译失败](https://github.com/Grinch27/samba/actions/runs/43732065983)

[默认 VFS 补丁](../research/cygwin-vfs-compat.patch) 从 Cygwin 头文件取无覆盖重命名标志，并让 Samba 文件复制回退的声明与实现使用 Waf 已验证为至少 64 位的 `off_t`。当前 Cygwin 的复制回退仍返回 `ENOSYS`，由 VFS 接续现有文件复制路径。 [VFS 构建失败日志](https://github.com/Grinch27/samba/actions/runs/43771336521) · [Waf 大文件要求](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/buildtools/wafsamba/wscript#L640)

应用补丁后，Waf 配置成功。慢速 Runner 的构建在第 2242/2374 项触发 32 分钟时限，退出码为 124，尚未到达 VFS 任务。按截断前每项约 3 至 4 秒估算，还需约 7 至 9 分钟。重试将构建限时设为 52 分钟，整个作业限时设为 65 分钟，为配置、链接和诊断留出时间。 [带 VFS 补丁的限时运行](https://github.com/Grinch27/samba/actions/runs/43774502049)

历史索引生成于 2024-01-31 07:12:15 UTC，文件 SHA-256 为 `4bbf34f9922a2360b6bec9a149efad59a5fda5d33de5a28990c7480286dbf46d`。历史 HTTP 索引没有可用的对应签名，包哈希比对属于归档一致性证据。本轮新版包使用签名索引验证，CVUT 镜像 `setup.xz` 的 GPG 签名用 Cygwin 站点发布的公钥验证成功。该索引与 kernel.org 镜像索引 SHA-256 一致，12 个包的大小和 SHA-512 均匹配索引。 [历史索引](http://ctm.crouchingtigerhiddenfruitbat.org/pub/cygwin/circa/64bit/2024/01/30/231215/x86_64/setup.ini) · [Cygwin 安装验证说明](https://cygwin.com/faq.html) · [GnuTLS 软件包](https://www.cygwin.com/cygwin/packages/summary/libgnutls30.html)

历史索引缺失的 `Parse::Yapp::Driver` 可以从 `Parse-Yapp 1.21` 源码的 `lib/` 加入 `PERL5LIB`。CPAN 原始归档 SHA-256 为 `3810e998308fba2e0f4f26043035032b027ce51ce5c8a52a8b8e340ca65f13e5`，与签名索引对应的 Cygwin 源包中嵌入的原始归档逐字节一致。Linux Perl 5.40.1 的三组测试共 33 项通过，仍需在 Cygwin 的 Perl 5.36.3 下执行 Waf 的 PIDL 检测。 [Parse-Yapp 1.21](https://metacpan.org/release/WBRASWELL/Parse-Yapp-1.21) · [Samba 的 PIDL 检测](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/pidl/wscript#L23)

### `SCM_RIGHTS` 对服务端的影响

旧版 Cygwin 源码的 `fhandler_socket_local::sendmsg()` 对 `AF_LOCAL` 把辅助数据长度设为 0。Samba 的 `samba-dcerpcd` 用该机制把客户端套接字传给 RPC 工作进程。工作进程要求消息携带一个描述符，资源管理器浏览 `\\主机` 时所需的 `srvsvc` 共享枚举因此有明确的移植依赖。`smbd` 的 SMB3 Multichannel 也有独立的连接套接字移交路径。 [Cygwin 3.4.10 源包索引](https://ftp.cvut.cz/mirrors/cygwin.com/x86_64/release/cygwin/) · [Cygwin 的描述符传递限制](https://www.cygwin.com/cygwin-ug-net/highlights.html#ov-hi-sockets) · [Samba RPC 套接字移交](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/rpc_server/rpc_host.c#L1630) · [RPC 工作进程接收](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/rpc_server/rpc_worker_internal.c#L360) · [SMB 连接移交](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/smbXsrv_client.c#L340)

使用 [锁定的归档和测试源码](../research/cygwin-legacy/) 可以重建运行时探针。更新后的工作流记录描述符缺失的退出码 3，同时将加密、普通报文和程序执行错误单列。Linux 回环对照验证了关闭按需 RPC 后直连 `\\主机\共享` 可以进行身份认证及文件操作。下一轮分别检查 Win7 的直连共享和 `\\主机` 的共享列表。 [Cygwin 3.4.10 运行结果](https://github.com/Grinch27/samba/actions/runs/43771683491) · [Linux 签名读写运行结果](https://github.com/Grinch27/samba/actions/runs/43772456895) · [Linux 回环脚本](../research/probe-smbd-fileshare.sh)

### 服务身份与文件权限

Cygwin 默认将 `LocalSystem` 映射为 UID 18。Samba 的 `non_root_mode()` 用初始 UID 是否为 0 判断是否以特权方式运行，`gain_root()` 据此决定是否恢复特权身份。Win7 原型需要核对启动令牌、特权恢复和会话令牌切换，并用两个本地账号验证 NTFS 允许及拒绝结果。 [Cygwin SID 映射](https://www.cygwin.com/cygwin-ug-net/ntsec.html) · [Samba 的特权模式判断](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/lib/util_sec.c#L127) · [Samba 会话特权切换](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/sec_ctx.c#L100)

## 共享配置兼容性

以默认模板和实际运行配置为两个验收输入。每份配置通过 `testparm` 后都要验证服务启动和共享操作。Win7 部署需要将配置中的 POSIX 路径映射到本机 NTFS 目录，并为 Samba 状态、缓存、锁和日志准备目录。两份配置存在同名共享时，分别验证各自的身份策略。 [testparm 手册](https://www.samba.org/samba/docs/current/man-html/testparm.1.html)

| 配置功能 | 验收条件 |
| --- | --- |
| 认证、访问限制和强制身份 | 保留 `hosts allow`、`valid users`、`write list` 和访客策略。验证允许与拒绝场景。确认 `force user`、`force group` 解析到预期的账户和组，并检查新文件的 Windows 所有者、ACL 和实际读写权限 |
| 文件操作 | 验证 `create mask`、`directory mask`、强制模式和 `veto files`。用两个客户端核对并发访问、重命名、锁和大文件内容 |
| 扩展属性和备用数据流 | 构建时显式纳入 `vfs_streams_xattr`。从 SMB 客户端写入、列出和读回备用数据流，核对 DOS 属性，以及重命名和重启后的数据 |
| TCP 445 和共享展示 | 先验证通过已知 UNC 路径直连，再用资源管理器验证 `browseable` 共享枚举。枚举依赖 `srvsvc` 和 RPC 套接字移交 |
| 模板的家目录与打印 | 验证启用的 `[homes]` 只暴露预期的目录。启用 `[printers]` 时验证队列、spool 路径和打印 RPC |

Windows Server 2022 上的 NTFS 实验使用 Cygwin 3.4.10。`user.DOSATTRIB` 和 `user.DosStream.probe` 的二进制值读回一致，`user.DosStream.probe:$DATA` 写入返回 `EINVAL`。Samba 的 `streams_xattr` 默认添加 `:$DATA`，而 Cygwin 传给 NTFS 的扩展属性名保留该冒号。 [NTFS 实验](https://github.com/Grinch27/samba/actions/runs/44450541438) · [Samba 模块文档](https://www.samba.org/samba/docs/current/man-html/vfs_streams_xattr.8.html) · [Microsoft EA 命名要求](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fscc/0eb94f48-6aac-41df-a878-79f4dcfd8989)

`streams_xattr xattr_tdb` 是可验证的 Windows 存储候选。上游自测使用这组模块，`xattr_tdb` 将扩展属性名和值保存到独立的 TDB。验收需要覆盖数据库权限、备份、重启和文件重命名。若要求 Win7 本机应用直接看到原生 NTFS 备用数据流，则需要另行验证原生 ADS 后端。 [Samba 4.25.1 自测配置](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/selftest/target/Samba3.pm#L3698) · [vfs_xattr_tdb 手册](https://www.samba.org/samba/docs/current/man-html/vfs_xattr_tdb.8.html)

## 下一步与验收

1. 固定 Cygwin 3.4.10 x64 构建环境并补齐 `Parse::Yapp`。将 `smbd`、配置检查、账户管理工具和所需 VFS 模块纳入构建。首轮原型验证普通工作组文件共享。
2. 在干净的 Win7 SP1 x64 虚拟机复测加密与 IPC 探针，记录补丁和 DLL 依赖。依次验收 `smbd --version`、`testparm` 校验 `smb.conf`、回环高端口监听和正常退出。
3. 使用独立客户端验证至少 SMB 2.1 签名和账户认证。若项目要求 SMB 3.1.1 加密，单独验证实际协商方言和加密。覆盖 Unicode 名称、大文件、读写校验、错误密码、跨用户权限拒绝、并发锁及重启后的状态一致性。
4. 核对本机 `LanmanServer` 与 TCP 445 的占用，确定监听方案。之后在隔离局域网用用户预期的客户端验证 `\\主机\共享`。正式产物验收还包括依赖许可证、对应源码和 Win7 运行说明。

| 操作 | 风险 | 批准条件与停止点 |
| --- | --- | --- |
| 在 `Grinch27/samba` 保存研究与运行公开源码构建实验 | LOW | 本任务已指定仓库。完成构建及静态检查后记录实际结果 |
| 在用户 Win7 上修改服务、监听、共享权限或防火墙 | HIGH | 先确认目标测试机和变更范围。实际监听变更留待批准 |
| 发布可安装的 Samba Windows 服务端 | HIGH | 先完成 Win7 双账号和跨机共享验证、依赖审计及发布授权 |

## 已确定的首版认证与交付门禁（2026-11-23）

- 首版 LAN 共享采用 Samba 本地用户名、密码认证（NTLMv2），禁用匿名访问，强制 SMB 签名；SMB 版本从 2.1 起，最高目标 3.1.1。
- 不要求 SMB 文件内容加密。采用 `server smb encrypt = if_required`，客户端仍可协商加密；不得将 NTLMv2 认证等同于传输加密。
- 必须同时具备 `smbd.exe`、`testparm.exe`、`smbpasswd.exe`、递归 DLL 依赖和文件哈希清单，缺任意一项不得标记为完整包。
- `cygcheck` 递归依赖扫描不保证检测按需加载的 DLL/VFS 模块；Win7 SP1 加载、用户权限和 NTFS 隔离未验收前只能上传实验 Artifact，不得创建正式 Release。
- GitHub Actions Windows 历史 Cygwin 压缩包直接解包在 Run `45181375098` 超过 90 分钟仍未完成，后续先定位单包/解包工具阻塞并设置明确超时。

## 2026-11-24 便携式预发布授权

不要求 LanmanServer 共存；不自动停服务，不变更用户实机。首版 ZIP 便携包优先，Win7 VM 和双用户 NTFS 实机验收延后。完整三工具、DLL、配置、启动检查及精确对应源码通过后，自动创建 GitHub Pre-release，不再重复批准。专项许可证审计延后但对应源码和许可材料不能省略。发布 Job 单独权限，固定 preview1 标签，不覆盖已发布版本；失败草稿保留供后续诊断。
