# Win7 Cygwin Setup 管理式部署包研究（2026-11-25）

## 目标与范围

用户要求研究 Cygwin 官方 Setup 管理式运行环境，并重新生成部署包；保留 Win7 SP1 x64、构建时动态解析 Samba 最新稳定版、四工具 smbd/testparm/smbpasswd/smbcontrol、双栈白名单、独立账户密码、每共享权限和签名要求。ZIP 仍作为离线安装材料分发形式；不制作自有 MSI，不自动安装 Windows 服务或修改目标机防火墙、原生 SMB 服务及账户权限。本文为设计与待验收规范，不表示已产生可安装二进制。

## 官方依据

- https://cygwin.com/install.html ：Win7 最后兼容 DLL 3.4.10；使用当前 Setup 与 --allow-unsupported-windows，历史仓库 URL 见该页。支持本地目录离线安装。
- https://cygwin.com/faq.html ：分离安装根和 DLL，禁止跨安装混用；建议通过官方 Setup 管理运行环境。
- https://cygwin.com/cygwin-ug-net/ntsec.html ：SID/UID/GID、S4U、访问令牌及身份切换；SYSTEM 默认 UID 18，Administrator 示例 UID 197108。
- https://cygwin.com/package-server.html 和 https://cygwin.com/packaging-package-files.html ：本地自定义仓库、包元数据及 mksetupini。
- https://cygwin.com/licensing.html ：Cygwin API library LGPLv3+，其他包各自许可；对应源码材料随分发提供。

## 已确认事实

- 现代对照 Run 45398538598 / Artifact 14924519512：smbd.exe 4.25.1 + Cygwin 3.6.12 编译成功，16 个非系统 DLL 依赖；不代表 Win7 可用。
- Run 45524518258：动态版本解析 4.25.1、历史包校验及官方离线 Setup 安装、Python 3.9.16 恢复、库覆盖均成功；Parse-Yapp 下载 404，未进入 Samba 编译。修正 CPAN W/WR 为 W/WB，CPAN CHECKSUMS 中既有 SHA-256 一致。
- Runner 实际 UID 197108；Samba smbpasswd -L 检查 UID 0。Setup 本身不会解决这个问题。
- 当前构建使用 --without-acl-support；NTFS 文件操作身份与 SMB ACL 管理能力不得混为一谈。

## 设计候选：独立最小运行时

1. 将运行时安装至独立 NTFS 根（例如 C:\SambaRuntime），安装器管理 bin、lib、etc、postinstall、软件包数据库，不复制或替换其他 Cygwin 安装目录。
2. 使用历史基础仓库固定索引与包哈希；不要在目标机接入滚动更新。动态 Samba 版本与固定 Cygwin ABI 分离。
3. 完整四工具成功后，以实际 PE 导入闭包和动态模块、数据文件需求为准，建立 runtime-lock：包名、版本、架构、原始归档 SHA-512、对应源码、实际文件哈希。编译工具链不进入部署仓库。
4. 若新 GnuTLS 等覆盖库不能由旧索引正确解决依赖或 ABI，使用 Cygwin 3.4.10 SDK 重新构建必要库，并制作独立的 Cygwin 包与索引；禁止直接混入最新 Cygwin 核心 DLL。当前覆盖成功仅是文件安装成功。
5. 将 Samba 作为独立自定义包（暂名 samba-win7），安装四工具、必需动态模块及配置模板，使用 cygport 或可验证等效方式生成包与元数据。由 mksetupini 等生成自定义仓库索引。保留源代码及构建配方。不得使用未验证的包或静默降级。
6. 最终 ZIP 含已核验 Setup、离线仓库、安装入口、说明、哈希清单，另提供对应源码 ZIP。所有包从本地目录安装；历史无签名索引仅在可信固定哈希与包完整校验通过后允许离线使用 --no-verify。Setup 本体应核验签名。
7. 安装后使用明确根目录下的配置与状态目录；不修改系统 PATH，不保存明文 Windows 密码，不生成预置凭据。默认 IPv4/IPv6 仅回环、拒绝其余地址、禁止 guest、每共享最小授权。现有安装不得覆盖或降级。
8. 身份专项研究：使用真实 Windows 用户/SID/访问令牌；对合法授权的管理身份与 S4U 切换进行测试，禁止删除或绕过 Samba 权限检查。若必须引入 LocalSystem 服务，须重新明确部署授权及权限模型；不自动注册服务。cygserver 是否必须由真实 IPC/身份需求确定。

## 发布门禁

- 四工具真实编译、递归依赖及对应源码完整；Windows 运行库 PE 导入兼容性检查。
- 从离线 ZIP 安装到全新 Runner 根，不依赖构建根或其 PATH；验证实际 runtime 3.4.10、cygcheck -c、安装日志和四工具启动。
- Windows 账户数据库真实初始化、双栈白名单正反向连接、独立账户密码、共享读写隔离及 NTFS 文件操作身份；不得为通过测试扩大权限。Win7 实机仍待验证，预发布标签注明。
- 不分发测试密码数据库、不暴露外部网络端口、不自动安装目标机服务。
- 首次合格 Pre-release 按既有授权；后续产物不覆盖既有版本。

## 当前阻塞与边界

当前工作流仍是原先 DLL 便携包实验管线，Setup 管理式运行时部署包生成尚未实现。不可将现代对照诊断 Artifact、历史基础包缓存或上游 Setup 当作完成的 Samba 安装包。下一入口为修正后的 Parse-Yapp 构建，取得四工具与实际依赖，再实现运行时仓库生成、离线安装验收。用户真实 Win7 安装、账户/ACL 变更和服务注册均未执行。

## 决策冻结（2026-11-25）

正式采用独立 Cygwin 3.4.10 Setup 管理式离线 ZIP；Samba 自身作为自定义 Cygwin 软件包。旧扁平 DLL 便携包只作依赖研究 Artifact，移除旧自动发布 Job，未撤销首个符合新规格的 Pre-release 授权。新版发布 Job 必须等管理式离线安装和安全门禁实现后再启用。不得覆盖或删除已有产物。

### Python 部署边界（P0）

目标 Win7 SP1 x64 不要求安装原生 Windows Python，也不主动安装 Cygwin Python。当前使用 --without-ad-dc --disable-python，只交付独立文件服务的四个 C 工具；Python 3.9.16 是 Waf 构建依赖，原生 Python 3.14 是 CI 打包和归档处理依赖。Setup 本身为 Windows EXE。现代 smbd 实际递归 DLL 清单未发现 Python DLL。Run 45524865945 已实际通过 Python >=3.6.0 检查（3.9.16），并显示 python headers: Check disabled due to --disable-python；随后在 GnuTLS >=3.6.13 检测失败。无 Win7 完整四工具产物，因此 Python-free 运行仍是待验证目标，不宣称已经通过。

运行仓库仅使用历史 Base、实际运行包、经验证的动态模块/资源和自定义 Samba 包；分别检查二进制普通/延迟导入、动态加载、脚本 shebang、postinstall、包依赖闭包及目标机实际安装清单。新干净 Runner 的隔离安装不得依赖构建环境 Python 或主机 PATH；不得包含 python.exe/python3*.exe、cygpython*.dll、原生 python*.dll 或 Python site-packages，除非后续证明为不可替代依赖并获得用户批准。若历史 Base 或任何选定运行包拉入 Python，明确定位引入者并研究替代或合法裁剪方案，不跳过依赖求解。cygport/mksetupini 可以使用 Python，但只能在打包 CI 使用，不部署到 Win7。不要为新版本的 Python 需求扩大目标机依赖。

### 当前 GnuTLS 阻塞

Run 45524865945 / Job 138905621458：Parse-Yapp 成功，Waf 配置首次到达 GnuTLS 检测；getrandom ok，最低 3.6.13，not found。根因尚未确认：可能是 .pc 元数据、开发头文件、导入库、依赖 pc 文件或实际链接失败，不能只据 not found 推断缺库。保存完整 bin/config.log 与 gnutls-probe.txt；记录 pkg-config 查找路径、gnutls 版本/普通及 static cflags/libs、头文件、导入库和 DLL 依赖。先核对证据，再决定补齐匹配开发依赖或使用旧 SDK 重建 GnuTLS/Nettle。禁止降低 Samba 加密库最低版本要求。

### 验收与账户研究

Run 45524518315 的 SMB2_10/SMB3_11 共 18 个 PASS 日志项（含复合测试）：签名连接、文件操作、错密、IPv4 来源拒绝、匿名拒绝、未授权账户、独立读者密码和只读授权、IPv6 回环允许及配置拒绝、真实非白名单 IPv6 拒绝。仅 Linux 对照，目标 Windows 运行仍未验证。Runner UID 197108；LocalSystem 默认 UID 18，不自动等于 Samba root。下一阶段研究真实访问令牌、S4U、NTFS ACL 及必要的专用服务启动方案；不伪造 root、不跳过权限检查、不自动注册服务、不修改用户真实系统。
