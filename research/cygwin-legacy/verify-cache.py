#!/usr/bin/env python3
# 待确认：历史快照能否继续提供固定哈希的包索引。
# 歧义：setup 可能缓存未压缩或 xz 压缩索引。
# 后续研究：确认全部构建依赖的确切包版本。
# 潜在优化：下载缓存仅在有性能证据时启用。
# 风险：历史索引未签名；固定哈希只是可复现完整性基线。
# 验证重点：安装前核对索引 SHA-256 和所有包 SHA-512。
"""Fail closed on changes to the archived Cygwin package index or archives."""

import hashlib
import lzma
from pathlib import Path
import re
import sys

INDEX_SHA256 = "4bbf34f9922a2360b6bec9a149efad59a5fda5d33de5a28990c7480286dbf46d"
INSTALL = re.compile(r"^install:\s+(\S+)\s+(\d+)\s+([A-Fa-f0-9]{128})\s*$", re.M)


def hash_file(path):
    result = hashlib.sha512()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify-cache.py <cygwin-cache>")
    cache = Path(sys.argv[1]).resolve(strict=True)
    index_files = [p for p in cache.rglob("*")
                   if p.is_file() and p.name in {"setup.ini", "setup.xz"}]
    indexes = []
    for path in index_files:
        data = lzma.decompress(path.read_bytes()) if path.suffix == ".xz" else path.read_bytes()
        if hashlib.sha256(data).hexdigest() == INDEX_SHA256:
            indexes.append(data)
    if not indexes:
        raise ValueError("Missing expected historical Cygwin package index (SHA-256)")
    known = {name.replace("\\", "/").lower(): (int(size), sha.lower())
             for name, size, sha in INSTALL.findall(indexes[0].decode("utf-8"))}
    if not known:
        raise ValueError("No package records in historical index")
    archives = [p for p in cache.rglob("*")
                if p.is_file() and p.name.endswith((".tar.xz", ".tar.zst", ".tar.bz2", ".tar.gz"))]
    if not archives:
        raise ValueError("No binary packages downloaded")
    for path in archives:
        matches = [value for name, value in known.items()
                   if path.as_posix().lower().endswith("/" + name)]
        if len(matches) != 1:
            raise ValueError(f"Archive is missing or ambiguous in pinned index: {path}")
        size, sha = matches[0]
        if path.stat().st_size != size or hash_file(path) != sha:
            raise ValueError(f"Archive checksum mismatch: {path}")
    print(f"Verified pinned index and {len(archives)} downloaded packages")


if __name__ == "__main__":
    main()
