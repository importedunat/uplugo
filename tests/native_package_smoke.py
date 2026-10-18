# SPDX-License-Identifier: GPL-3.0-only
"""Real dpkg/RPM transactions in native_package_namespace.py only; no USB."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
sys.path.insert(0,'/tmp/source')
from app_info import VERSION
import native_package as package
from native_grant import NativeGrantFiles
from native_lifecycle import NativePackageGate


def main():
    manager=sys.argv[1]
    mapping=Path('/proc/self/uid_map').read_text().split()
    assert len(mapping)==3 and mapping[0]=='0' and mapping[1]!='0' and mapping[2]=='1'
    assert os.geteuid()==0 and Path('/run/dualsense-native-package-test').read_text()=='private package transaction test\n'
    assert not list(Path('/sys/bus/usb/devices').iterdir()) and not Path('/run/dbus/system_bus_socket').exists()
    output=Path('/artifacts');cases=[]
    Path('/tmp/runtime').mkdir(mode=0o700)
    if manager=='deb':Path('/var/cache/apt/archives/partial').mkdir(parents=True,exist_ok=True)
    def run(command,success=True,**kwargs):
        result=subprocess.run(command,capture_output=True,text=True,timeout=120,**kwargs)
        if (result.returncode==0)!=success:
            print(result.stdout,result.stderr,flush=True)
            raise AssertionError((command,result.returncode,success))
        return result
    def install(artifact,success=True,initial=False):
        if manager=='deb':
            # Only UID 0 exists in this user namespace; apt cannot switch to
            # _apt. The outer namespace supplies filesystem/device isolation.
            command=['apt-get','-o','APT::Sandbox::User=root','-y','install',str(artifact)] if initial else ['dpkg','--install',str(artifact)]
        else:
            command=['dnf','--cacheonly','--disablerepo=*','--setopt=install_weak_deps=False','install','-y',str(artifact)] if initial else ['rpm','--upgrade','--replacepkgs',str(artifact)]
        return run(command,success)
    def remove(success=True):return run(['dpkg','--remove',package.NAME] if manager=='deb' else ['rpm','--erase',package.NAME],success)
    def revision():
        command=['dpkg-query','-W','-f=${Version}',package.NAME] if manager=='deb' else ['rpm','-q','--queryformat','%{VERSION}-%{RELEASE}',package.NAME]
        return run(command).stdout.strip()
    def private_admin(uid,action):
        return run(['/usr/bin/python3','-I','/usr/libexec/dualsense-usb-access',action],env=dict(os.environ,PKEXEC_UID=str(uid)))
    for uid,name in ((1000,'alice'),(1001,'bob')):
        try:pwd.getpwuid(uid)
        except KeyError:
            with Path('/etc/passwd').open('a') as stream:stream.write(f'{name}:x:{uid}:{uid}:Test:/home/{name}:/bin/sh\n')
    first=package.build(manager,output,'Local validation only <test@example.invalid>',1)
    second=package.build(manager,output,'Local validation only <test@example.invalid>',2)
    files=NativeGrantFiles();gate=NativePackageGate(files)
    payloads=package.payloads(manager);expected=package.expected_files(payloads)
    foreign=Path('/usr/share/dualsense-usb/window.py');foreign.parent.mkdir(parents=True,exist_ok=True);foreign.parent.chmod(0o755);foreign.write_text('unmanaged program\n')
    refused=install(first,False,initial=True)
    assert 'Unmanaged file already exists' in refused.stdout+refused.stderr,refused.stdout+refused.stderr
    assert foreign.read_text()=='unmanaged program\n' and not Path('/usr/libexec/dualsense-usb-helper').exists()
    foreign.unlink();cases.append('fresh install refuses unmanaged file collision')
    personal=Path('/home/alice/.config/dualsense-usb/controllers.json');personal.parent.mkdir(parents=True,exist_ok=True)
    personal.write_text('{"names":{"fixture":"Keep me"}}\n');personal_before=personal.read_bytes()
    legacy=Path('/home/alice/.local/share/applications/dualsense-usb.desktop');legacy.parent.mkdir(parents=True,exist_ok=True)
    legacy.write_text('legacy user shortcut\n')
    install(first,initial=True);gate.verify(expected)
    assert gate.state()['phase']=='ready' and revision().endswith('-1')
    run(['/usr/bin/dualsense-usb','--version'])
    run(['/usr/bin/dualsense-usb','--doctor','--no-session'])
    run(['desktop-file-validate','/usr/share/applications/dualsense-usb.desktop'])
    run(['systemd-analyze','--user','verify','/usr/lib/systemd/user/dualsense-usb-system.service'])
    cases.append('package-manager installation with dependency checking, fixed entrypoint, doctor, desktop and unit validation')
    for uid in (1000,1001):private_admin(uid,'install')
    grants={uid:files.read(files.relative('rule',uid)) for uid in (1000,1001)}
    held=subprocess.Popen(['/usr/bin/python3','-I','-c',
        "import sys;sys.path.insert(0,'/usr/share/dualsense-usb');from native_lifecycle import hold_native_package;hold_native_package("+repr(VERSION)+");print('held',flush=True);input()"],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert held.stdout.readline().strip()=='held'
        for operation in (lambda:install(second,False),lambda:remove(False)):
            result=operation();assert 'Uplugo is open' in result.stdout+result.stderr
            assert held.poll() is None and revision().endswith('-1')
            assert gate.state()['phase']=='ready';gate.verify(expected)
    finally:
        if held.poll() is None:held.communicate('\n',timeout=8)
    assert held.returncode==0;cases.append('live process prevents upgrade and removal without being killed or changing package files')
    install(second);assert revision().endswith('-2');gate.verify(expected)
    assert grants=={uid:files.read(files.relative('rule',uid)) for uid in grants}
    cases.append('upgrade preserves both account grants')
    gate.begin(manager,VERSION)
    refused=run(['/usr/bin/dualsense-usb','--doctor','--no-session'],False)
    assert refused.returncode==78 and 'maintenance' in refused.stderr
    refused=run(['/usr/bin/python3','-I','/usr/libexec/dualsense-usb-access','install'],False,env=dict(os.environ,PKEXEC_UID='1000'))
    assert 'maintenance' in refused.stderr
    install(second);assert gate.state()['phase']=='ready'
    cases.append('persistent maintenance gate blocks new entrypoints and admin; real reinstall recovers it')
    for name,code in [('native_lifecycle.py',78),('launch.py',1)]:
        path=Path('/usr/share/dualsense-usb')/name;saved=path.read_bytes();path.unlink()
        try:
            refused=run(['/usr/bin/dualsense-usb'],False)
            assert refused.returncode==code and ('native_lifecycle' if code==78 else 'launch.py') in refused.stderr
        finally:path.write_bytes(saved);path.chmod(0o644)
    gate.verify(expected)
    cases.append('standalone launcher explains missing gate or program files without importing the app; maintenance exits 78')
    if manager=='deb':
        run(['dpkg','--unpack',str(second)]);assert gate.state()['phase']=='maintenance'
        path=Path('/usr/share/dualsense-usb/window.py');saved=path.read_bytes();path.write_bytes(b'incomplete program\n')
        refused=run(['dpkg','--configure',package.NAME],False);assert 'missing or changed' in refused.stderr
        assert gate.state()['phase']=='maintenance'
        path.write_bytes(saved);run(['dpkg','--configure',package.NAME]);assert gate.state()['phase']=='ready'
        cases.append('unpack/configure failure stays blocked; verified repair completes configuration')
    custom=files.path(files.relative('rule',1002),create=True);custom.write_text('// administrator customization\n');custom.chmod(0o644)
    unknown=Path('/usr/share/dualsense-usb/local-note.txt');unknown.write_text('keep this unknown file\n')
    remove()
    assert gate.state()['phase']=='removed' and not Path('/usr/libexec/dualsense-usb-helper').exists()
    assert all(files.read(files.relative('rule',uid)) is None for uid in grants)
    assert custom.read_text()=='// administrator customization\n' and unknown.read_text()=='keep this unknown file\n'
    assert personal.read_bytes()==personal_before and legacy.read_text()=='legacy user shortcut\n'
    cases.append('remove clears canonical native grants and package files; custom rules, unknown files, user data and legacy shortcut preserved')
    install(second);gate.verify(expected)
    assert all(files.read(files.relative('rule',uid)) is None for uid in grants)
    remove()
    if manager=='deb':
        python=Path('/usr/bin/python3');saved_python=Path('/usr/bin/python3.package-test')
        python.rename(saved_python)
        try:run(['dpkg','--purge',package.NAME])
        finally:saved_python.rename(python)
        cases.append('purge after Python removal succeeds; grants were cleared before program removal')
    assert custom.exists() and personal.read_bytes()==personal_before
    cases.append('reinstall does not silently restore grants; second removal/purge is repeatable')
    result=dict(version=VERSION,manager=manager,ok=True,cases=cases,
        artifacts={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (first,second)},
        scope='Real package-manager transactions in a copied OS image and unprivileged user namespace. Administrative programs use synthetic PKEXEC_UID. No host root, real authentication, desktop login, USB or user-directory migration.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('NATIVE PACKAGE OK:',json.dumps(result),flush=True)


if __name__=='__main__':main()
