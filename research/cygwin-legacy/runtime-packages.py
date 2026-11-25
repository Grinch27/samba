#!/usr/bin/env python3
# 待确认：运行时包的递归依赖、按需加载模块、Base 集合是否无 Python。
# 歧义：递归 PE 导入提供者集合不等于完整 Setup 安装依赖闭包。
# 后续研究：对应源码、版本约束、postinstall 及 Win7 实际加载。
# 潜在优化：只读取匹配目标 DLL 的内容；复用已有 manifest 和归档锁。
# 风险：现代覆盖包与历史包可能包含相同 DLL 名称，必须匹配实际字节。
# 验证重点：四工具已有 manifest 的每个 Cygwin DLL 对应唯一固定归档。
"""Identify runtime DLL providers from previously verified build archives."""

import argparse
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


def identify_providers(manifest, archives):
    required = {
        PurePosixPath(entry["path"]).name.lower(): entry["sha256"].lower()
        for entry in manifest["files"]
        if entry["origin"] == "cygwin"
    }
    providers = {}
    # Overlay has precedence because these packages were extracted after Setup.
    for path, record in archives.items():
        if len(providers) == len(required):
            break
        with tarfile.open(path, "r:*") as archive:
            for member in archive:
                name = PurePosixPath(member.name).name.lower()
                if name not in required or name in providers or not member.isfile():
                    continue
                with archive.extractfile(member) as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
                if digest == required[name]:
                    providers[name] = record
    missing = sorted(required.keys() - providers.keys())
    if missing:
        raise ValueError(f"No byte-matched runtime archive for {missing}")
    return providers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "historical", "overlay", "lock", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    archives = overlay_archives(args.overlay, args.lock)
    archives.update(historical_archives(args.historical))
    providers = identify_providers(manifest, archives)
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
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Matched {len(providers)} DLLs to {len(packages)} runtime packages")
    for record in result["packages"]:
        print(f'{record["package"]}: {record["archive"]}')


if __name__ == "__main__":
    main()
