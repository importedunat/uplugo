# SPDX-License-Identifier: GPL-3.0-only
"""Recoverable user installation. Caller holds the exclusive maintenance lock.

No administrator files, controller settings or USB sessions are changed here.
The complete app directory is exchanged atomically on Linux; a durable journal
covers the menu entry, service, icon and receipt, including separate XDG disks.
"""
import ctypes
import errno
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import uuid
from maintenance import GENERATED, file_hash, no_links, removal_plan, create_directory

JOURNAL = '.installation-pending.json'
GENERATION = '.installation-id'
ALIASES = ('desktop', 'icon', 'service', 'receipt')


def checkpoint(name):
    """Fault-injection seam for process-kill tests; no environment backdoor."""


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def ordinary(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError('Arquivo de manutenção inválido: '+str(path))
    return info


def file_state(path):
    try: info = ordinary(path)
    except FileNotFoundError: return None
    return {'sha256': file_hash(path), 'mode': stat.S_IMODE(info.st_mode)}


def atomic_write(path, data, token, mode=0o600):
    create_directory(path.parent)
    temporary = path.with_name('.'+path.name+'.'+token+'.tmp')
    if temporary.exists() or temporary.is_symlink(): ordinary(temporary)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fchmod(stream.fileno(), mode); os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def exchange(first, second):
    libc = ctypes.CDLL(None, use_errno=True)
    call = getattr(libc, 'renameat2', None)
    if call is None:
        raise OSError(errno.ENOSYS, 'O sistema não oferece a troca atômica necessária para atualizar.')
    call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    call.restype = ctypes.c_int
    if call(-100, os.fsencode(first), -100, os.fsencode(second), 2):
        error = ctypes.get_errno()
        raise OSError(error, 'Não foi possível trocar a instalação de forma atômica: '+os.strerror(error))


def tree_state(root):
    if not root.exists(): return None
    if root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.getuid():
        raise ValueError('Diretório de instalação inválido: '+str(root))
    result = {}
    for directory, names, files in os.walk(root, followlinks=False):
        # Python can create these simply by importing the recovery command.
        names[:] = [name for name in names if name != '__pycache__']
        for name in [*names, *files]:
            path = Path(directory)/name
            if path.name == '__pycache__': continue
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if info.st_uid != os.getuid(): raise ValueError('Arquivo de outra conta: '+relative)
            if stat.S_ISLNK(info.st_mode): result[relative] = {'link': os.readlink(path)}
            elif stat.S_ISDIR(info.st_mode): result[relative] = {'directory': True}
            elif stat.S_ISREG(info.st_mode): result[relative] = file_state(path)
            else: raise ValueError('Tipo de arquivo não suportado na instalação: '+relative)
    return result


def sync_tree(root):
    directories = []
    for directory, names, files in os.walk(root, followlinks=False):
        directories.append(Path(directory))
        for name in files:
            path = Path(directory)/name
            if path.is_symlink(): continue
            ordinary(path)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try: os.fsync(fd)
            finally: os.close(fd)
    for directory in reversed(directories): sync_dir(directory)


def target(locations, alias):
    if alias not in ALIASES: raise ValueError('Destino de manutenção inválido.')
    path = locations.receipt if alias == 'receipt' else locations.target(alias)
    no_links(path, locations.config if alias == 'service' else locations.data)
    return path


def write_journal(locations, record):
    path = locations.base/JOURNAL
    no_links(path, locations.data)
    if path.exists(): ordinary(path)
    payload=(json.dumps(record, ensure_ascii=False, sort_keys=True)+'\n').encode()
    if len(payload)>4*1024*1024:raise ValueError('Registro de recuperação excessivo. Nenhum arquivo instalado será substituído.')
    atomic_write(path,payload,record['id'])


def read_journal(locations):
    path = locations.base/JOURNAL
    no_links(path, locations.data)
    if not path.exists(): return None
    if ordinary(path).st_size > 4*1024*1024: raise ValueError('Registro de recuperação excessivo.')
    record = json.loads(path.read_text())
    if (not isinstance(record, dict) or type(record.get('format')) is not int or record['format'] != 1
            or not isinstance(record.get('id'), str) or not re.fullmatch('[0-9a-f]{32}', record['id'])
            or record.get('phase') not in ('building', 'prepared', 'committed')
            or record.get('roots') != {'data': str(locations.data), 'config': str(locations.config)}):
        raise ValueError('Registro de recuperação inválido ou pertencente a outra instalação.')
    if record['phase'] != 'building':
        if ('old_tree' not in record or not isinstance(record.get('new_tree'), dict) or not record['new_tree']
                or (record.get('old_tree') is not None and not isinstance(record['old_tree'], dict))
                or not isinstance(record.get('files'), dict) or set(record['files']) != set(ALIASES)):
            raise ValueError('Registro de recuperação incompleto.')
        for value in record['files'].values():
            if not isinstance(value, dict) or set(value) != {'before', 'after'}:
                raise ValueError('Registro de recuperação incompleto.')
            for key, state in value.items():
                if key == 'before' and state is None: continue
                if (not isinstance(state, dict) or set(state) != {'sha256','mode'}
                        or not isinstance(state['sha256'], str) or not re.fullmatch('[0-9a-f]{64}',state['sha256'])
                        or type(state['mode']) is not int or not 0 <= state['mode'] <= 0o777):
                    raise ValueError('Registro de arquivos inválido.')
    return record


def bundle_path(locations, record):
    path = locations.base/('.installation-'+record['id'])
    no_links(path, locations.data)
    if path.exists():
        if not path.is_dir() or path.stat().st_uid != os.getuid():
            raise ValueError('Pasta de recuperação inválida.')
        contents = list(path.iterdir())
        if contents and record['phase']=='building' and {p.name for p in contents} <= {'.transaction-id'}:
            for item in contents:ordinary(item)
            return path
        if contents:
            marker = path/'.transaction-id'; ordinary(marker)
            if marker.read_text() != record['id']: raise ValueError('Pasta de recuperação não corresponde ao registro.')
    return path


def cleanup(locations, record):
    bundle = bundle_path(locations, record)
    if bundle.exists():
        # Remove the ownership marker last, so interrupted cleanup is repeatable.
        for path in bundle.iterdir():
            if path.name == '.transaction-id': continue
            if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
            else: path.unlink()
            checkpoint('cleanup-'+path.name)
        (bundle/'.transaction-id').unlink(missing_ok=True)
        bundle.rmdir(); sync_dir(locations.base); checkpoint('cleanup-bundle')
    for alias in ALIASES:
        path = target(locations, alias)
        temporary = path.with_name('.'+path.name+'.'+record['id']+'.tmp')
        if temporary.exists() or temporary.is_symlink():
            ordinary(temporary); temporary.unlink(); sync_dir(temporary.parent)
    (locations.base/JOURNAL).unlink(); sync_dir(locations.base)


def recover(locations):
    """Rollback an incomplete update, or finish cleanup of a committed one."""
    record = read_journal(locations)
    if record is None: return 'none'
    bundle = bundle_path(locations, record)
    if record['phase'] == 'building':
        cleanup(locations, record); return 'discarded'
    live, staged = tree_state(locations.app), tree_state(bundle/'app')
    before, after = record['old_tree'], record['new_tree']
    if record['phase'] == 'committed':
        if live != after: raise ValueError('A instalação mudou após a atualização. Os arquivos de recuperação foram preservados.')
        for alias in ALIASES:
            if file_state(target(locations, alias)) != record['files'][alias]['after']:
                raise ValueError('Arquivo instalado foi alterado: '+alias)
        cleanup(locations, record); return 'completed'
    if not ((live == before and staged == after) or (live == after and staged == before)):
        raise ValueError('Os arquivos mudaram desde a interrupção. A cópia anterior foi preservada para revisão.')
    # Validate every destination and backup before starting the rollback.
    for alias in ALIASES:
        state = record['files'][alias]
        if file_state(target(locations, alias)) not in (state['before'], state['after']):
            raise ValueError('Arquivo alterado durante a interrupção: '+alias)
        if file_state(bundle/'old'/alias) != state['before']:
            raise ValueError('Cópia de recuperação ausente ou alterada: '+alias)
    if live == after:
        if before is None: os.replace(locations.app, bundle/'app')
        else: exchange(locations.app, bundle/'app')
        sync_dir(locations.base); sync_dir(bundle)
    checkpoint('rollback-app')
    for alias in ALIASES:
        path, state = target(locations, alias), record['files'][alias]['before']
        if state is None:
            path.unlink(missing_ok=True)
            if path.parent.exists(): sync_dir(path.parent)
        else: atomic_write(path, (bundle/'old'/alias).read_bytes(), record['id'], state['mode'])
        checkpoint('rollback-'+alias)
    # The rollback is complete. A durable building record makes cleanup restartable
    # even after its now-unused backup files have been partially removed.
    record['phase'] = 'building'; write_journal(locations, record); checkpoint('rolled-back')
    cleanup(locations, record)
    return 'restored' if before is not None else 'removed'


def install_files(locations, sources, external, version):
    """Stage all runtime files and commit only after helper generation succeeds."""
    if read_journal(locations) is not None:
        raise RuntimeError('Há uma atualização interrompida. Execute python3 install.py --recover antes de tentar novamente.')
    if set(external) != set(ALIASES)-{'receipt'}: raise ValueError('Arquivos externos incompletos.')
    for name in [*sources, *GENERATED, GENERATION]:
        path = locations.target('app/'+name); no_links(path, locations.data)
        if path.exists(): ordinary(path)
    before = tree_state(locations.app)
    originals = {alias: file_state(target(locations, alias)) for alias in ALIASES}
    old_owned = removal_plan(locations)['remove'] if locations.receipt.exists() else {}
    record = {'format': 1, 'id': uuid.uuid4().hex, 'phase': 'building',
              'roots': {'data': str(locations.data), 'config': str(locations.config)}}
    write_journal(locations, record)
    bundle = locations.base/('.installation-'+record['id'])
    try:
        bundle.mkdir(mode=0o700); checkpoint('bundle-created')
        (bundle/'.transaction-id').write_text(record['id']); sync_tree(bundle); sync_dir(locations.base)
        checkpoint('building')
        app = bundle/'app'
        if locations.app.exists(): shutil.copytree(locations.app, app, symlinks=True)
        else: app.mkdir()
        for name, source in sources.items():
            destination = app/name; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        for key in old_owned:
            if key.startswith('app/') and key[4:] not in {*sources, *GENERATED, GENERATION}:
                (app/key[4:]).unlink(missing_ok=True)
        cache = app/'__pycache__'
        modules = {Path(key[4:]).stem for key in old_owned if key.startswith('app/') and key.count('/') == 1}
        modules |= {Path(name).stem for name in sources if '/' not in name and name.endswith('.py')}
        if cache.is_dir() and not cache.is_symlink():
            for path in cache.iterdir():
                match = re.fullmatch(r'(.+)\.cpython-\d+(?:\.opt-[012])?\.pyc', path.name)
                if match and match[1] in modules: path.unlink()
        subprocess.run(['/usr/bin/python3', str(app/'build_helper.py')], check=True, capture_output=True)
        (app/GENERATION).write_text(record['id'])
        new = bundle/'new'; old = bundle/'old'; new.mkdir(); old.mkdir()
        for alias, content in external.items(): (new/alias).write_bytes(content)
        files = {'app/'+name: file_hash(app/name) for name in [*sources, *GENERATED, GENERATION]}
        files.update({alias: file_hash(new/alias) for alias in external})
        (new/'receipt').write_text(json.dumps({'format':1, 'version':version, 'generation':record['id'], 'files':files}, indent=2)+'\n')
        for alias in ALIASES:
            (new/alias).chmod(0o600 if alias == 'receipt' else 0o644)
            if originals[alias] is not None: shutil.copy2(target(locations, alias), old/alias)
        sync_tree(bundle); sync_dir(locations.base)
        if tree_state(locations.app) != before or any(file_state(target(locations, alias)) != originals[alias] for alias in ALIASES):
            raise ValueError('A instalação mudou durante a preparação. Tente novamente com o app encerrado.')
        record.update(phase='prepared',old_tree=before,new_tree=tree_state(app),
                      files={alias:{'before':originals[alias],'after':file_state(new/alias)} for alias in ALIASES})
        write_journal(locations, record); checkpoint('prepared')
        if before is None: os.replace(app, locations.app)
        else: exchange(app, locations.app)
        sync_dir(locations.base); sync_dir(bundle); checkpoint('app')
        for alias in ALIASES:
            atomic_write(target(locations, alias), (new/alias).read_bytes(), record['id'], record['files'][alias]['after']['mode'])
            checkpoint(alias)
        record['phase'] = 'committed'; write_journal(locations, record); checkpoint('committed')
        cleanup(locations, record)
    except Exception:
        # On a recoverable I/O failure, restore before reporting failure. SIGKILL
        # and power loss leave the durable journal for the separate recovery step.
        recover(locations)
        raise
