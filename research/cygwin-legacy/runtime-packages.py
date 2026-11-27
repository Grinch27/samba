#!/usr/bin/env python3
# 待确认：运行时包的递归依赖、按需加载模块、Base 集合是否无 Python。
# 歧义：递归 PE 导入提供者集合不等于完整 Setup 安装依赖闭包。
# 后续研究：对应源码、版本约束、postinstall 及 Win7 实际加载。
# 潜在优化：历史包仅查询 Setup 文件清单，覆盖包仅检查目标 DLL。
# 风险：Setup autorebase 会改变 DLL 字节；覆盖包不在 Setup 数据库中。
# 验证重点：安装版本与固定归档一致，覆盖包优先，无法确定归属时失败。
"""Identify runtime DLL providers from previously verified build archives."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


INSTALL = re.compile(r"^install:\s+(\S+)\s+(\d+)\s+([a-fA-F0-9]{128})\s*$")


def historical_archives(cache):
    index = cache / "historical/x86_64/setup.ini"
    records = {}
    package = None
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.startswith(("@ ", "Package: ")):
            package = line.split(None, 1)[1].strip()
        match = INSTALL.fullmatch(line)
        if package and match:
            relative, size, checksum = match.groups()
            path = cache / "historical" / relative
            if path.is_file():
                records[path] = {
                    "package": package,
                    "archive": relative,
                    "size": int(size),
                    "sha512": checksum.lower(),
                    "origin": "historical",
                }
    return records


def overlay_archives(cache, lock):
    records = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        url, size, checksum = line.split("\t")
        relative = "x86_64/" + url.split("/x86_64/", 1)[1]
        path = cache / PurePosixPath(relative).name
        if path.is_file():
            records[path] = {
                "package": PurePosixPath(relative).parent.name,
                "archive": relative,
                "size": int(size),
                "sha512": checksum.lower(),
                "origin": "overlay",
            }
    return records


def archive_version(name):
    # installed.db historically uses .tar.bz2 even for xz/zst archives.
    return re.sub(r"-x86_64$|-noarch$", "",
                  re.sub(r"\.tar\.(?:bz2|xz|zst|gz)$", "", name))


def setup_providers(root, archives, required):
    database = root / "etc/setup"
    lines = (database / "installed.db").read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("INSTALLED.DB "):
        raise ValueError("Invalid Setup installed.db")
    installed = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        package, filename, *_ = line.split()
        installed[package] = archive_version(PurePosixPath(filename).name)
    providers = {}
    for path, record in archives.items():
        package = record["package"]
        if installed.get(package) != archive_version(path.name):
            continue
        listing = database / f"{package}.lst.gz"
        if not listing.is_file():
            continue
        with gzip.open(listing, "rt", encoding="utf-8", errors="strict") as stream:
            for line in stream:
                relative = line.strip().replace("\\", "/").lstrip("/")
                if relative.startswith("./"):
                    relative = relative[2:]
                directory, _, basename = relative.rpartition("/")
                name = basename.lower()
                if directory not in {"bin", "usr/bin"} or name not in required:
                    continue
                if name in providers and providers[name] != {**record, "evidence": "setup-installed-db"}:
                    raise ValueError(f"Ambiguous Setup ownership for {name}")
                providers[name] = {**record, "evidence": "setup-installed-db"}
    return providers


def identify_providers(manifest, historical, overlay, root):
    required = {
        PurePosixPath(entry["path"]).name.lower(): entry["sha256"].lower()
        for entry in manifest["files"]
        if entry["origin"] == "cygwin"
    }
    providers = {}
    # Overlay order matches the extraction order; these archives bypass Setup.
    for path, record in overlay.items():
        with tarfile.open(path, "r:*") as archive:
            for member in archive:
                relative = member.name.removeprefix("./")
                directory, _, basename = relative.rpartition("/")
                name = basename.lower()
                if directory not in {"bin", "usr/bin"} or name not in required:
                    continue
                if not member.isfile():
                    raise ValueError(f"Unsupported overlay DLL member: {member.name}")
                with archive.extractfile(member) as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
                providers[name] = ({**record, "evidence": "overlay-dll-sha256"}, digest)
    # Do not attribute an overwritten DLL to the historical package.
    for name, (_, digest) in providers.items():
        if digest != required[name]:
            raise ValueError(f"Overlay DLL differs from compiled manifest: {name}")
    result = {name: record for name, (record, _) in providers.items()}
    result.update(setup_providers(root, historical, required.keys() - result.keys()))
    missing = sorted(required.keys() - result.keys())
    if missing:
        raise ValueError(f"No fixed package owner for {missing}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "historical", "overlay", "lock", "root", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    providers = identify_providers(manifest, historical_archives(args.historical),
                                   overlay_archives(args.overlay, args.lock), args.root)
    packages = {
        (record["package"], record["archive"]): record
        for record in providers.values()
    }
    result = {
        "status": "direct-runtime-providers-not-complete-setup-closure",
        "samba_version": manifest["samba_version"],
        "cygwin_runtime": manifest["cygwin_runtime"],
        "dll_providers": dict(sorted(providers.items())),
        "packages": [packages[key] for key in sorted(packages)],
    }
    if args.expected and result != json.loads(args.expected.read_text(encoding="utf-8")):
        raise ValueError("Reinstalled runtime package provenance differs from original build")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Matched {len(providers)} DLLs to {len(packages)} runtime packages")
    for record in result["packages"]:
        print(f'{record["package"]}: {record["archive"]}')


if __name__ == "__main__":
    main()
