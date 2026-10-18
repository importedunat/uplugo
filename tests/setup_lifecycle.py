# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic setup child survives its parent. Optional real user-systemd check.

No GTK window, installed app, hardware, privileged action or real settings.
--systemd creates and removes only a temporary test service and scope.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))


def until(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>=deadline:raise AssertionError('Setup lifecycle test timed out')
        time.sleep(.025)


def exercise(systemd=False):
    from session import systemd_available
    if systemd and not systemd_available():raise RuntimeError('A running user systemd manager is required for --systemd.')
    with tempfile.TemporaryDirectory(prefix='dualsense-setup-lifecycle-') as temporary:
        root=Path(temporary);directory=root/'download $name % with spaces';directory.mkdir()
        child=directory/'setup.py'
        child.write_text('import json,os,time\nfrom pathlib import Path\n'
            +f'root=Path({str(root)!r})\n'
            +'info={"pid":os.getpid(),"cgroup":Path("/proc/self/cgroup").read_text(),"cwd":str(Path.cwd())}\n'
            +'(root/"child.tmp").write_text(json.dumps(info));os.replace(root/"child.tmp",root/"child.json")\n'
            +'deadline=time.monotonic()+30\n'
            +'while not (root/"finish").exists() and time.monotonic()<deadline:time.sleep(.025)\n'
            +'(root/"exited").write_text("done")\n')
        parent=root/'parent.py'
        parent.write_text('import os,sys,time\nfrom pathlib import Path\nfrom unittest.mock import patch\n'
            +f'sys.path.insert(0,{str(BASE)!r})\n'
            +f'os.environ["XDG_STATE_HOME"]={str(root/"state")!r}\n'
            +'from setup_state import launch_assistant\n'
            +f'with patch("setup_state.systemd_available",return_value={systemd!r}):launch_assistant({str(directory)!r})\n'
            +f'Path({str(root/"parent-cgroup")!r}).write_text(Path("/proc/self/cgroup").read_text())\n'
            +'time.sleep(30)\n')
        process=None;unit='dualsense-setup-qa-'+uuid.uuid4().hex+'.service';info=None
        try:
            if systemd:
                subprocess.run(['systemd-run','--user','--quiet','--collect','--unit='+unit,
                    '--service-type=exec','--property=KillMode=mixed','--property=TimeoutStopSec=3',
                    '/usr/bin/python3',str(parent)],check=True,capture_output=True,timeout=10)
            else:
                process=subprocess.Popen([sys.executable,str(parent)],stdin=subprocess.DEVNULL)
            until(lambda:(root/'child.json').exists() and (root/'parent-cgroup').exists())
            info=json.loads((root/'child.json').read_text())
            assert info['cwd']==str(directory),'Special path characters were expanded'
            if systemd:
                assert unit in (root/'parent-cgroup').read_text()
                assert unit not in info['cgroup'] and '.scope' in info['cgroup'],info
                subprocess.run(['systemctl','--user','stop',unit],check=True,capture_output=True,timeout=10)
            else:
                process.terminate();process.wait(timeout=5)
            time.sleep(.15)
            os.kill(info['pid'],0)
            assert not (root/'exited').exists(),'Assistant exited with its parent'
            (root/'finish').touch();until(lambda:(root/'exited').exists())
            return {'mode':'systemd scope' if systemd else 'direct child',
                    'survived_parent_exit':True,'literal_special_path':True,'synthetic_only':True}
        finally:
            (root/'finish').touch()
            if systemd:subprocess.run(['systemctl','--user','stop',unit],capture_output=True,timeout=10)
            if process and process.poll() is None:process.terminate();process.wait(timeout=5)
            if info and not (root/'exited').exists():
                try:os.kill(info['pid'],signal.SIGTERM)
                except ProcessLookupError:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--systemd',action='store_true');args=parser.parse_args()
    print(json.dumps(exercise(args.systemd),indent=2))
