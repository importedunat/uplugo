# SPDX-License-Identifier: GPL-3.0-only
"""Recoverable, per-account migration to an already installed native package.

Whole legacy objects are renamed to adjacent private archives, never deleted or
executed. Adjacent archives preserve atomic moves across separate XDG filesystems.
The journal identifies inodes, not administrator-controlled or arbitrary paths.
"""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid
from maintenance import Locations, no_links, installation_lock, require_stopped, running_app, create_directory
from install_transaction import atomic_write, sync_dir
from deployment import inspect_deployment
from session import systemd_available, UNIT
from i18n import _
from dualsense import xdg_directory

JOURNAL='.migration-pending.json'
PREFIX='.dualsense-usb-before-system-'
ENABLE=re.compile(r'[A-Za-z0-9_.@:\-]+\.(?:wants|requires)')
DATA_NAMES=('controllers.json','battery-readings.json','charge-history.json')


def roots(loc):return {'data':str(loc.data),'config':str(loc.config),'state':str(xdg_directory('XDG_STATE_HOME','.local/state').resolve())}


def data_target(loc,name):
    if name not in DATA_NAMES:raise ValueError(_('O registro de migração está inválido. Nenhum arquivo foi removido.'))
    root=loc.config if name=='controllers.json' else Path(roots(loc)['state'])
    path=root/'dualsense-usb'/name;no_links(path,root);return path


def data_bytes(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>8*1024*1024:
            raise ValueError(_('Um arquivo de dados antigo precisa ser conferido antes da migração.')+'\n'+str(path))
        value=stream.read(8*1024*1024+1)
    if len(value)>8*1024*1024:raise ValueError(_('Um arquivo de dados antigo precisa ser conferido antes da migração.'))
    return value


def import_plan(loc):
    imports={}
    for name in DATA_NAMES:
        target=data_target(loc,name);source=loc.app/name
        if target.exists() or target.is_symlink() or not (source.exists() or source.is_symlink()):continue
        value=data_bytes(source)
        try:json.loads(value)
        except ValueError as exc:raise ValueError(_('Um arquivo de dados antigo precisa ser conferido antes da migração.')+'\n'+str(source)) from exc
        imports[name]={'sha256':hashlib.sha256(value).hexdigest(),'size':len(value)}
    return imports


def checkpoint(name):
    """Fault-injection seam for isolated tests, never a CLI/environment switch."""


def program_paths(loc):
    paths={'app':loc.app,'receipt':loc.receipt,'desktop':loc.target('desktop'),
           'icon':loc.target('icon'),'service':loc.target('service'),
           'overrides':loc.target('service').with_name(UNIT+'.d')}
    parent=loc.target('service').parent
    no_links(parent,loc.config)
    if parent.is_dir():
        for directory in parent.iterdir():
            if ENABLE.fullmatch(directory.name):
                path=directory/UNIT
                if path.exists() or path.is_symlink():paths['enable/'+directory.name]=path
    return paths


def path_for(loc,key):
    if key in ('app','receipt','desktop','icon','service','overrides'):
        return {'app':loc.app,'receipt':loc.receipt,'desktop':loc.target('desktop'),
                'icon':loc.target('icon'),'service':loc.target('service'),
                'overrides':loc.target('service').with_name(UNIT+'.d')}[key]
    if key.startswith('enable/') and ENABLE.fullmatch(key[7:]):
        return loc.target('service').parent/key[7:]/UNIT
    raise ValueError(_('O registro de migração contém um caminho inválido. Os arquivos foram preservados.'))


def anchor(loc,key):return loc.config if key in ('service','overrides') or key.startswith('enable/') else loc.data


def identity(path,allow_link=False):
    try:info=path.lstat()
    except FileNotFoundError:return None
    kind=stat.S_IFMT(info.st_mode)
    if info.st_uid!=os.getuid() or kind not in ((stat.S_IFREG,stat.S_IFDIR,stat.S_IFLNK) if allow_link else (stat.S_IFREG,stat.S_IFDIR)):
        raise ValueError(_('Há um arquivo de outra conta ou um link inesperado. Confira os detalhes antes de migrar.')+'\n'+str(path))
    return {'device':info.st_dev,'inode':info.st_ino,'kind':kind,'uid':info.st_uid}


def inspect_paths(loc):
    result={}
    for key,path in program_paths(loc).items():
        no_links(path.parent,anchor(loc,key))
        value=identity(path,allow_link=key.startswith('enable/'))
        if value is None:continue
        if key in ('app','overrides'):
            if value['kind']!=stat.S_IFDIR:raise ValueError(_('A pasta da instalação antiga tem um formato inesperado.')+'\n'+str(path))
        elif key.startswith('enable/'):
            if value['kind']!=stat.S_IFLNK or path.resolve()!=loc.target('service').resolve():
                raise ValueError(_('Um atalho de inicialização aponta para outro serviço. Ele foi preservado.')+'\n'+str(path))
        elif value['kind']!=stat.S_IFREG:
            raise ValueError(_('Um arquivo da instalação antiga tem um formato inesperado.')+'\n'+str(path))
        result[key]=value
    if len(result)>128:raise ValueError(_('Há muitos atalhos antigos. Confira a instalação antes de migrar.'))
    return result


def journal_path(loc):
    path=loc.base/JOURNAL;no_links(path,loc.data);return path


def read_journal(loc):
    path=journal_path(loc)
    if not path.exists():return None
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>128*1024:
            raise ValueError(_('O registro de migração está inválido. Nenhum arquivo foi removido.'))
        record=json.loads(stream.read(128*1024+1))
    if not isinstance(record,dict) or set(record)!={'format','id','roots','files','imports','phase','started'} or type(record['format']) is not int or record['format']!=1 or record['phase'] not in ('moving','archived') or not isinstance(record['id'],str) or not re.fullmatch('[0-9a-f]{32}',record['id']) or record['roots']!=roots(loc) or not isinstance(record['files'],dict) or not record['files'] or len(record['files'])>128 or type(record['started']) is not int or not isinstance(record['imports'],dict):
        raise ValueError(_('O registro de migração está inválido. Nenhum arquivo foi removido.'))
    for key,value in record['files'].items():
        path_for(loc,key)
        kind=stat.S_IFDIR if key in ('app','overrides') else (stat.S_IFLNK if key.startswith('enable/') else stat.S_IFREG)
        if not isinstance(value,dict) or set(value)!={'device','inode','kind','uid'} or any(type(x) is not int or x<0 for x in value.values()) or value['uid']!=os.getuid() or value['kind']!=kind:
            raise ValueError(_('O registro de migração está inválido. Nenhum arquivo foi removido.'))
    for name,value in record['imports'].items():
        data_target(loc,name)
        if not isinstance(value,dict) or set(value)!={'sha256','size'} or not isinstance(value['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',value['sha256']) or type(value['size']) is not int or not 0<=value['size']<=8*1024*1024:
            raise ValueError(_('O registro de migração está inválido. Nenhum arquivo foi removido.'))
    return record


def backup_for(loc,key,token):
    path=path_for(loc,key)
    return path.parent/(PREFIX+token)/path.name


def check_pair(loc,key,expected,token):
    source=path_for(loc,key);backup=backup_for(loc,key,token)
    no_links(source.parent,anchor(loc,key));no_links(backup.parent,anchor(loc,key))
    original=identity(source,allow_link=key.startswith('enable/'))
    saved=identity(backup,allow_link=key.startswith('enable/'))
    if (original==expected and saved is None) or (original is None and saved==expected):return original is None
    raise ValueError(_('Os arquivos mudaram desde o início da migração. As duas cópias foram preservadas; confira os detalhes.')+'\n'+str(source)+'\n'+str(backup))


def preview(loc):
    no_links(loc.base,loc.data)
    record=read_journal(loc)
    pending=loc.pending.exists() or loc.pending.is_symlink()
    installation_record=None
    if pending:
        no_links(loc.pending,loc.data)
        if record:raise ValueError(_('Há duas operações interrompidas. Confira os registros antes de continuar.'))
        from install_transaction import read_journal as read_installation
        installation_record=read_installation(loc)  # Validate and bind the preview to this operation.
    files=record['files'] if record else inspect_paths(loc)
    if record:
        for key,value in files.items():check_pair(loc,key,value,record['id'])
        unexpected=set(inspect_paths(loc))-set(files)
        if unexpected:raise ValueError(_('Surgiram novos arquivos da instalação antiga. Verifique novamente antes de continuar.'))
    imports=record['imports'] if record else ({} if pending else import_plan(loc))
    if record:
        for name,expected in imports.items():
            target=data_target(loc,name)
            if target.exists() and hashlib.sha256(data_bytes(target)).hexdigest()!=expected['sha256']:
                raise ValueError(_('Os dados de destino mudaram durante a migração. As duas versões foram preservadas.')+'\n'+str(target))
    data={'record':record,'files':files,'imports':imports,'installation_pending':installation_record}
    token=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return {'action':'recover_legacy' if pending else ('resume_migration' if record else ('migrate' if files else '')),
            'token':token,'files':[str(path_for(loc,key)) for key in files],
            'backups':[str(backup_for(loc,key,record['id'])) for key in files] if record else [],'record':record,'identities':files,'imports':imports,
            'data_imports':[str(data_target(loc,name)) for name in imports]}


def require_idle(loc,source):
    require_stopped(loc)
    if running_app(loc,directory=source):raise RuntimeError(_('Encerre o app antes de migrar a instalação.'))
    if systemd_available():
        result=subprocess.run(['systemctl','--user','show',UNIT,'--property=ActiveState','--property=FragmentPath'],check=True,capture_output=True,text=True,timeout=10)
        data=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        if data.get('ActiveState') in ('active','activating','deactivating','reloading'):
            raise RuntimeError(_('O serviço antigo ainda está ativo. Encerre o app pela bandeja e verifique novamente.'))
        if data.get('FragmentPath') and data['FragmentPath']!=str(loc.target('service')):
            raise RuntimeError(_('O serviço antigo pertence a outra instalação. Confira sua configuração antes de migrar.'))


def move_no_replace(source,destination):
    libc=ctypes.CDLL(None,use_errno=True);call=getattr(libc,'renameat2',None)
    if call is None:raise OSError(errno.ENOSYS,_('O sistema não oferece a movimentação atômica necessária para migrar.'))
    call.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];call.restype=ctypes.c_int
    if call(-100,os.fsencode(source),-100,os.fsencode(destination),1):
        error=ctypes.get_errno();raise OSError(error,os.strerror(error),str(source))


def save_record(loc,record):
    atomic_write(journal_path(loc),(json.dumps(record,sort_keys=True)+'\n').encode(),record['id'])


def import_data(loc,record):
    for name,expected in record['imports'].items():
        target=data_target(loc,name)
        source=(loc.app if loc.app.exists() else backup_for(loc,'app',record['id']))/name
        value=data_bytes(source)
        if hashlib.sha256(value).hexdigest()!=expected['sha256']:
            raise ValueError(_('Os dados antigos mudaram durante a migração. Verifique os arquivos antes de continuar.'))
        temporary=target.parent/('.dualsense-migration-'+record['id']+'-'+name)
        if temporary.exists() or temporary.is_symlink():
            if data_bytes(temporary)!=value:raise ValueError(_('A cópia temporária dos dados foi alterada e será preservada.'))
        if target.exists() or target.is_symlink():
            if data_bytes(target)!=value:raise ValueError(_('Os dados de destino mudaram durante a migração. As duas versões foram preservadas.'))
        else:
            atomic_write(temporary,value,record['id']);checkpoint('staged-data-'+name)
            move_no_replace(temporary,target);sync_dir(target.parent);checkpoint('imported-'+name)
        if temporary.exists():temporary.unlink();sync_dir(target.parent)


def migrate(source,loc,expected_token):
    if os.geteuid()==0:raise ValueError(_('Abra o assistente como seu usuário, sem sudo.'))
    if not inspect_deployment(source).system:raise ValueError(_('Abra a migração pelo assistente da versão instalada pelo sistema.'))
    with installation_lock(loc,allow_migration=True):
        require_idle(loc,source)
        plan=preview(loc)
        if not expected_token or plan['token']!=expected_token:
            raise RuntimeError(_('A prévia mudou. Clique em Verificar novamente antes de migrar.'))
        if plan['action']=='recover_legacy':
            from install_transaction import recover
            recover(loc)
            if systemd_available():subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=10)
            return {'recovered':True,'backups':[]}
        if not plan['action']:return {'recovered':False,'backups':[]}
        record=plan['record'] or {'format':1,'id':uuid.uuid4().hex,'phase':'moving','started':int(time.time()),
                                 'roots':roots(loc),'files':plan['identities'],'imports':plan['imports']}
        if plan['record'] is None:save_record(loc,record);checkpoint('journal')
        import_data(loc,record)
        for key,value in record['files'].items():
            if check_pair(loc,key,value,record['id']):continue
            path=path_for(loc,key);backup=backup_for(loc,key,record['id'])
            create_directory(backup.parent)
            info=backup.parent.stat()
            if info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError(_('A pasta da cópia anterior tem permissões inesperadas.'))
            check_pair(loc,key,value,record['id'])
            move_no_replace(path,backup);sync_dir(path.parent);sync_dir(backup.parent)
            checkpoint('moved-'+key)
        require_idle(loc,source)
        for key,value in record['files'].items():
            if not check_pair(loc,key,value,record['id']):raise RuntimeError(_('A migração ainda precisa ser concluída.'))
        if inspect_paths(loc):raise RuntimeError(_('Surgiram novos arquivos da instalação antiga. Verifique novamente antes de continuar.'))
        if systemd_available():subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=10)
        checkpoint('reloaded')
        record['phase']='archived';save_record(loc,record);checkpoint('archived')
        history=loc.base/'migrations'/ (record['id']+'.json');no_links(history,loc.data)
        data=(json.dumps(record,sort_keys=True)+'\n').encode()
        if history.exists():
            info=history.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>128*1024 or history.read_bytes()!=data:
                raise ValueError(_('O registro da cópia anterior foi alterado e será preservado.'))
        atomic_write(history,data,record['id']);checkpoint('history')
        journal_path(loc).unlink();sync_dir(loc.base);checkpoint('finished')
        return {'recovered':False,'backups':[str(backup_for(loc,key,record['id'])) for key in record['files']]}
