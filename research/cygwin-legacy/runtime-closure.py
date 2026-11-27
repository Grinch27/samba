#!/usr/bin/env python3
# 待确认：现代运行包依赖的版本约束是否可由 3.4.10 满足。
# 歧义：候选闭包不等于 Setup 已安装成功或 Win7 ABI 验收。
# 后续研究：生成 samba-win7 原生包、Setup 求解、动态模块、源码。
# 潜在优化：只处理选定记录，重用原始已验证归档。
# 风险：禁止静默替换固定包或移除版本约束；缺包时停止。
# 验证重点：Base、递归依赖、精确归档索引及 Python-free 候选。
"""Plan a version-pinned Cygwin runtime repository from verified inputs."""

import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re

INDEX_SHA256 = "4bbf34f9922a2360b6bec9a149efad59a5fda5d33de5a28990c7480286dbf46d"
ARCHIVE = re.compile(r"^(\S+)\s+(\d+)\s+([a-fA-F0-9]{128})$")
DEPENDENCY = re.compile(r"^([A-Za-z0-9_.+@-]+)(?:\s*\(([^)]+)\))?$")


def index_records(text, origin):
    versions = []
    package = None
    category = ""
    section = "curr"
    current = {}

    def flush():
        if package and "version" in current and "install" in current:
            match = ARCHIVE.fullmatch(current["install"])
            if not match:
                raise ValueError(f"Invalid archive metadata: {package}")
            relative, size, sha = match.groups()
            versions.append({
                "package": package, "version": current["version"],
                "archive": relative, "size": int(size), "sha512": sha.lower(),
                "category": category, "section": section, "origin": origin,
                "depends": current.get("depends2", current.get("depends",
                    ", ".join(current.get("requires", "").split()))),
                "provides": current.get("provides", ""),
            })

    for line in text.splitlines():
        if line.startswith("@ "):
            flush()
            package, category, section, current = line[2:].strip(), "", "curr", {}
        elif re.fullmatch(r"\[[A-Za-z0-9_-]+\]", line):
            flush()
            section, current = line[1:-1], {}
        elif line.startswith("category:"):
            category = line.partition(":")[2].strip()
        elif line.startswith("version:") and "version" in current:
            flush()
            current = {"version": line.partition(":")[2].strip()}
        elif package and ":" in line:
            field, _, value = line.partition(":")
            if field in {"version", "install", "requires", "depends", "depends2", "provides"}:
                current[field] = value.strip()
    flush()
    return versions


def dependencies(record):
    for item in record["depends"].split(","):
        item = item.strip()
        if not item:
            continue
        match = DEPENDENCY.fullmatch(item)
        if not match:
            raise ValueError(f"Unsupported dependency expression: {item}")
        yield match.group(1), match.group(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("historical", "modern", "providers", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    historical_bytes = args.historical.read_bytes()
    if hashlib.sha256(historical_bytes).hexdigest() != INDEX_SHA256:
        raise ValueError("Historical index differs from fixed build input")
    historical = index_records(historical_bytes.decode("utf-8"), "historical")
    modern = index_records(lzma.decompress(args.modern.read_bytes()).decode("utf-8"), "overlay")
    pins = json.loads(args.providers.read_text(encoding="utf-8"))["packages"]
    selected = {r["package"]: r for r in historical if r["section"] == "curr"}
    for pin in pins:
        records = modern if pin["origin"] == "overlay" else historical
        matches = [r for r in records if all(r[k] == pin[k] for k in
                   ("package", "archive", "size", "sha512"))]
        if len(matches) != 1:
            raise ValueError(f"Exact signed/locked metadata unavailable: {pin['archive']}")
        selected[pin["package"]] = matches[0]
    seeds = {r["package"] for r in historical
             if r["section"] == "curr" and "Base" in r["category"].split()}
    seeds.update(r["package"] for r in pins)
    seeds.update(("bash", "coreutils", "getent", "cygrunsrv"))
    pending = sorted(seeds)
    closure = {}
    constraints = []
    while pending:
        name = pending.pop()
        if name in closure or name == "_windows":
            continue
        if name not in selected:
            # Virtual names are recorded, not guessed from similarly named files.
            alternatives = [r["package"] for r in selected.values()
                            if name in {p.strip().split(" ", 1)[0]
                                        for p in r["provides"].split(",")}]
            if len(alternatives) != 1:
                raise ValueError(f"Unresolved dependency {name}: {alternatives}")
            pending.append(alternatives[0])
            continue
        record = selected[name]
        closure[name] = record
        for dependency, constraint in dependencies(record):
            if constraint:
                constraints.append({"package": name, "dependency": dependency,
                                    "constraint": constraint})
            pending.append(dependency)
    python_packages = sorted(name for name in closure
                             if re.match(r"^(python[0-9]*|libpython)", name))
    result = {
        "status": "candidate-name-closure-version-constraints-not-yet-solved",
        "seeds": sorted(seeds),
        "packages": [closure[name] for name in sorted(closure)],
        "version_constraints": constraints,
        "python_packages": python_packages,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Candidate closure: {len(closure)} packages; {len(constraints)} version constraints")
    print("Python packages:", python_packages)
    for name in sorted(closure):
        print(f"{name}: {closure[name]['version']}")
    if python_packages:
        raise ValueError("Candidate closure contains Python; investigate before packaging")


if __name__ == "__main__":
    main()
