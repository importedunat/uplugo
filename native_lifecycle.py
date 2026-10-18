# SPDX-License-Identifier: GPL-3.0-only
"""Persistent package transaction gate; no daemon or user-directory traversal.

Alternate roots are in-process fixtures, never privileged CLI arguments.
"""
from contextlib import contextmanager, ExitStack
import atexit
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from native_grant import NativeGrantFiles, native_rule_actor

PACKAGE_LOCK='var/lib/dualsense-usb/package.lock'
PACKAGE_STATE='var/lib/dualsense-usb/package-state.json'
PACKAGE_WAIT='Uplugo: package maintenance is in progress or incomplete. Finish or repair the package-manager operation before opening the app.'
PACKAGE_BUSY='Uplugo is open. Quit the app (including its tray icon and setup assistant) in all accounts, then retry. No controllers were stopped.'


class NativePackageGate:
    def __init__(self,files=None):self.files=files or NativeGrantFiles()

    @contextmanager
    def lock(self,shared=False,create=False):
        path=self.files.path(PACKAGE_LOCK,create=create)
        flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
        if create:
            try:
                fd=os.open(path,flags|os.O_CREAT|os.O_EXCL,0o644)
                os.fchmod(fd,0o644)
            except FileExistsError:fd=os.open(path,flags)
        else:fd=os.open(path,flags)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.files.owner_uid or info.st_nlink!=1 or info.st_size or stat.S_IMODE(info.st_mode)!=0o644:
                raise ValueError('Unexpected package lock; preserved for administrator review.')
            try:fcntl.flock(fd,(fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError(PACKAGE_WAIT if shared else PACKAGE_BUSY) from None
            yield
        finally:os.close(fd)

    def state(self):
        saved=self.files.read(PACKAGE_STATE)
        if saved is None:return None
        data=json.loads(saved[0])
        if not isinstance(data,dict) or set(data)!={'format','phase','manager','version'} or type(data['format']) is not int or data['format']!=1 or data['phase'] not in ('maintenance','ready','removed') or data['manager'] not in ('deb','rpm') or not isinstance(data['version'],str) or not 0<len(data['version'])<64:
            raise ValueError('Unexpected package state; preserved for administrator review.')
        return data

    def check_manager(self,manager):
        if manager not in ('deb','rpm'):raise ValueError('Unknown package manager.')
        state=self.state()
        if state and state['manager']!=manager:raise ValueError('This installation belongs to another package manager.')
        return state

    def save(self,phase,manager,version):
        path=self.files.path(PACKAGE_STATE,create=True)
        data=json.dumps(dict(format=1,phase=phase,manager=manager,version=version),sort_keys=True)+'\n'
        fd,temporary=tempfile.mkstemp(prefix='.package-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(data);os.fchmod(stream.fileno(),0o644);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
            parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(parent)
            finally:os.close(parent)
        finally:Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def session(self,version):
        with ExitStack() as stack:
            try:stack.enter_context(self.lock(shared=True))
            except FileNotFoundError:raise RuntimeError(PACKAGE_WAIT) from None
            state=self.state()
            if state is None or state['phase']!='ready' or state['version']!=version:raise RuntimeError(PACKAGE_WAIT)
            yield

    def begin(self,manager,version,expected=None):
        with self.lock(create=True):
            state=self.check_manager(manager)
            if state is None and expected:
                for name in expected:
                    path=self.files.path(name)
                    if path.exists() or path.is_symlink():raise ValueError('Unmanaged file already exists: /'+name+'. Resolve this installation before using the system package.')
            self.save('maintenance',manager,version)

    def verify(self,expected):
        for name,(digest,mode) in expected.items():
            value=self.files.read(name,8*1024*1024)
            if value is None or value[1]!=mode or hashlib.sha256(value[0]).hexdigest()!=digest:
                raise ValueError('Package file missing or changed: /'+name+'. Repair or reinstall the package.')

    def finish(self,manager,version,expected):
        state=self.check_manager(manager)
        self.verify(expected)
        # Recovery after a refused upgrade must preserve an unchanged ready app.
        if state==dict(format=1,phase='ready',manager=manager,version=version):return
        with self.lock(create=True):
            self.verify(expected)
            self.save('ready',manager,version)

    def revoke_rules(self):
        directory=self.files.path('etc/polkit-1/rules.d/placeholder').parent
        if directory.exists():
            import re
            for path in sorted(directory.glob('49-dualsense-usb-native-*.rules')):
                match=re.fullmatch(r'49-dualsense-usb-native-([1-9][0-9]*)\.rules',path.name)
                if not match:continue
                try:
                    uid=int(match[1]);relative=self.files.relative('rule',uid)
                    saved=self.files.read(relative)
                    if saved is None:continue
                    native_rule_actor(saved[0],uid)
                except (OSError,ValueError) as exc:
                    print('Preserved local access file: '+path.name+' ('+str(exc)+')')
                    continue
                # A recognized grant must be revoked successfully. Keep the
                # transaction closed if it is busy or cannot be removed.
                with self.files.lock(uid,create=True):path.unlink()
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)

    def prepare_remove(self,manager,version):
        with self.lock(create=True):
            self.check_manager(manager)
            self.save('maintenance',manager,version)
            self.revoke_rules()

    def removed(self,manager,version):
        with self.lock(create=True):
            self.check_manager(manager)
            self.revoke_rules()
            self.save('removed',manager,version)


def hold_native_package(version):
    lease=NativePackageGate().session(version)
    lease.__enter__()
    atexit.register(lease.__exit__,None,None,None)
