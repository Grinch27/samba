#!/usr/bin/env python3
# 待确认：旧 ABI 的工具链、动态加载与 Win7 实机兼容性。
# 歧义：Server 2022 通过不等于 Win7 通过。
# 后续研究：Win7 双账户 NTFS ACL 和运行时模块。
# 潜在优化：成功冷构建后优化缓存。
# 风险：必须校验历史索引、包和对应源码；不发布缺件产物。
# 验证重点：三工具、DLL 来源、隔离启动和 ZIP 完整性。
"""Install pinned overlay packages before starting any legacy Cygwin process."""

import argparse
import hashlib
from http.client import IncompleteRead
import posixpath
from pathlib import Path, PurePosixPath
import tarfile
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

def download(url, size, checksum, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, 4):
        print(f"Downloading {destination.name} (attempt {attempt}/3)", flush=True)
        try:
            with urlopen(url, timeout=90) as response, partial.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
        except (URLError, TimeoutError, ConnectionError, IncompleteRead) as error:
            partial.unlink(missing_ok=True)
            if isinstance(error, HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}:
                raise
            if attempt == 3:
                raise
            print(f"Retrying {destination.name}: {error}", flush=True)
            sleep(attempt * 2)
            continue
        with partial.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha512").hexdigest()
        if partial.stat().st_size != size or actual != checksum:
            partial.unlink(missing_ok=True)
            raise ValueError(f"Archive integrity failed: {url}")
        partial.replace(destination)
        return

def mapped(name):
    parts = PurePosixPath(name).parts
    if not parts or parts[0] == "/" or ".." in parts:
        raise ValueError(f"Unsafe package member: {name}")
    if parts[:2] in {("usr", "bin"), ("usr", "lib")}:
        parts = parts[1:]
    return "/".join(parts)

def member_filter(member, dest):
    original = member.name
    member.name = mapped(original)
    if member.name.startswith(("usr/share/man/", "usr/share/info/")):
        return None
    if member.issym() or member.islnk():
        target = member.linkname
        if member.issym() and not target.startswith("/"):
            target = posixpath.join(posixpath.dirname(original), target)
        target = mapped(posixpath.normpath(target.lstrip("/")))
        member.linkname = (posixpath.relpath(target, posixpath.dirname(member.name))
                           if member.issym() else target)
    return tarfile.data_filter(member, dest)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("packages", type=Path)
    parser.add_argument("cache", type=Path)
    args = parser.parse_args()
    for line in args.packages.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        url, size, checksum = line.split("\t")
        name = url.rsplit("/", 1)[-1]
        if name.startswith(("cygwin-3.4.10-", "cygwin-devel-3.4.10-")):
            continue
        archive = args.cache / name
        download(url, int(size), checksum, archive)
        print(f"Overlay verified {name}", flush=True)
        with tarfile.open(archive, "r:*") as source:
            source.extractall(args.root, filter=member_filter)

if __name__ == "__main__":
    main()
