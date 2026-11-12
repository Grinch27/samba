#!/usr/bin/env bash
# 待确认的关键需求：Win7 SP1 的正式目标架构，以及优先移植 smbclient 或 smbd。
# 歧义：上游 Samba 源码移植与使用 Windows 内置 SMB 的应用需要不同的验收。
# 后续研究：在目标系统执行 Waf 的临时文件检测，验证 POSIX 兼容层和目标库。
# 潜在优化：在 CI 中缓存校验通过的交叉工具链。
# 风险：PE 头、导入表和编译时断言无法证明 Win7 加载或运行成功。
# 验证重点：目标架构、系统版本字段、DLL 导入、off_t 宽度和 Waf 的实际退出状态。
set -euo pipefail

if [[ $# != 4 || ! $1 =~ ^(x86_64|i686)$ ]]; then
  printf 'Usage: %s <x86_64|i686> <Samba checkout> <LLVM-MinGW bin> <new output directory>\n' "$0" >&2
  exit 2
fi

target=$1
samba_source=$(realpath -e -- "$2")
toolchain_bin=$(realpath -e -- "$3")
source_commit=$(git -C "$samba_source" rev-parse HEAD)
git -C "$samba_source" diff --quiet HEAD --
triplet="$target-w64-mingw32"
compiler="$toolchain_bin/$triplet-clang"
target_flags=(-D_WIN32_WINNT=0x0601 -DWINVER=0x0601)
if [[ $target == x86_64 ]]; then
  pe_machine=IMAGE_FILE_MACHINE_AMD64
else
  pe_machine=IMAGE_FILE_MACHINE_I386
fi

mkdir -- "$4"
output=$(realpath -e -- "$4")
mkdir -- "$output/target-pkgconfig"

"$compiler" "${target_flags[@]}" -Wall -Wextra -Werror \
  -Wl,--major-os-version,6,--minor-os-version,1 \
  -Wl,--major-subsystem-version,6,--minor-subsystem-version,1 \
  -x c - -lws2_32 -o "$output/winsock-probe.exe" <<'C'
#include <winsock2.h>

int main(void)
{
    WSADATA data;
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        return 1;
    }
    return WSACleanup() == 0 ? 0 : 2;
}
C

pe_report="$output/pe-headers.txt"
"$toolchain_bin/llvm-readobj" --file-headers --coff-imports \
  "$output/winsock-probe.exe" > "$pe_report"
grep -Fq "Machine: $pe_machine " "$pe_report"
for field in OperatingSystem Subsystem; do
  grep -Fxq "  Major${field}Version: 6" "$pe_report"
  grep -Fxq "  Minor${field}Version: 1" "$pe_report"
done
imports=$(awk 'tolower($1) == "name:" && tolower($2) ~ /\.dll$/ { print tolower($2) }' "$pe_report" | sort -u)
if [[ $imports != $'kernel32.dll\nmsvcrt.dll\nws2_32.dll' ]]; then
  printf 'Unexpected DLL imports:\n%s\n' "$imports" >&2
  exit 1
fi

check_off_t() {
  local expected_bytes=$1
  shift
  "$compiler" "${target_flags[@]}" -DPROBE_OFF_T_BYTES="$expected_bytes" "$@" \
    -x c -fsyntax-only - <<'C'
#include <sys/types.h>
_Static_assert(sizeof(off_t) == PROBE_OFF_T_BYTES, "unexpected off_t size");
C
}

check_off_t 4
check_off_t 8 -D_FILE_OFFSET_BITS=64
check_off_t 4 -D_LARGE_FILES

# 以下是原生 Windows 目标的 getconf 缺省和编译时实测值。其余运行时回答由 Waf 记录。
answers="$output/cross-answers.txt"
cat > "$answers" <<'ANSWERS'
Checking getconf LFS_CFLAGS: NO
Checking for large file support without additional flags: NO
Checking for -D_FILE_OFFSET_BITS=64: OK
Checking for -D_LARGE_FILES: NO
ANSWERS

configure_status=0
(
  cd "$samba_source"
  env -u CPATH -u C_INCLUDE_PATH -u LIBRARY_PATH -u PKG_CONFIG_SYSROOT_DIR \
    PATH="$toolchain_bin:$PATH" CC="$triplet-clang" AR="$triplet-ar" \
    CFLAGS="${target_flags[*]}" CPPFLAGS= LDFLAGS= \
    PKG_CONFIG_DIR= PKG_CONFIG_PATH= PKG_CONFIG_LIBDIR="$output/target-pkgconfig" \
    ./configure --out="$output/waf" \
      --cross-compile --hostcc=gcc --cross-answers="$answers" \
      --without-ad-dc --without-ads --without-ldap --without-pam \
      --without-gpgme --without-json --without-acl-support --without-libarchive \
      --without-regedit --without-winexe --without-systemd --without-ldb-lmdb \
      --disable-python
) > "$output/configure.log" 2>&1 || configure_status=$?

if (( configure_status == 0 )); then
  outcome='配置通过，待编译 Samba 目标。'
elif grep -Eq '^Checking for HAVE_SECURE_MKSTEMP +: not found' "$output/configure.log" \
  && grep -Fxq 'Checking for HAVE_SECURE_MKSTEMP: UNKNOWN' "$answers"; then
  outcome='配置停在 HAVE_SECURE_MKSTEMP，待目标 Windows 执行检测。'
else
  tail -n 32 "$output/configure.log" >&2
  printf 'Unexpected configure failure. See %s\n' "$output/configure.log" >&2
  exit "$configure_status"
fi

cat > "$output/summary.md" <<SUMMARY
### Samba Win7 交叉配置探针 ($target)

- Samba 源码提交 \`$source_commit\`。
- Winsock 探针编译通过。PE 目标版本字段为 6.1，直接导入 DLL 为 kernel32.dll、msvcrt.dll 和 ws2_32.dll。
- \`off_t\` 默认 4 字节，\`_FILE_OFFSET_BITS=64\` 时为 8 字节，仅设置 \`_LARGE_FILES\` 时为 4 字节。
- Waf 退出码 \`$configure_status\`。$outcome
- Samba 程序的编译结果及 Win7 上的运行结果待验证。
SUMMARY
cat "$output/summary.md"
