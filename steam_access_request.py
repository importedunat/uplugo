# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a private, explicit Steam Snap authorization; no privilege on inspect."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
from deployment import inspect_deployment
from touchpad_policy import touchpad_identity
from steam_access import STEAM_ADMIN,steam_snapshot


@contextmanager
def prepare_steam_access(identity,choice,directory=None):
    identity=touchpad_identity(identity)
    if choice not in ('allow','system'):raise ValueError('choice')
    if inspect_deployment(directory).system:
        yield ['pkexec','/'+STEAM_ADMIN,choice,identity];return
    from build_helper import steam_access_source
    with tempfile.TemporaryDirectory(prefix='dualsense-steam-access-') as temporary:
        path=Path(temporary)/'configure-steam-access.py'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(steam_access_source())
        yield ['pkexec','/usr/bin/python3','-I',str(path),choice,identity]


class SteamAccessBackend:
    def __init__(self,identity,directory=None):
        self.identity=touchpad_identity(identity);self.directory=directory

    def inspect(self):return steam_snapshot(self.identity)

    def apply(self,choice):
        with prepare_steam_access(self.identity,choice,self.directory) as command:
            result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True)
        answer={}
        if result.returncode==0:
            try:
                answer=json.loads(result.stdout)
                if not isinstance(answer,dict) or set(answer)!={'choice','refreshed','pending'} or answer['choice']!=choice or type(answer['refreshed']) is not int or answer['refreshed']<0 or type(answer['pending']) is not bool or answer['pending']!=(answer['refreshed']==0):raise ValueError()
            except (ValueError,TypeError):raise RuntimeError('invalid-result') from None
        view=self.inspect()
        if result.returncode==0 and view['saved']!=choice:raise RuntimeError('not-saved')
        return result,answer,view
