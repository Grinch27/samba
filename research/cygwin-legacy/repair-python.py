#!/usr/bin/env python3
# 待确认：历史 Setup 未选择 Python 的具体求解冲突。
# 歧义：补齐历史运行时不是完整安装器事务。
# 后续研究：以 solver 日志选择长期修复。
# 潜在优化：仅选取 Waf 必需的 Python 依赖。
# 风险：只允许在临时构建根补齐已校验且未安装的归档，不覆盖已安装文件。
# 验证重点：完整解释器、导入测试、Cygwin ABI 及依赖来源。
"""Repair an incomplete historical Python install in the disposable CI root."""

import argparse
import hashlib
from pathlib import Path
import subprocess


def run(root, command, *arguments):
    return subprocess.run(
        [str(root / "bin" / "bash.exe"), "--noprofile", "--norc",
         "-c", command, "python-repair", *map(str, arguments)],
        check=True, timeout=180)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("cache", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    cache = args.cache.resolve(strict=True)
    database = root / "etc/setup/installed.db"
    installed = {line.split()[0] for line in database.read_text(
        encoding="utf-8", errors="strict").splitlines()[1:] if line.split()}
    if not installed:
        raise ValueError("Offline installer database is empty")
    entries = []
    for line in (cache / "python-runtime.tsv").read_text(encoding="utf-8").splitlines():
        name, relative, size, checksum = line.split("\t")
        if name in installed:
            continue
        archive = (cache / "historical" / relative).resolve(strict=True)
        if not archive.is_relative_to(cache):
            raise ValueError("Archive escaped verified cache")
        with archive.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha512").hexdigest()
        if archive.stat().st_size != int(size) or actual != checksum:
            raise ValueError(f"Archive integrity mismatch: {name}")
        entries.append((name, archive))
    for name, archive in entries:
        print(f"Adding missing verified build-only package: {name}", flush=True)
        run(root, 'set -e; export PATH=/usr/bin:/bin; '
            'tar --skip-old-files -xf "$(cygpath -u "$1")" -C /', archive)
    run(root, 'set -e; export PATH=/usr/bin:/bin; '
        'test -x /usr/bin/python3.9; '
        'if ! command -v python3 >/dev/null; then ln -s python3.9 /usr/bin/python3; fi; '
        'if ! command -v python >/dev/null; then ln -s python3.9 /usr/bin/python; fi; '
        'python3 --version; python3 -c "import ssl, ctypes, sqlite3, zlib, hashlib, multiprocessing"')


if __name__ == "__main__":
    main()
