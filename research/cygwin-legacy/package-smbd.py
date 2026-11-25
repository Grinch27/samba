#!/usr/bin/env python3
# 待确认：延迟加载和按需载入的 VFS 模块是否需要额外归档。
# 歧义：Windows Server 2022 的系统 DLL 不代表 Win7 SP1 完全兼容。
# 后续研究：Win7 实机运行、NTFS 账户隔离、依赖许可证及对应源码。
# 潜在优化：完成构建后再对打包大小、动态模块选取进行精简。
# 风险：不得将 Actions 实验包误认为已完成 Win7 验收的正式 Release。
# 验证重点：三个可执行文件、Cygwin 递归 DLL 依赖、缺失文件与哈希。
"""Stage all three Samba programs plus their recursive cygcheck DLL dependencies."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

BINARIES = ("smbd.exe", "testparm.exe", "smbpasswd.exe", "smbcontrol.exe")
DLL_PATH = re.compile(r"^\s*(?:[A-Za-z]:[\\/]|/).+?\.dll\s*$", re.I)
ERROR = re.compile(r"(?:could not find|not found|error:|cannot find)", re.I)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def executable_paths(source: Path) -> dict[str, Path]:
    bin_dir = source / "bin"
    if not bin_dir.is_dir():
        raise ValueError(f"Samba build output not found: {bin_dir}")
    result = {}
    for name in BINARIES:
        matches = sorted({p.resolve() for p in bin_dir.rglob(name) if p.is_file()})
        if len(matches) != 1:
            raise ValueError(f"Expected one {name}, found {len(matches)}: {matches}")
        result[name] = matches[0]
    return result


def dependencies(cygcheck: Path, binary: Path, cygwin_root: Path, source: Path) -> tuple[set[Path], set[str]]:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join((str(cygwin_root / "bin"), str(source / "bin"), str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]))
    result = subprocess.run([str(cygcheck), str(binary)], capture_output=True, text=True,
                            errors="replace", env=env, timeout=90, check=False)
    if result.returncode != 0 or ERROR.search(result.stderr) or ERROR.search(result.stdout):
        raise RuntimeError(f"cygcheck failed for {binary.name}: {result.stdout}\n{result.stderr}")
    libraries = set()
    windows_os = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not DLL_PATH.fullmatch(line):
            continue
        path = Path(line).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"cygcheck dependency absent: {path}")
        if inside(path, cygwin_root) or inside(path, source / "bin"):
            libraries.add(path)
        elif os.name == "nt" and inside(path, Path(os.environ["SystemRoot"]).resolve()):
            windows_os.add(path.name)
        else:
            raise RuntimeError(f"Unexpected non-system DLL path {path} (for {binary.name})")
    if not any(p.name.lower() == "cygwin1.dll" for p in libraries):
        raise RuntimeError(f"cygwin1.dll missing from recursive dependency output for {binary.name}")
    return libraries, windows_os


def create_package(source: Path, cygwin_root: Path, output: Path) -> dict:
    source = source.resolve(strict=True)
    cygwin_root = cygwin_root.resolve(strict=True)
    paths = executable_paths(source)
    cygcheck = cygwin_root / "bin" / "cygcheck.exe"
    if not cygcheck.is_file():
        raise FileNotFoundError(f"Missing dependency inspector: {cygcheck}")
    roots = set(paths.values())
    dlls = set()
    os_dependencies = set()
    for binary in paths.values():
        found, external = dependencies(cygcheck, binary, cygwin_root, source)
        dlls.update(found)
        os_dependencies.update(external)
    output.mkdir(parents=True, exist_ok=False)
    bin_dir = output / "bin"
    bin_dir.mkdir()
    manifest = {"status": "experimental-not-win7-validated", "samba_version": os.environ["SAMBA_VERSION"],
                "cygwin_runtime": "3.4.10", "protocol_min": "SMB2_10",
                "protocol_max": "SMB3_11", "signing": "mandatory",
                "ntlm_auth": "ntlmv2-only", "smb_encryption": "if_required",
                "windows_system_dlls_not_bundled": sorted(os_dependencies), "files": []}
    placed = {}
    for file in sorted(roots | dlls):
        name = file.name.lower()
        digest = hash_file(file)
        if name in placed:
            if placed[name] != digest:
                raise ValueError(f"DLL basename collision with different bytes: {file.name}")
            continue
        placed[name] = digest
        destination = bin_dir / file.name
        shutil.copy2(file, destination)
        manifest["files"].append({"path": f"bin/{file.name}", "sha256": digest,
                                  "origin": "cygwin" if inside(file, cygwin_root) else "samba",
                                  "bytes": destination.stat().st_size})
    for name in BINARIES:
        if not (bin_dir / name).is_file():
            raise RuntimeError(f"Required executable not staged: {name}")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(
        "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in manifest["files"]), encoding="utf-8")
    (output / "README.txt").write_text(
        f"Samba {manifest['samba_version']} / Cygwin 3.4.10 x64 RESEARCH ARTIFACT\n"
        "This is an authorized experimental preview candidate, not a verified Win7 runtime or installer.\n"
        "Executables: bin/smbd.exe, bin/testparm.exe, bin/smbpasswd.exe, bin/smbcontrol.exe\n"
        "SMB2_10..SMB3_11; NTLMv2 user authentication; mandatory signing.\n"
        "SMB3 encryption is negotiable and not mandatory (server smb encrypt = if_required).\n"
        "Windows system DLLs and dynamically loaded modules may require separate validation.\n"
        "Use only for testing until Win7 service, NTFS access control and DLL/Win7 imports\n"
        "are validated. Corresponding source is supplied as a separate ZIP.\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cygwin-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = create_package(args.source_root, args.cygwin_root, args.output)
    print(f"Prepared {len(manifest['files'])} binaries with SHA256SUMS", flush=True)


if __name__ == "__main__":
    main()
