# SPDX-License-Identifier: GPL-3.0-only
"""User installation ownership and locks. Never opens hardware or escalates."""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from dualsense import xdg_directory, write_json

GENERATED = ('install-access.py', 'remove-access.py')


class PendingInstallation(RuntimeError):
    def __init__(self):
        super().__init__('Há uma atualização interrompida. Recupere a instalação antes de abrir ou remover o app: python3 install.py --recover')


def create_directory(path):
    if path.exists():
        if not path.is_dir():raise ValueError('Destino não é um diretório: '+str(path))
        return
    create_directory(path.parent)
    path.mkdir(mode=0o700)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


@dataclass
class Locations:
    data: Path
    config: Path

    @classmethod
    def current(cls):
        return cls(xdg_directory('XDG_DATA_HOME','.local/share').resolve(),
                   xdg_directory('XDG_CONFIG_HOME','.config').resolve())

    @property
    def base(self):return self.data/'dualsense-usb'
    @property
    def app(self):return self.base/'app'
    @property
    def receipt(self):return self.base/'installation.json'
    @property
    def pending(self):return self.base/'.installation-pending.json'

    def target(self,key):
        fixed={'desktop':self.data/'applications/dualsense-usb.desktop',
               'icon':self.data/'icons/hicolor/scalable/apps/dualsense-usb.svg',
               'service':self.config/'systemd/user/dualsense-usb.service'}
        if key in fixed:return fixed[key]
        if not key.startswith('app/'):raise ValueError('Arquivo de instalação desconhecido: '+key)
        name=key[4:]
        if not name or any(p in ('','.','..') for p in name.split('/')) or '\\' in name or name.startswith('/'):
            raise ValueError('Caminho de instalação inválido.')
        return self.app/name


def no_links(path,anchor):
    """Configured XDG roots may be links; managed descendants must not be."""
    current=anchor
    for part in path.relative_to(anchor).parts:
        current=current/part
        if current.is_symlink():raise ValueError('Link inesperado na instalação: '+str(current))


@contextmanager
def installation_lock(locations=None,shared=False,allow_migration=False):
    locations=locations or Locations.current()
    no_links(locations.base,locations.data)
    create_directory(locations.base)
    fd=os.open(locations.base/'.installation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        if os.fstat(fd).st_uid!=os.getuid():raise ValueError('O bloqueio da instalação pertence a outra conta.')
        try:fcntl.flock(fd,(fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('O app ou outra operação de manutenção está em execução. Encerre pela bandeja e tente novamente.') from None
        if not allow_migration and ((locations.base/'.migration-pending.json').exists() or (locations.base/'.migration-pending.json').is_symlink()):
            from i18n import _
            raise RuntimeError(_('Uma migração foi interrompida. Abra o assistente da versão instalada pelo sistema para continuar.'))
        if shared and (locations.pending.exists() or locations.pending.is_symlink()):raise PendingInstallation()
        yield
    finally:os.close(fd)


def running_app(locations,proc=Path('/proc'),directory=None):
    """Also recognize older releases, which did not hold the maintenance lock."""
    expected=Path(directory if directory is not None else locations.app)/'window.py'
    found=[]
    for entry in proc.iterdir():
        if not entry.name.isdecimal():continue
        try:
            if entry.stat().st_uid!=os.getuid():continue
            args=(entry/'cmdline').read_bytes().split(b'\0')
            if not args or not Path(os.fsdecode(args[0])).name.startswith('python'):continue
            index=1
            while index<len(args) and args[index] in (b'-I',b'-B',b'-u',b'-E',b'-s',b'-S',b'-O',b'-OO'):index+=1
            if index>=len(args) or not args[index] or args[index].startswith(b'-'):continue
            script=Path(os.fsdecode(args[index]))
            if not script.is_absolute():script=(entry/'cwd').resolve()/script
            if script.resolve()==expected.resolve():found.append(int(entry.name))
        except (OSError,ValueError):continue
    return found


def require_stopped(locations):
    if running_app(locations):
        raise RuntimeError('Encerre o Uplugo pela bandeja antes de atualizar ou remover. Fechar a janela mantém o app aberto.')


def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''):digest.update(chunk)
    return digest.hexdigest()


def record_installation(locations,runtime,version):
    keys=['app/'+name for name in (*runtime,*GENERATED)]+['desktop','icon','service']
    files={}
    for key in keys:
        path=locations.target(key)
        anchor=locations.config if key=='service' else locations.data
        no_links(path,anchor)
        if not stat.S_ISREG(path.stat().st_mode):raise ValueError('Arquivo instalado inválido: '+key)
        files[key]=file_hash(path)
    no_links(locations.receipt,locations.data)
    write_json(locations.receipt,{'format':1,'version':version,'files':files})


def removal_plan(locations):
    if locations.pending.exists() or locations.pending.is_symlink():raise PendingInstallation()
    if not locations.receipt.exists():
        if locations.app.exists():
            raise ValueError('Esta instalação antiga não tem registro de arquivos. Encerre o app e execute o instalador atualizado antes de removê-la.')
        return {'remove':{},'preserve':{},'missing':[],'receipt':False}
    no_links(locations.receipt,locations.data)
    if locations.receipt.stat().st_size>128*1024:raise ValueError('Registro de instalação inválido.')
    record=json.loads(locations.receipt.read_text())
    if not isinstance(record,dict) or type(record.get('format')) is not int or record['format']!=1 or not isinstance(record.get('files'),dict):
        raise ValueError('Registro de instalação inválido.')
    remove={};preserve={};missing=[]
    for key,expected in record['files'].items():
        if not isinstance(key,str) or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
            raise ValueError('Registro de instalação inválido.')
        path=locations.target(key)
        try:no_links(path,locations.config if key=='service' else locations.data)
        except ValueError:preserve[key]='link';continue
        try:info=path.stat()
        except FileNotFoundError:missing.append(key);continue
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():preserve[key]='tipo ou proprietário diferente';continue
        if file_hash(path)!=expected:preserve[key]='modificado';continue
        remove[key]=expected
    return {'remove':remove,'preserve':preserve,'missing':missing,'receipt':True}


def remove_user_files(locations):
    """Caller holds the exclusive installation lock and has checked shutdown."""
    plan=removal_plan(locations)
    for key,expected in plan['remove'].items():
        path=locations.target(key)
        no_links(path,locations.config if key=='service' else locations.data)
        if file_hash(path)!=expected:raise ValueError('Arquivo mudou durante a remoção: '+key)
        path.unlink()
    # Only bytecode belonging to modules actually removed, never arbitrary data.
    cache=locations.app/'__pycache__'
    if cache.is_dir() and not cache.is_symlink():
        modules={Path(key[4:]).stem for key in plan['remove'] if key.startswith('app/') and key.count('/')==1 and key.endswith('.py')}
        for path in cache.iterdir():
            match=re.fullmatch(r'(.+)\.cpython-\d+(?:\.opt-[012])?\.pyc',path.name)
            if match and match[1] in modules and not path.is_symlink() and path.is_file() and path.stat().st_uid==os.getuid():path.unlink()
    # Do not remove unknown files, edited code, photos or preference directories.
    parents={locations.target(key).parent for key in plan['remove'] if key.startswith('app/')}
    parents.add(cache)
    for parent in list(parents):
        parents.update(p for p in parent.parents if p==locations.app or locations.app in p.parents)
    for parent in sorted(parents,key=lambda p:len(p.parts),reverse=True):
        try:parent.rmdir()
        except (FileNotFoundError,OSError):pass
    if plan['receipt'] and not plan['preserve']:locations.receipt.unlink()
    return plan
