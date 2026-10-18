# SPDX-License-Identifier: GPL-3.0-only
"""Execute actual generated admin programs in a marked namespace, with fake udev."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,'/tmp/source')
from build_helper import native_payloads,touchpad_source
from native_grant import NativeGrantFiles
from native_lifecycle import NativePackageGate
from app_info import VERSION
from touchpad_policy import TOUCHPAD_ADMIN,touchpad_rule_path,touchpad_rule,touchpad_snapshot
from tests.test_touchpad import fixture_device,WHITE,BLACK


def main():
    mapping=Path('/proc/self/uid_map').read_text().split()
    assert len(mapping)==3 and mapping[0]=='0' and mapping[1]!='0' and mapping[2]=='1'
    assert os.geteuid()==0 and Path('/run/dualsense-native-admin-test').read_text()=='disposable namespace\n'
    assert not Path('/run/dbus/system_bus_socket').exists()
    os.umask(0o022)
    files=NativeGrantFiles();payloads=native_payloads()
    for name,(data,mode) in payloads.items():
        path=files.path(name,create=True);path.write_bytes(data);path.chmod(mode)
    NativePackageGate(files).finish('deb',VERSION,{name:(hashlib.sha256(data).hexdigest(),mode) for name,(data,mode) in payloads.items()})
    before={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in payloads}
    manual=Path('/tmp/touchpad-admin.py');manual.write_text(touchpad_source())
    white=fixture_device(Path('/'));fixture_device(Path('/'),'event14',BLACK,product='0df2')
    fixture_device(Path('/'),'event2',name='Sony DualSense Wireless Controller')
    fixture_device(Path('/'),'event8',name='Mouse')
    def execute(program,*args,uid=1000):
        return subprocess.run(['/usr/bin/python3','-I',str(program),*args],env=dict(os.environ,PKEXEC_UID=str(uid)),capture_output=True,text=True,timeout=10)
    for program in (manual,Path('/'+TOUCHPAD_ADMIN)):
        result=execute(program,'game',WHITE);assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)=={'choice':'game','refreshed':1,'pending':False}
        assert Path('/'+touchpad_rule_path(WHITE)).read_bytes()==touchpad_rule(WHITE)
        assert touchpad_snapshot(WHITE)['nodes'][0]['ignored'] is True
        assert not Path('/'+touchpad_rule_path(BLACK)).exists()
        commands=[json.loads(line) for line in Path('/run/touchpad-commands.jsonl').read_text().splitlines()]
        assert all(command[-1]==str(white) for command in commands if command[0]=='trigger')
        # An administrator in a second account can restore this computer-wide
        # preference. It is not a per-account USB access grant.
        result=execute(program,'system',WHITE,uid=1001);assert result.returncode==0,result.stderr
        assert touchpad_snapshot(WHITE)['saved']=='system' and touchpad_snapshot(WHITE)['nodes'][0]['ignored'] is False
        Path('/run/touchpad-fail-remove').touch()
        result=execute(program,'game',WHITE);assert result.returncode!=0 and 'apply-failed-restored' in result.stderr
        assert touchpad_snapshot(WHITE)['saved']=='system' and touchpad_snapshot(WHITE)['nodes'][0]['ignored'] is False
        for arguments in (('unknown',WHITE),('game','../outside'),('game',WHITE,'--root','/tmp')):
            assert execute(program,*arguments).returncode!=0
        assert execute(program,'game',WHITE,uid=0).returncode!=0
        assert execute(program,'game',WHITE,uid=9999).returncode!=0
    assert before=={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in payloads}
    print('TOUCHPAD ADMIN OK: generated manual/native programs, fixed paths, isolated root UID, synthetic input nodes and udev, policy save/restore, targeted refresh, failed-remove recovery, invalid arguments/actors; package payloads unchanged. No real polkit, udev daemon, compositor, Steam or USB.')


if __name__=='__main__':main()
