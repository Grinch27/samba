#!/usr/bin/env python3
# 待确认：Cygwin 历史包的符号链接及硬链接能否被 Windows 原生 Python 直接复原。
# 歧义：历史 Cygwin 打包方式与 Windows 系统符号链接语义不完全一致。
# 后续研究：针对 crypto-policies 及其余归档记录每包实际结果。
# 潜在优化：可考虑并行解压但须评估目录冲突，当前保持顺序。
# 风险：归档来自可信固定索引，但仍禁止绝对路径和逃逸链接。
# 验证重点：解包超时、路径安全、文件可读性以及 Bash 能启动。
"""Extract vetted Cygwin .tar.xz/.gz/.bz2 archives on Windows without bsdtar."""

import argparse
from pathlib import Path
import tarfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    with tarfile.open(args.archive, 'r:*') as archive:
        archive.extractall(args.destination, filter='data')


if __name__ == '__main__':
    main()
