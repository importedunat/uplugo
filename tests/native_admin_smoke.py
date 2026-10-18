# SPDX-License-Identifier: GPL-3.0-only
"""Run only in native_admin_namespace.py's disposable root user namespace.

Exercises generated fixed-path root programs with synthetic PKEXEC_UID values.
This does not exercise actual pkexec authentication, polkit decisions or USB.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,'/tmp/source')
from build_helper import native_payloads,BASE
from native_grant import NativeGrantFiles,NATIVE_ADMIN_PATH,NATIVE_HELPER_PATH
from native_lifecycle import NativePackageGate
from app_info import VERSION


def main():
    mapping=Path('/proc/self/uid_map').read_text().split()
    assert len(mapping)==3 and mapping[0]=='0' and mapping[1]!='0' and mapping[2]=='1'
    assert os.geteuid()==0 and Path('/run/dualsense-native-admin-test').read_text()=='disposable namespace\n'
    assert not list(Path('/sys/bus/usb/devices').iterdir())
    assert not Path('/run/dbus/system_bus_socket').exists()
    files=NativeGrantFiles();payloads=native_payloads()
    for name,(data,mode) in payloads.items():
        path=files.path(name,create=True);path.write_bytes(data);path.chmod(mode)
    NativePackageGate(files).finish('deb',VERSION,{name:(hashlib.sha256(data).hexdigest(),mode) for name,(data,mode) in payloads.items()})
    before={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in payloads}
    def execute(program,uid,*args):
        return subprocess.run(['/usr/bin/python3','-I','/'+program,*args],
            env=dict(os.environ,PKEXEC_UID=str(uid)),capture_output=True,text=True,timeout=8)
    for uid in (1000,1001):
        denied=execute(NATIVE_HELPER_PATH,uid,'--fixture-no-usb')
        assert denied.returncode and 'Configure o acesso' in denied.stderr,denied.stderr
        result=execute(NATIVE_ADMIN_PATH,uid,'install');assert result.returncode==0,result.stderr
        assert files.read(files.relative('lock',uid))==(b'',0o600)
        admitted=execute(NATIVE_HELPER_PATH,uid,'--fixture-no-usb')
        assert admitted.returncode and 'Operação inválida' in admitted.stderr,admitted.stderr
    bob=files.read(files.relative('rule',1001))
    # Use the exact embedded permission guard to hold a real shared lock, without
    # creating USB endpoints or pretending to provide controller input.
    code=(BASE/'native_grant.py').read_text()+"\nwith NativeGrantFiles().session(native_actor()):\n    print('held',flush=True)\n    input()\n"
    held=subprocess.Popen(['/usr/bin/python3','-I','-c',code],env=dict(os.environ,PKEXEC_UID='1000'),
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert held.stdout.readline().strip()=='held'
        result=execute(NATIVE_ADMIN_PATH,1000,'remove')
        assert result.returncode and 'sessões USB' in result.stderr,result.stderr
        result=execute(NATIVE_ADMIN_PATH,1001,'remove');assert result.returncode==0,result.stderr
        assert files.read(files.relative('rule',1000)) is not None
        assert files.read(files.relative('rule',1001)) is None
    finally:
        if held.poll() is None:held.communicate('\n',timeout=5)
    assert held.returncode==0
    assert execute(NATIVE_ADMIN_PATH,1001,'install').returncode==0
    assert files.read(files.relative('rule',1001))==bob
    assert execute(NATIVE_ADMIN_PATH,1000,'remove').returncode==0
    assert execute(NATIVE_HELPER_PATH,1000,'--fixture-no-usb').returncode!=0
    assert execute(NATIVE_ADMIN_PATH,1000,'install','--uid','1001').returncode!=0
    assert execute(NATIVE_ADMIN_PATH,0,'install').returncode!=0
    assert execute(NATIVE_ADMIN_PATH,9999,'install').returncode!=0
    # A renamed account cannot inherit an old name-based polkit grant silently.
    passwd=Path('/etc/passwd');passwd.write_text(passwd.read_text().replace('bob:','renamed:'))
    denied=execute(NATIVE_HELPER_PATH,1001,'--fixture-no-usb')
    assert denied.returncode and 'Configure o acesso' in denied.stderr
    assert execute(NATIVE_ADMIN_PATH,1001,'install').returncode==0
    admitted=execute(NATIVE_HELPER_PATH,1001,'--fixture-no-usb')
    assert 'Operação inválida' in admitted.stderr
    assert before=={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in payloads}
    print('NATIVE ADMIN OK: generated fixed-path programs, two accounts, root-owned 0600 locks, active-session exclusion, independent revocation, renamed identity, invalid arguments, immutable package files; no real authorization or USB.',flush=True)


if __name__=='__main__':main()
