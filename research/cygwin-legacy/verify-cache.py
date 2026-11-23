#!/usr/bin/env python3
# 待确认：历史快照中的开发包是否具有完整、无歧义的依赖闭包。
# 歧义：部分虚拟包不包含 install 归档，其他包可提供它们。
# 后续研究：记录最终包版本、工具链及 Win7 实际动态链接依赖。
# 潜在优化：基线完成后考虑按固定索引缓存经过验证的归档。
# 风险：历史索引没有可用签名，必须使用此前核实的索引 SHA-256。
# 验证重点：下载索引固定、依赖可解析、全部文件长度及 SHA-512 正确。
"""Download a checked Cygwin Time Machine package closure for offline setup."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import lzma
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.request import Request, urlopen

INDEX_SHA256 = "4bbf34f9922a2360b6bec9a149efad59a5fda5d33de5a28990c7480286dbf46d"
MIRROR = "http://ctm.crouchingtigerhiddenfruitbat.org/pub/cygwin/circa/64bit/2024/01/30/231215/"
INSTALL = re.compile(r"^install:\s+(\S+)\s+(\d+)\s+([a-fA-F0-9]{128})\s*$")


def digest(path, method="sha512"):
    checksum = hashlib.new(method)
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(part)
    return checksum.hexdigest()


def select_index(cache):
    for path in cache.rglob("*"):
        if not path.is_file() or path.name not in {"setup.ini", "setup.xz"}:
            continue
        data = lzma.decompress(path.read_bytes()) if path.suffix == ".xz" else path.read_bytes()
        if hashlib.sha256(data).hexdigest() == INDEX_SHA256:
            return data.decode("utf-8"), path.parent.parent
    raise ValueError("Expected Cygwin historical index SHA-256 not found")


def read_records(index):
    packages = {}
    current = None
    active = True
    for line in index.splitlines():
        if line.startswith("@ ") or line.startswith("Package: "):
            name = line.split(None, 1)[1].strip()
            current = packages[name] = {"base": False, "deps": set(), "provides": set(), "install": None}
            active = True
        elif current is not None and line.startswith("["):
            active = line.strip() == "[curr]"
        elif current is not None and active:
            if line.startswith("category:"):
                current["base"] |= "Base" in line[9:].split()
            elif line.startswith("provides:"):
                current["provides"].update(part.strip() for part in line[9:].split(",") if part.strip())
            elif line.startswith("requires:"):
                current["deps"].update(line[9:].split())
            elif line.startswith(("depends:", "depends2:")):
                current["deps"].update(
                    item.split("(", 1)[0].strip()
                    for item in line.split(":", 1)[1].split(",")
                    if item.strip()
                )
            else:
                match = INSTALL.match(line)
                if match:
                    name, size, checksum = match.groups()
                    current["install"] = (name, int(size), checksum.lower())
    return packages


def closure(packages, requested):
    pending = [name for name, record in packages.items() if record["base"]]
    pending.extend(requested)
    providers = {}
    for package, record in packages.items():
        for virtual in record["provides"]:
            providers.setdefault(virtual, []).append(package)
    chosen = set()
    while pending:
        name = pending.pop()
        if name in chosen:
            continue
        if name == "_windows":
            continue  # Cygwin setup synthetic host capability, not an archive.
        if name not in packages:
            alternatives = providers.get(name, [])
            selected = [provider for provider in alternatives if provider in chosen or provider in requested]
            if len(selected) == 1:
                pending.append(selected[0])
                continue
            if len(alternatives) == 1:
                pending.append(alternatives[0])
                continue
            raise ValueError(f"Historical dependency has no unique provider: {name} ({alternatives})")
        chosen.add(name)
        pending.extend(packages[name]["deps"] - chosen)
    return [packages[name]["install"] for name in sorted(chosen)
            if packages[name]["install"] is not None]


def fetch_one(archive, root):
    relative, expected_size, expected_hash = archive
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "x86_64":
        raise ValueError(f"Invalid historical package path: {relative}")
    output = root.joinpath(*path.parts)
    if output.exists() and output.stat().st_size == expected_size and digest(output) == expected_hash:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    url = MIRROR + relative
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Samba-Win7-Cygwin-Research"}), timeout=90) as response:
                with temporary.open("wb") as destination:
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        destination.write(chunk)
            if temporary.stat().st_size != expected_size or digest(temporary) != expected_hash:
                raise ValueError(f"Checksum failed for {relative}")
            temporary.replace(output)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise


def verify_archives(cache, root, index):
    all_records = {
        (path, int(size), checksum.lower())
        for path, size, checksum in re.findall(INSTALL.pattern, index, re.M)
    }
    known = {name: (size, checksum) for name, size, checksum in all_records}
    suffixes = (".tar.xz", ".tar.zst", ".tar.gz", ".tar.bz2")
    archives = [path for path in cache.rglob("*")
                if path.is_file() and path.name.endswith(suffixes)]
    if not archives:
        raise ValueError("No historical archives downloaded")
    for archive in archives:
        relative = archive.relative_to(root).as_posix()
        if relative not in known:
            raise ValueError(f"Unknown package in cache: {relative}")
        size, checksum = known[relative]
        if archive.stat().st_size != size or digest(archive) != checksum:
            raise ValueError(f"Package integrity failure: {relative}")
    print(f"Verified historical index and {len(archives)} package archives")


def main():
    if len(sys.argv) not in (2, 4) or (len(sys.argv) == 4 and sys.argv[1] != "--download"):
        raise SystemExit("Usage: verify-cache.py [--download] <cache directory> [comma-separated packages]")
    download = len(sys.argv) == 4
    cache = Path(sys.argv[2] if download else sys.argv[1]).resolve(strict=True)
    index, root = select_index(cache)
    if download:
        packages = read_records(index)
        archives = closure(packages, sys.argv[3].split(","))
        print(f"Downloading and verifying {len(archives)} pinned Cygwin packages", flush=True)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda record: fetch_one(record, root), archives))
    verify_archives(cache, root, index)


if __name__ == "__main__":
    main()
