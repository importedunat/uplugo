# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a private, short-lived administrative request from read-only code.

Only explicit configuration/removal calls use this module. The privileged
script is self-contained, uses fixed system paths and still requires pkexec.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import tempfile
import stat
import threading
import time
from build_helper import helper_source, native_helper_source, installation_source, removal_source
from deployment import inspect_deployment, SYSTEM_ACCESS
from i18n import _


class HelperRevision:
    """Advisory comparison only; never authorizes, installs or stops a session.

    Compare off the GTK thread, memoizing immutable expected source and the
    installed file signature. A different file may be newer or locally changed;
    it is not necessarily an old version or an invalid authorization.
    """
    def __init__(self,path,native=False,builder=None):
        self.path=Path(path)
        self.builder=builder or (native_helper_source if native else helper_source)
        self.native=native
        self._lock=threading.Lock()
        self._state='checking';self._running=False;self._next=0
        self._signature=None;self._expected=None

    @staticmethod
    def signature(info):
        return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

    def state(self):
        with self._lock:
            if not self._running and time.monotonic()>=self._next:
                self._running=True
                threading.Thread(target=self._check,daemon=True).start()
            return self._state

    def _check(self):
        result='unavailable'
        try:
            info=self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size>2*1024*1024:
                return
            signature=self.signature(info)
            if signature==self._signature:
                result=self._state
                return
            fd=os.open(self.path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as stream:
                before=os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):return
                actual=stream.read(2*1024*1024+1)
                after=os.fstat(stream.fileno())
            if len(actual)>2*1024*1024:return
            if self.signature(before)!=self.signature(after) or signature!=self.signature(after):
                result='checking';return
            if self._expected is None:self._expected=self.builder().encode()
            result='current' if actual==self._expected else 'different'
            self._signature=signature
        except FileNotFoundError:result='missing';self._signature=None
        except Exception:self._signature=None
        finally:
            with self._lock:
                self._state=result;self._running=False;self._next=time.monotonic()+5


@dataclass(frozen=True)
class AccessRequest:
    command: tuple
    expected_helper: str | None


@contextmanager
def manual_request(action,helper=None):
    if action not in ('install','remove'):raise ValueError('Unknown access action')
    source=installation_source(helper) if action=='install' else removal_source()
    with tempfile.TemporaryDirectory(prefix='dualsense-access-') as temporary:
        script=Path(temporary)/(action+'-access.py')
        fd=os.open(script,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(source)
        yield AccessRequest(('pkexec','/usr/bin/python3','-I',str(script)),helper)


def legacy_access_present():
    paths=(Path('/usr/local/libexec/dualsense-usb-helper'),Path('/usr/share/polkit-1/actions/org.local.dualsense.usb.policy'))
    return any(path.exists() or path.is_symlink() for path in paths)


def remove_legacy_access(directory=None):
    """Explicit native-setup cleanup of the separate manual installation.

    The existing self-contained remover still verifies ownership, registered
    contents and active helpers. Native package files/grants have different paths.
    """
    if not inspect_deployment(directory).system:
        raise ValueError(_('Abra essa limpeza pelo assistente da versão instalada pelo sistema.'))
    with manual_request('remove') as request:
        return subprocess.run(list(request.command),stdin=subprocess.DEVNULL,capture_output=True,text=True)


@contextmanager
def prepare_access(action,directory=None):
    if action not in ('install','remove'):raise ValueError('Unknown access action')
    profile=inspect_deployment(directory)
    helper=(native_helper_source() if profile.system else helper_source()) if action=='install' else None
    if profile.system:
        # Native grants are managed by a package-owned administrator, never by
        # the manual installer that would replace package-owned files.
        if not SYSTEM_ACCESS.is_file():
            raise RuntimeError(_('O suporte USB do pacote está incompleto. Reinstale o pacote pelo gerenciador da distribuição.'))
        yield AccessRequest(('pkexec',str(SYSTEM_ACCESS),action),helper)
        return
    # mkdtemp isolates concurrent requests and refuses pre-existing names.
    # No files in the installed application tree are created or replaced.
    with manual_request(action,helper) as request:yield request


def run_access(action,interactive=False,directory=None):
    """Keep the script alive until authorization and execution finish."""
    with prepare_access(action,directory) as request:
        # CLI maintenance keeps its terminal for pkexec's text agent. GUI calls
        # collect diagnostics and rely on the desktop's graphical agent.
        options={} if interactive else dict(stdin=subprocess.DEVNULL,capture_output=True,text=True)
        result=subprocess.run(list(request.command),**options)
        return result,request.expected_helper
