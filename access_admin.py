# SPDX-License-Identifier: GPL-3.0-only
"""Self-contained administrative install/removal logic, embedded by the builder.

Production entrypoints use root='/' and owner_uid=0. Alternate roots are only
an in-process test fixture; no target path is accepted from command-line input.
This code is never imported by the privileged controller helper.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile

ACCESS_PATHS = {
    'helper':'usr/local/libexec/dualsense-usb-helper',
    'policy':'usr/share/polkit-1/actions/org.local.dualsense.usb.policy',
    'rule':'etc/polkit-1/rules.d/49-dualsense-usb.rules',
    'udev':'etc/udev/rules.d/70-dualsense-usb-virtual.rules',
    'receipt':'var/lib/dualsense-usb/access.json',
}
ACCESS_POLICY = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN" "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">\n<policyconfig><action id="org.local.dualsense.usb"><description>Gerenciar Uplugo</description><message>Autorizar gerenciamento do DualSense</message><defaults><allow_any>no</allow_any><allow_inactive>no</allow_inactive><allow_active>auth_admin</allow_active></defaults><annotate key="org.freedesktop.policykit.exec.path">/usr/local/libexec/dualsense-usb-helper</annotate></action></policyconfig>\n'
ACCESS_UDEV = 'SUBSYSTEM=="hidraw", DEVPATH=="/devices/virtual/misc/uhid/0003:054C:0CE6.*/hidraw/hidraw*", MODE="0660", TAG+="uaccess"\nSUBSYSTEM=="hidraw", DEVPATH=="/devices/virtual/misc/uhid/0003:054C:0DF2.*/hidraw/hidraw*", MODE="0660", TAG+="uaccess"\n'


def access_rule(username):
    return 'polkit.addRule(function(action, subject) { if (action.id === "org.local.dualsense.usb" && subject.user === ' + json.dumps(username) + ' && subject.local && subject.active) { return polkit.Result.YES; } });\n'


def access_digest(data):return hashlib.sha256(data).hexdigest()


def access_actor():
    if os.geteuid()!=0:raise ValueError('Precisa de autorização administrativa.')
    value=os.environ.get('PKEXEC_UID','')
    if not re.fullmatch('[1-9][0-9]*',value):raise ValueError('Usuário inválido.')
    uid=int(value)
    return uid,pwd.getpwuid(uid).pw_name


def access_payloads(helper,username):
    return {'helper':(helper.encode(),0o755),'policy':(ACCESS_POLICY.encode(),0o644),
            'rule':(access_rule(username).encode(),0o644),'udev':(ACCESS_UDEV.encode(),0o644)}


class AccessFiles:
    def __init__(self,root=Path('/'),owner_uid=0,reload_rules=None,proc=Path('/proc')):
        self.root=Path(root);self.owner_uid=owner_uid;self.proc=proc
        self.reload_rules=reload_rules or self._reload

    def _reload(self):
        subprocess.run(['/usr/bin/udevadm','control','--reload-rules'],check=True,timeout=10)

    def path(self,name,create=False):
        current=self.root
        for part in Path(ACCESS_PATHS[name]).parent.parts:
            current=current/part
            try:info=current.lstat()
            except FileNotFoundError:
                if not create:return self.root/ACCESS_PATHS[name]
                current.mkdir(mode=0o755);info=current.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022:
                raise ValueError('Diretório administrativo sem proteção adequada: '+str(current))
        return self.root/ACCESS_PATHS[name]

    def read(self,name):
        path=self.path(name)
        try:info=path.lstat()
        except FileNotFoundError:return None
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022 or info.st_size>1024*1024:
            raise ValueError('Arquivo administrativo inesperado: '+str(path))
        return path.read_bytes(),stat.S_IMODE(info.st_mode)

    def write(self,name,data,mode):
        path=self.path(name,create=True)
        fd,temporary=tempfile.mkstemp(prefix='.dualsense-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(temporary,mode)
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)

    @contextmanager
    def lock(self):
        directory=self.path('receipt',create=True).parent
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Outra configuração do acesso USB está em execução.') from None
            yield
        finally:os.close(fd)

    def receipt(self):
        saved=self.read('receipt')
        if saved is None:return None
        record=json.loads(saved[0])
        if not isinstance(record,dict) or set(record)!={'format','owner_uid','files'} or type(record['format']) is not int or record['format']!=1:
            raise ValueError('Registro do acesso USB inválido.')
        if type(record['owner_uid']) is not int or record['owner_uid']<=0 or not isinstance(record['files'],dict) or set(record['files'])!=set(ACCESS_PATHS)-{'receipt'}:
            raise ValueError('Registro do acesso USB inválido.')
        if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in record['files'].values()):
            raise ValueError('Registro do acesso USB inválido.')
        return record

    def check_actor(self,actor,record):
        uid,username=actor
        if record is not None:
            if record['owner_uid']!=uid:raise ValueError('O acesso USB pertence a outra conta e não será alterado.')
        else:
            rule=self.read('rule')
            if rule is not None and rule[0]!=access_rule(username).encode():
                raise ValueError('A regra existente pertence a outra conta ou foi personalizada. Ela será preservada.')

    def rollback(self,snapshots):
        for name,saved in snapshots.items():
            if saved is not None:self.write(name,*saved)
            else:self.path(name).unlink(missing_ok=True)
        self.reload_rules()

    def install(self,helper,actor):
        with self.lock():
            record=self.receipt();self.check_actor(actor,record)
            snapshots={name:self.read(name) for name in ACCESS_PATHS}
            payloads=access_payloads(helper,actor[1])
            try:
                for name,(data,mode) in payloads.items():self.write(name,data,mode)
                self.reload_rules()
                record={'format':1,'owner_uid':actor[0],
                        'files':{name:access_digest(data) for name,(data,mode) in payloads.items()}}
                self.write('receipt',(json.dumps(record,sort_keys=True,indent=2)+'\n').encode(),0o600)
            except Exception as exc:
                try:self.rollback(snapshots)
                except Exception as rollback:raise RuntimeError('Configuração falhou; a restauração também precisa de atenção: '+str(rollback)) from exc
                raise RuntimeError('Configuração falhou; arquivos anteriores restaurados: '+str(exc)) from exc

    def remove(self,legacy_helper_hash,actor):
        with self.lock():
            record=self.receipt();self.check_actor(actor,record)
            snapshots={name:self.read(name) for name in ACCESS_PATHS}
            if record is None:
                expected={name:access_digest(data) for name,(data,mode) in access_payloads('',actor[1]).items()}
                expected['helper']=legacy_helper_hash
            else:expected=record['files']
            for name,hash_value in expected.items():
                if snapshots[name] is not None and access_digest(snapshots[name][0])!=hash_value:
                    raise ValueError('Arquivo do acesso USB modificado; nada foi removido: '+str(self.path(name)))
            helper=str(self.root/ACCESS_PATHS['helper']).encode()
            for entry in self.proc.iterdir():
                if not entry.name.isdecimal():continue
                try:args=(entry/'cmdline').read_bytes().split(b'\0')
                except (FileNotFoundError,ProcessLookupError):continue
                except PermissionError:raise ValueError('Não foi possível verificar as sessões USB em execução.') from None
                if helper in args:raise ValueError('Encerre as sessões do Uplugo antes de remover o acesso administrativo.')
            present=[name for name in expected if snapshots[name] is not None]
            try:
                for name in present:self.path(name).unlink()
                if present:self.reload_rules()
                self.path('receipt').unlink(missing_ok=True)
            except Exception as exc:
                try:self.rollback(snapshots)
                except Exception as rollback:raise RuntimeError('Remoção falhou; a restauração também precisa de atenção: '+str(rollback)) from exc
                raise RuntimeError('Remoção falhou; arquivos anteriores restaurados: '+str(exc)) from exc
            return present
