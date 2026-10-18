# SPDX-License-Identifier: GPL-3.0-only
"""Execute generated manual/native Steam grant programs with private fake Snap/udev."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/tmp/source')
from build_helper import native_payloads,steam_access_source
from native_grant import NativeGrantFiles
from native_lifecycle import NativePackageGate
from app_info import VERSION
from steam_access import STEAM_ADMIN,STEAM_HELPERS,steam_rule_path,steam_rule,steam_snapshot
from tests.test_steam_access import fixture_hid,WHITE,BLACK


def main():
    mapping=Path('/proc/self/uid_map').read_text().split();assert mapping[0]=='0' and mapping[1]!='0' and mapping[2]=='1'
    assert os.geteuid()==0 and Path('/run/dualsense-native-admin-test').read_text()=='disposable namespace\n'
    assert not Path('/run/dbus/system_bus_socket').exists();os.umask(0o022)
    files=NativeGrantFiles();payloads=native_payloads()
    for name,(data,mode) in payloads.items():
        path=files.path(name,create=True);path.write_bytes(data);path.chmod(mode)
    NativePackageGate(files).finish('deb',VERSION,{name:(hashlib.sha256(data).hexdigest(),mode) for name,(data,mode) in payloads.items()})
    before={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in payloads}
    helper=files.path(STEAM_HELPERS[0],create=True);helper.write_text('# disposable fixture; never executed\n');helper.chmod(0o755)
    manual=Path('/tmp/steam-admin.py');manual.write_text(steam_access_source())
    white=fixture_hid(Path('/'));fixture_hid(Path('/'),'hidraw1',BLACK);fixture_hid(Path('/'),'hidraw2',WHITE,bus='0005')
    def execute(program,*args,uid=1000):
        return subprocess.run(['/usr/bin/python3','-I',str(program),*args],env=dict(os.environ,PKEXEC_UID=str(uid)),capture_output=True,text=True,timeout=12)
    for program in (manual,Path('/'+STEAM_ADMIN)):
        result=execute(program,'allow',WHITE);assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)=={'choice':'allow','refreshed':1,'pending':False}
        assert steam_snapshot(WHITE)['nodes'][0]['tagged'] is True
        assert not Path('/'+steam_rule_path(BLACK)).exists()
        commands=[json.loads(line) for line in Path('/run/steam-commands.jsonl').read_text().splitlines()]
        assert all(c[-1]==str(white) for c in commands if c[0]=='trigger')
        # Revocation stays possible after Snap is no longer connected.
        Path('/run/steam-disconnected').touch()
        result=execute(program,'system',WHITE,uid=1001);assert result.returncode==0,result.stderr
        view=steam_snapshot(WHITE);assert view['saved']=='system' and view['nodes'][0]['tagged'] is False
        assert execute(program,'allow',WHITE).returncode!=0
        Path('/run/steam-disconnected').unlink()
        Path('/run/steam-fail-remove').touch()
        result=execute(program,'allow',WHITE);assert result.returncode!=0 and 'apply-failed-restored' in result.stderr
        assert steam_snapshot(WHITE)['saved']=='system'
        result=execute(program,'allow',WHITE);assert result.returncode==0,result.stderr
        Path('/run/steam-external').touch()
        assert execute(program,'system',WHITE).returncode==0
        view=steam_snapshot(WHITE);assert view['saved']=='system' and view['nodes'][0]['tagged'] is True
        Path('/run/steam-external').unlink()
        for args in (('other',WHITE),('allow','../node'),('allow',WHITE,'--root','/tmp')):assert execute(program,*args).returncode!=0
        assert execute(program,'allow',WHITE,uid=0).returncode!=0
        assert execute(program,'allow',WHITE,uid=9999).returncode!=0
    assert before=={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in payloads}
    print('STEAM ACCESS ADMIN OK: generated manual/native programs, fixed paths and actor, target USB HID only, save/revoke, disconnected Snap, rollback, external permission preservation, invalid arguments; private fake Snap/udev, no host authorization or USB.')


if __name__=='__main__':main()
