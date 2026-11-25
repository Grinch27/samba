#!/usr/bin/env bash
# 待确认的关键需求：Win7 SP1 x64 上的 smbd 服务、SMB 方言及依赖分发方式。
# 歧义：当前 Cygwin 编译宿主与 Win7 兼容运行时的 ABI 需要分别验证。
# 后续研究：复现 Cygwin 3.4.10，验证 NTFS ACL 和不同 SMB 会话的身份切换。
# 潜在优化：确定编译阻塞后再收窄依赖和 Samba 构建目标。
# 风险：新版 Cygwin 构建结果无法作为 Win7 可运行证据。
# 验证重点：记录 Waf 配置、服务端编译及版本命令的真实状态。
set -euo pipefail

if [[ $# != 1 ]]; then
  printf 'Usage: %s <new output directory>\n' "$0" >&2
  exit 2
fi
export PATH=/usr/bin:/bin
export LC_ALL=C
script_dir=$(dirname -- "$(realpath -e -- "${BASH_SOURCE[0]}")")
host_system=$(uname -s)
host_arch=$(uname -m)
if [[ $host_system != CYGWIN* || $host_arch != x86_64 ]]; then
  printf 'Expected x86_64 Cygwin, found %s %s.\n' "$host_system" "$host_arch" >&2
  exit 2
fi

mkdir -- "$1"
output=$(realpath -e -- "$1")
summary="$output/summary.md"
source_commit=${SAMBA_COMMIT:?Resolve the stable Samba commit first}
source_version=${SAMBA_VERSION:?Resolve the stable Samba version first}
[[ $source_version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && $source_commit =~ ^[0-9a-f]{40}$ ]]

{
  printf '# Samba %s smbd Cygwin probe\n\n' "$source_version"
  printf -- '- Host: `%s`.\n' "$(uname -srm)"
  printf -- '- Cygwin runtime: `%s`.\n' "$(uname -r)"
  printf -- '- Samba commit: `%s`.\n' "$source_commit"
} | tee "$summary"
cygcheck -c > "$output/packages.txt"

git -c core.autocrlf=false clone --quiet --depth 1 --branch "samba-$source_version" \
  https://github.com/samba-team/samba.git "$output/upstream-samba"
cd "$output/upstream-samba"
test "$(git rev-parse HEAD)" = "$source_commit"
git apply --check --whitespace=error-all "$script_dir/cygwin-vfs-compat.patch"
git apply --whitespace=error-all "$script_dir/cygwin-vfs-compat.patch"
printf -- '- VFS portability patch: `cygwin-vfs-compat.patch`.\n' | tee -a "$summary"

export PYTHONUNBUFFERED=1
export WAF_NO_PREFORK=1

# Preserve the package metadata and linker probe before Waf configuration.
# A failing diagnostic is evidence, not a replacement for Waf's own checks.
{
  printf 'pkg-config path: '
  pkg-config --variable=pc_path pkg-config
  printf '\nGnuTLS metadata:\n'
  pkg-config --print-errors --modversion gnutls
  pkg-config --print-errors --cflags --libs gnutls
  pkg-config --print-errors --static --libs gnutls
  printf '\nGnuTLS package config locations:\n'
  find /usr/lib /usr/share/pkgconfig -name gnutls.pc -print 2>/dev/null
  printf '\nGnuTLS headers and import libraries:\n'
  ls -l /usr/include/gnutls/gnutls.h /usr/lib/libgnutls.dll.a /usr/bin/cyggnutls-30.dll
  printf '\nGnuTLS DLL dependencies:\n'
  cygcheck /usr/bin/cyggnutls-30.dll
} > "$output/gnutls-probe.txt" 2>&1 || true
cat "$output/gnutls-probe.txt"

configure_status=0
# Cygwin 的 quotactl 探针通过，但其 dqblk 结构没有 dqb_curblocks。
timeout --kill-after=15s 8m ./configure \
  --without-ad-dc --without-ads --without-ldap --without-pam \
  --without-gpgme --without-json --without-acl-support --without-libarchive \
  --without-regedit --without-winexe --without-systemd --without-ldb-lmdb --without-quotas \
  --disable-python --without-smb1-server --with-shared-modules='!vfs_snapper' \
  --disable-wsp --disable-spotlight --without-libunwind --nonshared-binary="${SAMBA_NONSHARED_BINARIES:-smbd/smbd}" \
  2>&1 | tee "$output/configure.log" || configure_status=$?
printf -- '- Waf configure exit code: `%d`.\n' "$configure_status" | tee -a "$summary"
tail -n 36 "$output/configure.log" > "$output/configure-tail.txt"
if (( configure_status != 0 )); then
  exit "$configure_status"
fi

build_status=0
# 32 分钟的一轮跑到 2242/2374，结束前每项约耗时 3 至 4 秒。
PYTHONHASHSEED=1 WAF_MAKE=1 timeout --kill-after=15s 52m \
  ./buildtools/bin/waf build --targets=smbd/smbd -j 4 \
  2>&1 | tee "$output/build.log" || build_status=$?
printf -- '- Waf smbd build exit code: `%d`.\n' "$build_status" | tee -a "$summary"
tail -n 36 "$output/build.log" > "$output/build-tail.txt"
if (( build_status != 0 )); then
  exit "$build_status"
fi

server=$(find bin/default/source3/smbd -maxdepth 1 -type f -name smbd.exe -print -quit)
test -n "$server"
version=$("$server" --version)
printf -- '- Server version: `%s`.\n' "$version" | tee -a "$summary"
cygcheck "$server" > "$output/smbd-dlls.txt"
