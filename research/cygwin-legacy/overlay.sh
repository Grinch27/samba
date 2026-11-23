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
script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
output=$1
mkdir -p -- "$output/packages"
while IFS=$'\t' read -r url size checksum; do
  [[ $url == \#* || -z $url ]] && continue
  case "$url" in
    */cygwin/cygwin-3.4.10-*|*/cygwin-devel/cygwin-devel-3.4.10-*) continue ;;
  esac
  archive="$output/packages/$(basename -- "$url")"
  curl --fail --location --silent --show-error --retry 2 --max-time 90 \
    --proto '=https' --proto-redir '=https' --output "$archive" "$url"
  [[ $(wc -c < "$archive") -eq $size ]]
  printf '%s  %s\n' "$checksum" "$archive" | sha512sum --check
  tar -xf "$archive" -C /
done < "$script_dir/packages.tsv"
yapp=https://cpan.metacpan.org/authors/id/W/WR/WBRASWELL/Parse-Yapp-1.21.tar.gz
checksum=3810e998308fba2e0f4f26043035032b027ce51ce5c8a52a8b8e340ca65f13e5
curl --fail --location --silent --show-error --retry 2 --max-time 90 \
  --proto '=https' --proto-redir '=https' --output "$output/Parse-Yapp-1.21.tar.gz" "$yapp"
printf '%s  %s\n' "$checksum" "$output/Parse-Yapp-1.21.tar.gz" | sha256sum --check
tar -xf "$output/Parse-Yapp-1.21.tar.gz" -C "$output"
PERL5LIB="$output/Parse-Yapp-1.21/lib" perl -MParse::Yapp -e 'print "Parse::Yapp available\n"'
