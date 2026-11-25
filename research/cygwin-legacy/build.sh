#!/usr/bin/env bash
# 待确认的关键需求：正式服务端是否可分发 Cygwin 运行时及其依赖。
# 歧义：Cygwin 3.4.10 ABI 是探针目标，较新 Windows 可作为对照运行环境。
# 后续研究：在 Win7 VM 使用同一套探针和依赖验证实际加载。
# 潜在优化：依赖集稳定后复用已校验的下载缓存。
# 风险：PE 版本与导入表只能用于静态检查。
# 验证重点：固定依赖哈希，使用 3.4.10 头文件与启动对象构建探针。
set -euo pipefail

if [[ $# != 3 ]]; then
  printf 'Usage: %s <LLVM-MinGW root> <new output directory> <prepared archive directory>\n' "$0" >&2
  exit 2
fi

probe_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
toolchain=$(cd -- "$1" && pwd -P)
mkdir -- "$2"
output=$(cd -- "$2" && pwd -P)
archives=$(cd -- "$3" && pwd -P)
mkdir -- "$output/sysroot" "$output/runtime"

# The Ubuntu dependency job verifies every archive before transfer.
while IFS=$'\t' read -r url size digest; do
  [[ $url == \#* || -z $url ]] && continue
  tar --exclude=usr/lib/libg.a -xf "$archives/${url##*/}" -C "$output/sysroot"
done < "$probe_dir/packages.tsv"

sysroot="$output/sysroot/usr"
cp -- "$sysroot/bin/"*.dll "$output/runtime/"
for probe in datagram crypto filesystem; do
  libraries=()
  if [[ $probe == crypto ]]; then
    libraries+=("$sysroot/lib/libgnutls.dll.a")
  fi

  "$toolchain/bin/clang" --target=x86_64-pc-cygwin -nostdlibinc \
    -isystem "$sysroot/include" -std=gnu11 -Wall -Wextra -Werror \
    -c "$probe_dir/$probe.c" -o "$output/$probe.o"
  executable="$output/runtime/legacy-$probe.exe"
  "$toolchain/bin/ld.lld" -m i386pep --subsystem console --entry mainCRTStartup \
    --major-os-version 6 --minor-os-version 1 --major-subsystem-version 6 --minor-subsystem-version 1 \
    "$sysroot/lib/crt0.o" "$output/$probe.o" "${libraries[@]}" "$sysroot/lib/libcygwin.a" \
    "$toolchain/x86_64-w64-mingw32/lib/libkernel32.a" -o "$executable"
  "$toolchain/bin/llvm-readobj" --file-headers --coff-imports "$executable" > "$output/$probe-pe.txt"
done
