# SPDX-License-Identifier: GPL-3.0-only
"""Non-interactive permission checks, kept outside the GTK loop."""
import os
from pathlib import Path
import subprocess
import threading
import time
from native_grant import NATIVE_CONTROL_ACTION


def native_authorized():
    try:
        # Include start-time and UID so a reused PID cannot change the subject.
        fields=Path('/proc/self/stat').read_text().rpartition(')')[2].split()
        started=int(fields[19])
        command=['/usr/bin/pkcheck','--action-id',NATIVE_CONTROL_ACTION,
                 '--process',f'{os.getpid()},{started},{os.getuid()}']
        result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,timeout=3)
        return result.returncode==0
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):return False


class NativeAuthorization:
    def __init__(self,probe=None):
        self.probe=probe or native_authorized;self._lock=threading.Lock()
        self._value=False;self._running=False;self._next=0;self._generation=0

    def _store(self,value,generation):
        with self._lock:
            if generation==self._generation:
                self._value=value;self._running=False;self._next=time.monotonic()+5

    def _check(self,generation):
        try:value=bool(self.probe())
        except Exception:value=False
        self._store(value,generation)

    def ready(self):
        with self._lock:
            if not self._running and time.monotonic()>=self._next:
                self._running=True
                threading.Thread(target=self._check,args=(self._generation,),daemon=True).start()
            return self._value

    def confirm(self):
        """Called by the configuration worker; allow polkit's rule monitor time."""
        with self._lock:
            self._generation+=1;generation=self._generation;self._running=True
        value=False
        try:
            for delay in (0,.15,.35,.7):
                if delay:time.sleep(delay)
                if self.probe():value=True;break
            return value
        finally:self._store(value,generation)
