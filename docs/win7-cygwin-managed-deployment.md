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
