# SPDX-License-Identifier: GPL-3.0-only
"""Read/hold an administrator-approved native grant. Embedded in the helper.

Only standard-library imports; no user-selected paths or identities in the
privileged entrypoint. Alternate roots/owners below are in-process test fixtures.
"""
from contextlib import contextmanager, ExitStack
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat

NATIVE_ACCESS_VERSION = 1
NATIVE_CONTROL_ACTION = 'org.local.dualsense.usb.native.control'
NATIVE_MANAGE_ACTION = 'org.local.dualsense.usb.native.manage'
NATIVE_RULE_HEADER = '// DualSense USB native access '
NATIVE_HELPER_PATH = 'usr/libexec/dualsense-usb-helper'
NATIVE_ADMIN_PATH = 'usr/libexec/dualsense-usb-access'
NATIVE_POLICY_PATH = 'usr/share/polkit-1/actions/org.local.dualsense.usb.native.policy'
NATIVE_UDEV_PATH = 'usr/lib/udev/rules.d/70-dualsense-usb-native.rules'


def native_identity(actor):
    uid,username=actor
    if type(uid) is not int or not 0<uid<2**32-1 or not isinstance(username,str) or not 0<len(username)<=256:
        raise ValueError('Conta inválida.')
    return uid,username


def native_actor():
    if os.geteuid()!=0:raise ValueError('É necessária autorização administrativa.')
    value=os.environ.get('PKEXEC_UID','')
    if not re.fullmatch('[1-9][0-9]{0,9}',value):raise ValueError('Abra o suporte USB por pkexec, a partir da sua conta.')
    uid=int(value)
    return native_identity((uid,pwd.getpwuid(uid).pw_name))


def native_rule(actor):
    uid,username=native_identity(actor)
    record={'format':1,'uid':uid,'username':username}
    return (NATIVE_RULE_HEADER+json.dumps(record,sort_keys=True)+'\n'+
        'polkit.addRule(function(action, subject) {\n'+
        '    if (action.id === '+json.dumps(NATIVE_CONTROL_ACTION)+
        ' && subject.user === '+json.dumps(username)+' && subject.local && subject.active) {\n'+
        '        return polkit.Result.YES;\n    }\n});\n').encode()


def native_rule_actor(data,uid):
    try:
        text=data.decode('utf-8');first=text.split('\n',1)[0]
        if not first.startswith(NATIVE_RULE_HEADER):raise ValueError()
        record=json.loads(first[len(NATIVE_RULE_HEADER):])
        if not isinstance(record,dict) or set(record)!={'format','uid','username'} or type(record['format']) is not int or record['format']!=1:
            raise ValueError()
        actor=native_identity((record['uid'],record['username']))
        if actor[0]!=uid or native_rule(actor)!=data:raise ValueError()
        return actor
    except (ValueError,TypeError,KeyError,UnicodeError) as exc:
        raise ValueError('A concessão foi modificada ou pertence a outra conta. O arquivo será preservado.') from exc


class NativeGrantFiles:
    def __init__(self,root=Path('/'),owner_uid=0):
        self.root=Path(root);self.owner_uid=owner_uid

    def relative(self,kind,uid):
        native_identity((uid,'validation'))
        if kind=='rule':return f'etc/polkit-1/rules.d/49-dualsense-usb-native-{uid}.rules'
        if kind=='lock':return f'var/lib/dualsense-usb/native-access/{uid}.lock'
        raise ValueError('Arquivo desconhecido.')

    def path(self,relative,create=False):
        parts=Path(relative).parts
        if Path(relative).is_absolute() or any(part in ('.','..') for part in parts):raise ValueError('Caminho inválido.')
        current=self.root
        for part in parts[:-1]:
            current=current/part
            try:info=current.lstat()
            except FileNotFoundError:
                if not create:return self.root/relative
                try:
                    current.mkdir(mode=0o755)
                    # A caller's restrictive umask must not hide a newly
                    # created rules directory from polkitd. Existing directories
                    # retain their administrator-selected permissions/group.
                    directory=os.open(current,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:os.fchmod(directory,0o755);os.fsync(directory)
                    finally:os.close(directory)
                    parent=os.open(current.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:os.fsync(parent)
                    finally:os.close(parent)
                except FileExistsError:pass  # Another account may create shared parents.
                info=current.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022:
                raise ValueError('Diretório administrativo sem proteção adequada: '+str(current))
        return self.root/relative

    def read(self,relative,limit=16384):
        path=self.path(relative)
        try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:return None
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022 or info.st_nlink!=1 or info.st_size>limit:
                raise ValueError('Arquivo administrativo inesperado: '+str(path))
            with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(limit+1)
            if len(data)>limit:raise ValueError('Arquivo administrativo grande demais.')
            return data,stat.S_IMODE(info.st_mode)
        finally:os.close(fd)

    @contextmanager
    def lock(self,uid,shared=False,create=False):
        path=self.path(self.relative('lock',uid),create=create)
        # Other accounts must not be able to take a lock and deny this user USB.
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|(os.O_CREAT if create else 0),0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o077 or info.st_nlink!=1 or info.st_size:
                raise ValueError('Bloqueio administrativo inválido.')
            try:fcntl.flock(fd,(fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Esta conta tem sessões USB ou outra configuração em execução. Encerre seus controles no app antes de revogar o acesso.') from None
            if create:
                os.fsync(fd)
                directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:os.fsync(directory)
                finally:os.close(directory)
            yield
        finally:os.close(fd)

    @contextmanager
    def session(self,actor):
        uid,username=native_identity(actor)
        with ExitStack() as stack:
            try:stack.enter_context(self.lock(uid,shared=True))
            except FileNotFoundError as exc:
                raise ValueError('Configure o acesso USB para esta conta no aplicativo.') from exc
            saved=self.read(self.relative('rule',uid))
            if saved is None or native_rule_actor(saved[0],uid)!=(uid,username):
                raise ValueError('Configure o acesso USB para esta conta no aplicativo.')
            # Keep the lock throughout USB ownership, not only the check.
            yield
