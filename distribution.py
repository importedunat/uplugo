# SPDX-License-Identifier: GPL-3.0-only
"""Explicit distribution inventory shared by installer and source packaging."""
import json
from pathlib import Path, PurePosixPath
import re
import stat

BASE = Path(__file__).resolve().parent
MANIFEST = 'packaging/files.json'
PRIVATE_PARTS = {'.git', '__pycache__', '.venv', 'work', 'dist', '.preview',
                 'appearance-library', 'official'}
PRIVATE_NAMES = {'controllers.json', 'battery-readings.json', 'charge-history.json',
                 'install-access.py', 'remove-access.py', 'system-package.json', 'installation.json', '.installation-id', '.installation-pending.json', 'diagnostico-carga.txt'}


def safe_name(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',name):
        raise ValueError('Invalid distribution path: '+repr(name))
    # Inspect the original components: PurePosixPath silently collapses '.'.
    parts=tuple(name.split('/'))
    if any(p in {'.','..'} or p in PRIVATE_PARTS or p.startswith('.env') for p in parts):
        raise ValueError('Private or unsafe distribution path: '+name)
    if parts[-1] in PRIVATE_NAMES or name.endswith(('.pyc','.pyo','.log','.tmp')):
        raise ValueError('Generated or personal file in distribution: '+name)
    return name


def parse_manifest(data):
    if not isinstance(data,dict) or set(data)!={'format','runtime','development'} or type(data['format']) is not int or data['format']!=1:
        raise ValueError('Unsupported distribution inventory')
    found=set()
    for group in ('runtime','development'):
        names=data[group]
        if not isinstance(names,list) or not names:raise ValueError('Empty distribution group: '+group)
        for name in names:
            safe_name(name)
            if name=='RELEASE.json':raise ValueError('Reserved release record path')
            if name in found:raise ValueError('Duplicate distribution path: '+name)
            found.add(name)
    required={'install.py','app_info.py','distribution.py',MANIFEST,'build_helper.py',
              'packaging/install-access.py.in','LICENSE','THIRD_PARTY.md','README.md',
              'assets/dualsense-blueprint.LICENSE.txt','locales/en.json','locales/es.json'}
    # Format 1 also describes the earlier alpha.1 package. When maintenance is
    # present its runtime group must be complete, without rejecting old releases.
    maintenance={'uninstall.py','maintenance.py','access_admin.py','packaging/remove-access.py.in'}
    if maintenance & set(data['runtime']):required|=maintenance
    transaction={'install_transaction.py','recovery_ui.py'}
    if transaction & set(data['runtime']):required|=transaction|maintenance
    if not required<=set(data['runtime']):raise ValueError('Incomplete runtime inventory')
    if 'release.py' not in data['development']:raise ValueError('Missing source packaging tool')
    return data


def inventory(root=BASE):
    return parse_manifest(json.loads((Path(root)/MANIFEST).read_text(encoding='utf-8')))


def source_file(root,name):
    """Do not follow file or directory symlinks outside the reviewed inventory."""
    path=Path(root).resolve()
    parts=PurePosixPath(safe_name(name)).parts
    for part in parts:
        path=path/part
        if path.is_symlink():raise ValueError('Symlink in distribution: '+name)
    if not stat.S_ISREG(path.stat().st_mode):raise ValueError('Not a regular file: '+name)
    return path
