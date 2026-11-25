#!/usr/bin/env python3
# 待确认：旧 ABI 的工具链、动态加载与 Win7 实机兼容性。
# 歧义：Server 2022 通过不等于 Win7 通过。
# 后续研究：Win7 双账户 NTFS ACL 和运行时模块。
# 潜在优化：成功冷构建后优化缓存。
# 风险：必须校验历史索引、包和对应源码；不发布缺件产物。
# 验证重点：三工具、DLL 来源、隔离启动和 ZIP 完整性。
"""Collect byte-matched corresponding Cygwin sources and exact Samba build inputs."""

import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
from urllib.request import urlopen
import zipfile

HISTORICAL = "http://ctm.crouchingtigerhiddenfruitbat.org/pub/cygwin/circa/64bit/2024/01/30/231215/"
MODERN = "https://mirrors.kernel.org/sourceware/cygwin/"
INDEX_SHA256 = "4bbf34f9922a2360b6bec9a149efad59a5fda5d33de5a28990c7480286dbf46d"
FIELD = re.compile(r"^(install|source):\s+(\S+)\s+(\d+)\s+([0-9a-fA-F]{128})\s*$")
SUFFIXES = (".tar.xz", ".tar.zst", ".tar.gz", ".tar.bz2")

def sha(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()

def records(data, base):
    result = {}
    record = {}
    def finish():
        if "install" in record and "source" in record:
            binary, _, checksum = record["install"]
            result[(binary, checksum)] = (base, *record["source"])
    for line in data.decode("utf-8").splitlines():
        if line.startswith(("@ ", "Package: ", "version:", "[")):
            finish()
            record = {}
        match = FIELD.fullmatch(line)
        if match:
            field, path, size, checksum = match.groups()
            record[field] = (path, int(size), checksum.lower())
    finish()
    return result

def collect_archives(args, needed):
    indexes = list(args.cache.rglob("setup.ini"))
    if len(indexes) != 1:
        raise ValueError("Expected exactly one verified historical index")
    index = indexes[0]
    data = index.read_bytes()
    if hashlib.sha256(data).hexdigest() != INDEX_SHA256:
        raise ValueError("Historical source index mismatch")
    historical = records(data, HISTORICAL)
    modern = {}
    overlay = {}
    for line in args.packages.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            url, _, checksum = line.split("\t")
            relative = url.split("/x86_64/", 1)[1]
            overlay[url.rsplit("/", 1)[1]] = ("x86_64/" + relative, checksum)
    if args.overlay.exists():
        with urlopen(MODERN + "x86_64/setup.xz", timeout=90) as response:
            modern = records(lzma.decompress(response.read()), MODERN)
    matches = {}
    archives = sorted(args.overlay.glob("*")) + sorted(args.cache.rglob("*"))
    for archive in archives:
        if not needed:
            break
        if not archive.is_file() or not archive.name.endswith(SUFFIXES):
            continue
        if archive.parent == args.overlay:
            key = overlay[archive.name]
            lookup = modern
        else:
            key = (archive.relative_to(index.parent.parent).as_posix(),
                   sha(archive, "sha512"))
            lookup = historical
        with tarfile.open(archive, "r:*") as source:
            for member in source:
                name = PurePosixPath(member.name).name.lower()
                if name not in needed or not member.isfile():
                    continue
                with source.extractfile(member) as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != needed[name]:
                    continue
                if key not in lookup:
                    raise ValueError(f"Exact source metadata not available: {archive.name} / {name}")
                matches[name] = (archive.name, lookup[key])
                del needed[name]
    if needed:
        raise ValueError(f"No byte-matched source package for: {sorted(needed)}")
    return matches

def download_source(record, directory):
    base, relative, size, checksum = record
    path = PurePosixPath(relative)
    if not path.parts or path.parts[0] not in {"x86_64", "noarch"} or ".." in path.parts:
        raise ValueError(f"Invalid source path: {relative}")
    target = directory / path.name
    if not target.exists():
        with urlopen(base + relative, timeout=120) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out)
    if target.stat().st_size != size or sha(target, "sha512") != checksum:
        raise ValueError(f"Source checksum mismatch: {relative}")
    return target.name

def main():
    p = argparse.ArgumentParser()
    for name in ("cache", "overlay", "packages", "samba", "project", "package", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.package / "manifest.json").read_text(encoding="utf-8"))
    needed = {Path(f["path"]).name.lower(): f["sha256"] for f in manifest["files"]
              if f["origin"] == "cygwin"}
    matches = collect_archives(args, needed)
    sources = args.output / "sources"
    sources.mkdir()
    source_map = {}
    for name, (binary, record) in sorted(matches.items()):
        source_map[name] = {"binary_package": binary, "source": download_source(record, sources),
                            "source_url": record[0] + record[1], "sha512": record[3]}
    # Git archive contains exact pristine Samba sources; repository archive contains
    # the applied patch and full build instructions at the actual triggering revision.
    for repo, filename in ((args.samba, "samba-upstream.tar.gz"),
                           (args.project, "build-project.tar.gz")):
        subprocess.run(["git", "-C", str(repo), "archive", "--format=tar.gz",
                        "-o", str(sources / filename), "HEAD"], check=True)
    shutil.copy2(args.samba / "COPYING", args.package / "COPYING-Samba")
    (args.package / "SOURCE-MANIFEST.json").write_text(
        json.dumps({"cygwin_dll_sources": source_map,
                    "samba_commit": subprocess.check_output(["git", "-C", str(args.samba),
                        "rev-parse", "HEAD"], text=True).strip(),
                    "source_asset": "samba-corresponding-source.zip"}, indent=2) + "\n",
        encoding="utf-8")
    (args.package / "LICENSES.txt").write_text(
        "Samba: see COPYING-Samba. Cygwin and other libraries retain their own licenses.\n"
        "The corresponding-source ZIP contains the original source packages, build recipes,\n"
        "patches and license materials; see SOURCE-MANIFEST.json for the DLL mapping.\n"
        "No full independent license audit or Windows 7 runtime verification is claimed.\n",
        encoding="utf-8")
    for directory, name in ((sources, "samba-corresponding-source.zip"),
                            (args.package, f"samba-{manifest['samba_version']}-cygwin-3.4.10-x64.zip")):
        with zipfile.ZipFile(args.output / name, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for file in sorted(directory.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(directory))
    shutil.rmtree(sources)
    assets = sorted(args.output.glob("*.zip"))
    (args.output / "SHA256SUMS").write_text(
        "".join(f"{sha(file)}  {file.name}\n" for file in assets), encoding="utf-8")
    print("Source correspondence and both ZIP assets complete", flush=True)

if __name__ == "__main__":
    main()
