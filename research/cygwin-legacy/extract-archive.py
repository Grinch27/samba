#!/usr/bin/env python3
# 待确认：所有 Cygwin 包的绝对符号链接是否都指向归档根目录内部。
# 歧义：旧版 Cygwin 原生符号链接可能采用不同 NTFS 映射方式。
# 后续研究：在 Win7 VM 核对解包后的链接及 DLL 的运行加载。
# 潜在优化：冷构建稳定后再优化逐包提取次数。
# 风险：只允许安全地重新映射归档内部的绝对符号链接，禁止目录逃逸。
# 验证重点：历史 .tar.xz 的路径安全、绝对符号链接及工具链启动。
"""Extract hash-verified Cygwin archives with safe absolute-link remapping."""

import argparse
import posixpath
from pathlib import Path, PurePosixPath
import tarfile


def safe_member(member, destination):
    parts = PurePosixPath(member.name).parts
    # Windows cannot represent certain Unix manual filenames such as ":.1.gz".
    # Documentation trees are not required for Samba build dependencies.
    if parts[:3] in {("usr", "share", "man"), ("usr", "share", "info"),
                     ("usr", "share", "doc")}:
        return None
    if member.issym() or member.islnk():
        target = member.linkname
        if target.startswith('/'):
            target_path = PurePosixPath(target.lstrip('/'))
            if '..' in target_path.parts or not target_path.parts:
                raise ValueError(f'Unsafe absolute archive link: {member.name} -> {target}')
            if member.issym():
                # A Cygwin /usr/... target refers to this extracted sysroot, not the host /usr.
                member.linkname = posixpath.relpath(target_path.as_posix(),
                                                    posixpath.dirname(member.name))
            else:
                member.linkname = target_path.as_posix()
    return tarfile.data_filter(member, destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    with tarfile.open(args.archive, 'r:*') as archive:
        archive.extractall(args.destination, filter=safe_member)


if __name__ == '__main__':
    main()
