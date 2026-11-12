# Samba 4.25.1 的 Windows 7 构建可行性

研究日期为 2026-11-12。以 Windows 7 SP1 为候选运行基线，首选 x64，x86 进入独立验证。当前上游基线为 Samba 4.25.1 的提交 `02e8e3f93f4af787bcb3389cbff9e22e74567eb2`，参考构建实现为 Notepad++ 的提交 `066c93ac06e2f8d59c5e5f442e60d8306b603163`。 [Samba 发布说明](https://www.samba.org/samba/history/samba-4.25.1.html) · [Samba 源码](https://github.com/samba-team/samba/tree/02e8e3f93f4af787bcb3389cbff9e22e74567eb2) · [Notepad++ 源码](https://github.com/notepad-plus-plus/notepad-plus-plus/tree/066c93ac06e2f8d59c5e5f442e60d8306b603163)

## 从 Notepad++ 复用的做法

| 上游做法 | 在本项目中的应用 |
| --- | --- |
| `CI_build.yml` 在新 Windows Runner 上按架构与配置调用 MSBuild，并有 CMake 和 MSYS2 构建分支 | 将编译宿主与 Win7 运行环境独立处理。先用固定版本的 Linux 交叉工具链测 x64、x86，再用 Win7 SP1 客户机验证运行 |
| GCC 构建显式指定 Win7 的 `_WIN32_WINNT`、`NTDDI_VERSION`，项目清单声明 Windows 7 | 探针显式设定 `_WIN32_WINNT=0x0601`、`WINVER=0x0601` 和 PE 6.1 字段。真实应用还需核验全部 DLL、API 及实际启动 |
| 按架构保存构建产物，支持表分别记录可运行性与上游维护状态 | 每个架构单独保留 PE 审计和 Waf 结果。将编译通过、Win7 启动通过、SMB 功能通过记录为独立结果 |

[CI 工作流](https://github.com/notepad-plus-plus/notepad-plus-plus/blob/066c93ac06e2f8d59c5e5f442e60d8306b603163/.github/workflows/CI_build.yml) · [GCC Makefile](https://github.com/notepad-plus-plus/notepad-plus-plus/blob/066c93ac06e2f8d59c5e5f442e60d8306b603163/PowerEditor/gcc/makefile) · [应用清单](https://github.com/notepad-plus-plus/notepad-plus-plus/blob/066c93ac06e2f8d59c5e5f442e60d8306b603163/PowerEditor/src/notepad%2B%2B.exe.manifest) · [支持表](https://github.com/notepad-plus-plus/notepad-plus-plus/blob/066c93ac06e2f8d59c5e5f442e60d8306b603163/SUPPORTED_SYSTEM.md)

## 源码和构建证据

| 检查 | 观察 |
| --- | --- |
| Linux 原生对照 | 在 Debian 13 x64 上完成同一 Samba 提交的原生配置和构建。`smbclient` 和 `smbd` 均为 x86-64 ELF，两条 `--version` 命令均以退出码 0 输出 `Version 4.25.1` |
| Win7 工具链探针 | LLVM-MinGW `20261104` 的 MSVCRT 版本在 Debian 13 x64 构建了两个 Windows 控制台 PE。机器类型为 `0x8664`、`0x14C`，OS 和子系统版本字段均为 6.1。直接导入 `KERNEL32.dll`、`msvcrt.dll` 和 `WS2_32.dll`。执行体仅初始化并清理 Winsock |
| 大文件偏移 | 两个 MinGW 目标的 `off_t` 默认 4 字节，`-D_FILE_OFFSET_BITS=64` 时为 8 字节，仅设置 `-D_LARGE_FILES` 时为 4 字节。Linux x64 对照为 8 字节 |
| Waf 交叉配置 | 首次 x64 配置缺少运行时回答，停在大文件检测。填入编译时实测的回答后，x64 和 x86 均通过该项，继续到 `HAVE_SECURE_MKSTEMP`。测试程序已链接，回答为 `UNKNOWN`，配置退出码为 1。该项创建两个临时文件并调用 `unlink`，校验文件名唯一性和 `0600` 模式 |
| 原生 Windows 的 POSIX 差异 | x64 配置查不到 `sys/utsname.h`、`sys/socket.h`、`sys/mman.h`、`sys/wait.h`。另查到 `lib/replace/wscript` 使用构建宿主的 `sys.platform` 设置 `LINUX`。需要逐项核查跨编译目标判断和 Windows 等价实现 |
| 服务器实现 | `source3/smbd/server.c` 的连接处理使用 `fork()` 并在子进程重建状态。`source3/smbd/uid.c` 实现按会话切换身份。服务器移植还涉及凭据、文件共享与锁、ACL、扩展属性、进程和套接字行为 |
| 目标依赖 | Samba 4.25.1 的顶层配置检查 GnuTLS 和 zlib。当前 MinGW 实验隔离了 Linux 的 `pkg-config` 搜索路径，后续需显式提供目标平台的依赖并验证其 Win7 DLL 导入 |

[LLVM-MinGW 工具链与 CRT 说明](https://github.com/mstorsjo/llvm-mingw) · [固定工具链发布](https://github.com/mstorsjo/llvm-mingw/releases/tag/20261104) · [Waf 大文件检测](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/buildtools/wafsamba/samba_conftests.py#L87) · [POSIX 兼容检测](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/lib/replace/wscript#L843) · [服务端连接处理](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/server.c#L1318) · [会话身份切换](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/source3/smbd/uid.c#L453) · [GnuTLS 检查](https://github.com/samba-team/samba/blob/02e8e3f93f4af787bcb3389cbff9e22e74567eb2/wscript_configure_system_gnutls)

## 实现路线

| 需求 | 路线 | 主要边界 |
| --- | --- | --- |
| 在 Win7 上运行上游 `smbclient` 命令 | 首先复现 x64 Cygwin 路线。Win7 x64 的最后一代 Cygwin DLL 为 3.4.10，x86 的最终版本为 3.3.6。固定兼容的编译器、Python、Perl、GnuTLS、zlib 和 DLL 依赖 | 需要 `cygwin1.dll`，且 Samba 4.25.1 在这些环境上的构建和 Win7 运行待验证 |
| 在 Win7 上运行原生上游 `smbclient.exe` | 以 LLVM-MinGW/MSVCRT 开展 libreplace、Winsock、临时文件及目标依赖移植，先缩小到客户端目标 `client/smbclient` | 先解决 Waf 目标运行探测、ABI 和依赖，然后做完整的连接、认证和文件操作测试 |
| 在 Win7 上运行独立 `smbd.exe` | 单独研究进程模型、Windows 访问令牌、ACL、文件锁、文件名和并发语义。若只需 Samba 配置和服务能力，可在受支持的 Linux 环境中运行 Samba 并做 Win7 互操作测试 | 客户端构建结果无法验收文件服务器。Windows 自带 SMB 服务通常占用 TCP 445，需要单独确认监听与服务生命周期 |
| 在 Win7 上访问 Samba 共享，或管理 Win7 自己的共享 | 编写 Win32 应用，分别使用 `WNetAddConnection2W` 与 `NetShare*` API 调用系统已有功能。若客户端需要独立的 SMB3 协议栈，可评估有 Windows 构建入口的 libsmb2 | 系统 SMB 受 Win7 方言上限约束。libsmb2 的 Win7 运行仍需验证。两者均提供不同于 Samba 上游的程序接口 |

2016 年有 Samba 3.6.25 `smbclient.exe` 在 Win7 Pro x64 上用 32 位 Cygwin 编译成功的邮件记录。2021 年的第三方指南给出 Cygwin 链接器和源码修改，最后展示的构建命令针对 `smbclient`。2023 年 Samba 邮件列表讨论的是基于修改版 Cygwin 2.5.2 的 32 位 Samba 4.11.0 部分可用构建。当前实验以受维护的 Samba 4.25.1 为基线。 [2016 年编译记录](https://lists.samba.org/archive/samba/2016-May/200034.html) · [Cygwin 构建笔记](https://recolic.cc/blog/post/build-smbclient-for-windows) · [2023 年 Samba 讨论](https://lists.samba.org/archive/samba/2023-December/247381.html) · [Cygwin 3.5.0 公告](https://cygwin.com/pipermail/cygwin-announce/2024-February/011524.html) · [Cygwin x86 停止维护公告](https://cygwin.com/pipermail/cygwin-announce/2022-November/010810.html) · [Windows WNet API](https://learn.microsoft.com/en-us/windows/win32/api/winnetwk/nf-winnetwk-wnetaddconnection2w) · [Windows NetShare API](https://learn.microsoft.com/en-us/windows/win32/api/lmshare/nf-lmshare-netshareenum) · [Windows SMB TCP 端口](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/direct-hosting-of-smb-over-tcpip) · [libsmb2](https://github.com/sahlberg/libsmb2)

## 复现

Actions 工作流在 `ubuntu-24.04` 运行 x64、x86 矩阵，固定 Samba 源码提交与 LLVM-MinGW 发布资产的 SHA-256。运行 `43182908502` 的两个作业均完成，分别上传 `summary.md`、`pe-headers.txt`、`cross-answers.txt` 和 `winsock-probe.exe`。两个作业均记录 Waf 退出码 1 和 `HAVE_SECURE_MKSTEMP` 的目标运行时待测状态。 [工作流](../.github/workflows/win7-research.yml) · [运行记录](https://github.com/Grinch27/samba/actions/runs/43182908502)

本地复现需要 Bash、Git、GCC、Python 3、`pkg-config`、`curl`、`tar` 和 SHA-256 校验工具。以下命令在本研究仓库根目录运行。并行运行时，每个架构用独立的 Samba 检出目录。

```bash
set -e
git clone --depth 1 --branch samba-4.25.1 \
  https://github.com/samba-team/samba.git upstream-samba
test "$(git -C upstream-samba rev-parse HEAD)" = \
  02e8e3f93f4af787bcb3389cbff9e22e74567eb2

archive=llvm-mingw-20261104-msvcrt-ubuntu-22.04-x86_64.tar.xz
curl --fail --location --proto '=https' --proto-redir '=https' \
  --output "$archive" \
  "https://github.com/mstorsjo/llvm-mingw/releases/download/20261104/$archive"
printf '%s  %s\n' \
  '6e3342e2e0dfa56e9178f3c34b198f278bd5e603db4a759455d1439cc2230630' "$archive" \
  | sha256sum --check && tar -xJf "$archive"

for target in x86_64 i686; do
  bash research/probe-win7.sh "$target" upstream-samba "${archive%.tar.xz}/bin" "probe-$target"
done
```

`configure.log` 保存 Waf 输出，`waf/config.log` 保存详细编译与链接记录。当前 `cross-answers.txt` 的大文件条目来自静态编译结果，`HAVE_SECURE_MKSTEMP` 等依赖 Windows 行为的条目留给目标运行检测。下一轮直接移植应保存目标侧实测结果，包含权限、临时文件原子创建、文件打开时删除及清理行为。Win7 SP1 的具体补丁级别也需记录。

### Linux 原生对照

在同一提交的独立源码检出目录中运行。已验证的环境包括 GCC 14.2.0、Python 3.12.14、GnuTLS 3.8.9、MIT Kerberos 1.21.3、Parse::Yapp 1.21、GNU Bison 3.8.2 和 Flex 2.6.4。禁用 AD DC、SMB1 服务端和可选的搜索集成，构建目标限定为 `smbclient`、`smbd`。

```bash
set -e
./configure --without-ad-dc --without-ads --without-ldap --without-pam \
  --without-gpgme --without-json --without-acl-support --without-libarchive \
  --without-regedit --without-winexe --without-systemd --without-ldb-lmdb \
  --disable-python --with-system-mitkrb5 --without-smb1-server \
  --with-shared-modules='!vfs_snapper' --disable-wsp --disable-spotlight
PYTHONHASHSEED=1 WAF_MAKE=1 ./buildtools/bin/waf build --targets=client/smbclient,smbd/smbd -j 8
file -L bin/smbclient bin/smbd
bin/smbclient --version
bin/smbd --version
```

该对照验收到程序启动与版本输出。共享、认证和读写行为留给互操作测试。

## 下一阶段验收

| 阶段 | 可验证结果 |
| --- | --- |
| 编译与打包 | 记录源码提交、工具链、目标架构、完整 DLL 依赖及许可证。复核 PE 头、静态导入、延迟加载、运行时动态加载。分发 Cygwin 时准备对应源码和许可证材料 |
| Win7 SP1 启动 | 先在快照可回退的 x64 环境以普通账号执行 `smbclient --version` 和帮助命令。记录系统补丁、退出码、缺失的 DLL 或入口点。若要求 x86，再使用 x86 Win7 SP1 验证 |
| 客户端功能 | 用隔离的 Samba 测试共享验证认证、签名、列表、Unicode 路径、上传下载、内容校验和超过 4 GiB 的文件。覆盖错误密码、权限拒绝和断开重连 |
| 服务端功能 | 测试机运行 `smbd` 后，从独立客户端验证连接、认证与签名、权限拒绝、NTFS ACL 映射、文件锁、并发写入、服务退出及重启后的状态一致性 |

Win7 自带 SMB 最高协商 SMB 2.1。Win7 系统 SMB 互操作可在隔离共享上验证 SMB 2.1、强制签名和实名测试账号。要求 SMB3 加密的共享需要支持该方言的客户端。独立用户态客户端可单独验证 SMB3 能力。Windows 7 已结束扩展安全更新，运行旧版 Cygwin 也需把兼容性和安全维护状态分别记录。 [MS-SMB2 版本表](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-smb2/a64e55aa-1152-48e4-8206-edd96444e7f7) · [Samba 协议、签名与加密选项](https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html) · [Windows 7 生命周期](https://learn.microsoft.com/en-us/lifecycle/products/windows-7) · [Cygwin 分发许可](https://cygwin.com/licensing.html)

| 操作 | 风险 | 批准条件与停止点 |
| --- | --- | --- |
| 保存研究文件及运行探针 | LOW | 当前请求已指定 `Grinch27/samba`。范围为研究提交和 Actions 探针验证 |
| 对 Win7 系统启停服务、修改监听或共享权限 | HIGH | 等用户确认测试机和变更范围。在此之前停在源码、构建和静态验证 |
| 发布可安装的 Samba Windows 二进制 | HIGH | 先通过目标机和互操作验收、核对依赖分发要求，再取得发布授权 |
