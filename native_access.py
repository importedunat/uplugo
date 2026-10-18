# SPDX-License-Identifier: GPL-3.0-only
"""Native per-account grant administration; embedded as a fixed root program.

It writes only the calling account's grant and lock. Package-owned helper,
policy and udev files are verified but never rewritten. No host CLI root override.
"""
import hashlib
import os
from pathlib import Path
import tempfile
from native_grant import native_identity, native_rule, native_rule_actor


class NativeAccess:
    def __init__(self,files,expected):
        self.files=files;self.expected=expected

    def verify_package(self):
        for relative,(digest,mode) in self.expected.items():
            current=self.files.read(relative,1024*1024)
            if current is None or current[1]!=mode or hashlib.sha256(current[0]).hexdigest()!=digest:
                raise ValueError('O suporte USB do pacote está incompleto ou foi modificado. Reinstale pelo gerenciador da distribuição.')

    def sync_parent(self,path):
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def replace(self,relative,data,mode=0o644):
        path=self.files.path(relative,create=True)
        fd,temporary=tempfile.mkstemp(prefix='.dualsense-native-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(data);os.fchmod(stream.fileno(),mode);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
            self.sync_parent(path)
        finally:Path(temporary).unlink(missing_ok=True)

    def restore(self,relative,saved):
        if saved is not None:self.replace(relative,*saved)
        else:
            path=self.files.path(relative);path.unlink(missing_ok=True);self.sync_parent(path)

    def apply(self,action,actor):
        if action not in ('install','remove'):raise ValueError('Operação inválida.')
        uid,_=native_identity(actor)
        relative=self.files.relative('rule',uid)
        if action=='install':
            self.verify_package()
            before=self.files.read(relative)
            # Re-authorizing an unchanged grant must not interrupt its streams.
            lock=self.files.read(self.files.relative('lock',uid),0)
            if before==(native_rule(actor),0o644) and lock==(b'',0o600):return False
        with self.files.lock(uid,create=True):
            saved=self.files.read(relative)
            if saved is not None:native_rule_actor(saved[0],uid)
            if action=='remove' and saved is None:return False
            try:
                if action=='install':self.replace(relative,native_rule(actor))
                else:
                    path=self.files.path(relative);path.unlink();self.sync_parent(path)
            except Exception as exc:
                try:self.restore(relative,saved)
                except Exception as rollback:
                    raise RuntimeError('A configuração falhou e a restauração precisa de atenção: '+str(rollback)) from exc
                raise RuntimeError('A configuração falhou; a concessão anterior foi restaurada: '+str(exc)) from exc
        return True
