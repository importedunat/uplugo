#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only check that Git will publish the reviewed source inventory.

This checks paths, file types and bytes in the index, not secrets, licenses,
commit history, remote state or the correctness of the application.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from distribution import inventory, safe_name, source_file

MAX_BLOB = 8 * 1024 * 1024


def audit(root):
    root = Path(root).resolve()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), timeout=15).stdout
    if Path(os.fsdecode(git('rev-parse', '--show-toplevel')).strip()).resolve() != root:
        raise ValueError('Run this check at the application repository root, not in a parent repository.')
    manifest = inventory(root)
    expected = set(manifest['runtime'] + manifest['development'])
    entries = {}
    unsafe, unsupported = set(), set()
    for raw in git('ls-files', '--stage', '-z').split(b'\0'):
        if not raw:continue
        metadata, raw_name = raw.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        name = os.fsdecode(raw_name)
        entries[name] = oid
        try:safe_name(name)
        except ValueError:unsafe.add(name)
        if mode not in {'100644', '100755'} or stage != '0':unsupported.add(name)
    different, unavailable = [], []
    for name in sorted(expected & entries.keys() - unsafe - unsupported):
        try:
            path = source_file(root, name)
            size = int(git('cat-file', '-s', entries[name]))
            if size > MAX_BLOB or path.stat().st_size > MAX_BLOB:
                unavailable.append(name);continue
            if git('cat-file', 'blob', entries[name]) != path.read_bytes():different.append(name)
        except (OSError, ValueError, subprocess.CalledProcessError):unavailable.append(name)
    report = dict(expected_files=len(expected), indexed_files=len(entries),
                  missing_from_index=sorted(expected - entries.keys()),
                  outdated_in_index=different,
                  unexpected_indexed=sorted(entries.keys() - expected),
                  unsafe_indexed_paths=sorted(unsafe), unsupported_index_entries=sorted(unsupported),
                  unreadable_or_oversized=unavailable)
    report['ok'] = not any(value for value in report.values() if isinstance(value, list))
    report['scope'] = 'Git index paths, file types and bytes only; no staging, commits, uploads or secret/license scan.'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:result = audit(args.root)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Git stderr may expose configuration/remote URLs. A category is enough.
        print(json.dumps({'ok':False, 'error':type(exc).__name__,
                          'hint':'Check the repository root, Git installation and distribution inventory.'}, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':raise SystemExit(main())
