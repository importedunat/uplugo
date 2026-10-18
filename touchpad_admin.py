# SPDX-License-Identifier: GPL-3.0-only
"""Narrow administrative action, embedded in a standalone authorized program.

No destination or sysfs path is accepted from the command line. Test roots and
command runners are in-process fixtures only. Rules are local computer settings
and remain until explicitly restored, including after uninstalling the app.
"""
from contextlib import contextmanager
import fcntl
import os
import json
import pwd
import re
from pathlib import Path
import stat
import subprocess
import tempfile
from touchpad_policy import (touchpad_identity,touchpad_rule_path,touchpad_rule,
    touchpad_nodes,touchpad_matches,TOUCHPAD_LOCK)


class TouchpadAdmin:
    def __init__(self,root=Path('/'),sys_root=Path('/sys'),owner_uid=0,runner=None):
        self.root=Path(root);self.sys_root=Path(sys_root);self.owner_uid=owner_uid
        self.runner=runner or subprocess.run

    def path(self,relative,create=False):
        current=self.root
        for part in Path(relative).parent.parts:
            current=current/part
            try:info=current.lstat()
            except FileNotFoundError:
                if not create:return self.root/relative
                try:current.mkdir(mode=0o755);current.chmod(0o755)
                except FileExistsError:pass
                info=current.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022:
                raise ValueError('unsafe-directory')
        return self.root/relative

    def read(self,relative):
        path=self.path(relative)
        try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:return None
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022 or info.st_nlink!=1 or info.st_size>4096:
                raise ValueError('custom-rule')
            data=stream.read(4097)
        if len(data)>4096:raise ValueError('custom-rule')
        return data,stat.S_IMODE(info.st_mode)

    @contextmanager
    def lock(self):
        path=self.path(TOUCHPAD_LOCK,True)
        try:
            fd=os.open(path,os.O_RDONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            os.fchmod(fd,0o600)
        except FileExistsError:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_nlink!=1 or info.st_size or stat.S_IMODE(info.st_mode)!=0o600:
                raise ValueError('unsafe-lock')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('busy') from None
            yield
        finally:os.close(fd)

    def sync(self,directory):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def write(self,relative,value):
        path=self.path(relative,True)
        if value is None:path.unlink(missing_ok=True);self.sync(path.parent);return
        data,mode=value;fd,temporary=tempfile.mkstemp(prefix='.dualsense-touchpad-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data);os.fchmod(stream.fileno(),mode);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path);self.sync(path.parent)
        finally:Path(temporary).unlink(missing_ok=True)

    def command(self,*args):
        return self.runner(['/usr/bin/udevadm',*args],stdin=subprocess.DEVNULL,capture_output=True,text=True,check=True,timeout=15)

    def refresh(self,identity):
        self.command('control','--reload-rules')
        count=0
        for event in touchpad_nodes(identity,self.sys_root):
            # Resolve the full input/inputN/eventN path once. A transient eventN
            # class name could otherwise be reused by another device after an
            # unplug. Never trigger the USB parent or its gamepad node.
            try:event=event.resolve(strict=True)
            except FileNotFoundError:continue
            event.relative_to(self.sys_root.resolve())
            if not touchpad_matches(event,identity):continue
            filters=['--settle','--subsystem-match=input','--sysname-match='+event.name,str(event)]
            try:self.command('trigger','--action=remove',*filters)
            finally:
                # Even a failed remove/settle must try to make the touchpad
                # discoverable again. An unplugged device needs no synthetic add.
                if touchpad_matches(event,identity):
                    self.command('trigger','--action=add',*filters)
            count+=1
        return count

    def apply(self,identity,choice):
        identity=touchpad_identity(identity)
        if choice not in ('game','system'):raise ValueError('choice')
        relative=touchpad_rule_path(identity);expected=touchpad_rule(identity)
        with self.lock():
            before=self.read(relative)
            if before is not None and before[0]!=expected:raise ValueError('custom-rule')
            desired=(expected,0o644) if choice=='game' else None
            try:
                if before!=desired:self.write(relative,desired)
                count=self.refresh(identity)
            except Exception as exc:
                # Restore only our own previous policy. Re-add under the old
                # policy after failures; report separately if recovery fails.
                try:
                    self.write(relative,before);self.refresh(identity)
                except Exception:raise RuntimeError('recovery-needed') from exc
                raise RuntimeError('apply-failed-restored') from exc
        return {'choice':choice,'refreshed':count,'pending':count==0}


def touchpad_main(arguments):
    if os.geteuid()!=0:raise ValueError('authorization')
    uid=os.environ.get('PKEXEC_UID','')
    if not re.fullmatch('[1-9][0-9]{0,9}',uid) or int(uid)>=2**32-1:raise ValueError('authorization')
    pwd.getpwuid(int(uid))
    if len(arguments)!=2 or arguments[0] not in ('game','system'):raise ValueError('choice')
    print(json.dumps(TouchpadAdmin().apply(arguments[1],arguments[0])))
