# SPDX-License-Identifier: GPL-3.0-only
"""Explicit administrative request; inspecting policy never requests a password."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
from deployment import inspect_deployment
from touchpad_policy import TOUCHPAD_ADMIN,touchpad_identity,touchpad_snapshot


@contextmanager
def prepare_touchpad(identity,choice,directory=None):
    identity=touchpad_identity(identity)
    if choice not in ('game','system'):raise ValueError('choice')
    if inspect_deployment(directory).system:
        yield ['pkexec','/'+TOUCHPAD_ADMIN,choice,identity]
        return
    from build_helper import touchpad_source
    source=touchpad_source()
    with tempfile.TemporaryDirectory(prefix='dualsense-touchpad-') as temporary:
        path=Path(temporary)/'configure-touchpad.py'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(source)
        yield ['pkexec','/usr/bin/python3','-I',str(path),choice,identity]


class TouchpadBackend:
    def __init__(self,identity,directory=None):
        self.identity=touchpad_identity(identity);self.directory=directory

    def inspect(self):return touchpad_snapshot(self.identity)

    def apply(self,choice):
        with prepare_touchpad(self.identity,choice,self.directory) as command:
            result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True)
        value={}
        if result.returncode==0:
            try:
                value=json.loads(result.stdout)
                if not isinstance(value,dict) or set(value)!={'choice','refreshed','pending'} or value['choice']!=choice or type(value['refreshed']) is not int or value['refreshed']<0 or type(value['pending']) is not bool or value['pending']!=(value['refreshed']==0):raise ValueError()
            except (ValueError,TypeError):raise RuntimeError('invalid-result') from None
        view=self.inspect()
        if result.returncode==0 and view['saved']!=choice:raise RuntimeError('not-saved')
        return result,value,view
