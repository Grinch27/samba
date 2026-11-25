#!/usr/bin/env bash
# 待确认：GnuTLS 3.8.13 新库与旧版 Cygwin 的 Win7 可用性。
# 歧义：Windows Server 2022 的旧 ABI 探针不等于 Win7 实机验收。
# 后续研究：核实 DLL 动态加载、NTFS ACL 和 RPC。
# 潜在优化：冷编译成功后再考虑跨运行缓存。
# 风险：不得替换正在运行的 Cygwin 3.4.10 核心 DLL。
# 验证重点：逐包 SHA-512、Parse::Yapp 功能和库版本。
set -euo pipefail

[[ $# == 1 ]] || { echo "Usage: $0 <evidence directory>" >&2; exit 2; }
export PATH=/usr/bin:/bin
output=$1
# The archive is downloaded and verified by the Ubuntu dependency job.
tar -xf "$output/Parse-Yapp-1.21.tar.gz" -C "$output"
PERL5LIB="$output/Parse-Yapp-1.21/lib" perl -MParse::Yapp -e 'print "Parse::Yapp available\n"'
# Waf needs the CLI in its restricted PATH, not just the Perl module.
install -m 0755 "$output/Parse-Yapp-1.21/yapp" /usr/bin/yapp
PERL5LIB="$output/Parse-Yapp-1.21/lib" /usr/bin/yapp -V
