#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build local experimental Debian/RPM artifacts. Never installs them."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
from app_info import VERSION
from build_helper import native_payloads, native_shared_source
from distribution import BASE, inventory, source_file

NAME='dualsense-usb'
PREFIX='usr/share/dualsense-usb/'
ENTRYPOINTS={'launch.py','window.py','setup.py','doctor.py','install.py','uninstall.py','recovery_ui.py','development.py'}
GRAPHICAL_ENTRYPOINTS={'launch.py','window.py','setup.py','recovery_ui.py','development.py'}
DEB_DEPENDS='python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, librsvg2-common, libusb-1.0-0, pkexec, polkitd, udev, kmod, ca-certificates'
RPM_DEPENDS='python3 >= 3.10, python3-gobject, gobject-introspection, gtk3, librsvg2, libusb1, polkit, systemd-udev, kmod, ca-certificates'


def native_version():return VERSION.replace('-','~',1)


def bootstrap(data,graphical=True):
    source=data.decode()
    # The notice is embedded, not imported from the possibly incomplete app.
    # Catch even a missing/syntax-broken gate module before normal app imports.
    notice=(BASE/'startup_notice.py').read_text()
    guard="\nif __name__ == '__main__':\n    def _native_entry_guard():\n        import sys\n        sys.dont_write_bytecode=True\n        try:\n            from native_lifecycle import hold_native_package\n            hold_native_package("+repr(VERSION)+")\n        except Exception as exc:\n"
    guard+=textwrap.indent(notice,'            ')
    guard+='\n            raise SystemExit(report_startup_failure(exc, graphical='+repr(graphical)+", retry=[sys.executable, __file__, *sys.argv[1:]]))\n    _native_entry_guard()\n    del _native_entry_guard\n"
    first,separator,rest=source.partition('\n')
    result=(first+'\n'+guard+rest) if first.startswith('#!') else guard+source
    ast.parse(result)
    return result.encode()


def launcher_source():
    # Remains able to report missing app files, even if launch.py or the shared
    # startup notice module has been removed during an interrupted transaction.
    code='#!/usr/bin/python3\n'+(BASE/'startup_notice.py').read_text()+'''

def native_launch():
    arguments = sys.argv[1:]
    if arguments == ['--version']:
        print('''+repr(VERSION)+'''); return 0
    if not arguments: entry, extra, graphical = 'launch.py', [], True
    elif arguments == ['--setup']: entry, extra, graphical = 'setup.py', [], True
    elif arguments[0] == '--doctor': entry, extra, graphical = 'doctor.py', arguments[1:], False
    else:
        print('Usage: dualsense-usb [--setup | --doctor | --version]', file=sys.stderr)
        return 2
    retry = [sys.executable, __file__, *arguments]
    sys.dont_write_bytecode = True
    sys.path.insert(0, '/usr/share/dualsense-usb')
    try:
        from native_lifecycle import hold_native_package
        hold_native_package('''+repr(VERSION)+''')
    except Exception as exc:
        return report_startup_failure(exc, graphical=graphical, retry=retry)
    try:
        import runpy
        path = '/usr/share/dualsense-usb/' + entry
        sys.argv = [path, *extra]
        runpy.run_path(path, run_name='__main__')
    except Exception as exc:
        return report_startup_failure(exc, reason='launch', graphical=graphical, retry=retry)
    return 0

if __name__ == '__main__': raise SystemExit(native_launch())
'''
    ast.parse(code)
    return code.encode()


def payloads(manager):
    if manager not in ('deb','rpm'):raise ValueError('Unknown package format')
    files={PREFIX+name:(bootstrap(source_file(BASE,name).read_bytes(),name in GRAPHICAL_ENTRYPOINTS) if name in ENTRYPOINTS else source_file(BASE,name).read_bytes(),0o644)
           for name in inventory()['runtime']}
    files[PREFIX+'system-package.json']=((json.dumps(dict(format=1,manager=manager,version=VERSION),sort_keys=True)+'\n').encode(),0o644)
    files.update(native_payloads())
    files['usr/bin/dualsense-usb']=(launcher_source(),0o755)
    files['usr/share/applications/dualsense-usb.desktop']=(b'''[Desktop Entry]
Type=Application
Name=Uplugo
Comment=Play, charge and customize your DualSense controllers
Comment[pt_BR]=Jogue, carregue e personalize seus controles DualSense
Comment[es]=Juega, carga y personaliza tus mandos DualSense
Exec=/usr/bin/dualsense-usb
TryExec=/usr/bin/dualsense-usb
Icon=dualsense-usb
Terminal=false
Categories=Game;Utility;
Keywords=DualSense;PS5;USB;controller;
StartupWMClass=dualsense-usb
Actions=Setup;

[Desktop Action Setup]
Name=Manage installation
Name[pt_BR]=Gerenciar instala\xc3\xa7\xc3\xa3o
Name[es]=Gestionar instalaci\xc3\xb3n
Exec=/usr/bin/dualsense-usb --setup
''',0o644)
    files['usr/share/icons/hicolor/scalable/apps/dualsense-usb.svg']=((BASE/'assets/dualsense-usb.svg').read_bytes(),0o644)
    files['usr/lib/systemd/user/dualsense-usb-system.service']=(b'''[Unit]
Description=Uplugo controller manager
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=notify
NotifyAccess=main
ExecStart=/usr/bin/python3 /usr/share/dualsense-usb/window.py
Restart=on-failure
RestartSec=2
RestartPreventExitStatus=78
TimeoutStopSec=15
KillMode=mixed
''',0o644)
    files['usr/lib/modules-load.d/dualsense-usb.conf']=(b'uhid\n',0o644)
    for name in ('LICENSE','THIRD_PARTY.md'):
        files['usr/share/doc/dualsense-usb/'+name]=((BASE/name).read_bytes(),0o644)
    files['usr/share/doc/dualsense-usb/blueprint-license.txt']=((BASE/'assets/dualsense-blueprint.LICENSE.txt').read_bytes(),0o644)
    return files


def expected_files(files):
    # RPM/DNF support nodocs (the Fedora container default). These are duplicate
    # reference documents; runtime licenses and required assets remain in PREFIX.
    return {name:(hashlib.sha256(data).hexdigest(),mode) for name,(data,mode) in files.items()
            if not name.startswith('usr/share/doc/')}


def maintainer_script(manager,phase,expected):
    code='#!/usr/bin/python3 -I\n'+native_shared_source()+'\nimport sys\n'
    code+="if os.geteuid()!=0:raise SystemExit('Package maintenance requires root.')\n"
    code+='gate=NativePackageGate()\nmanager='+repr(manager)+'\nversion='+repr(VERSION)+'\n'
    code+='expected='+repr(expected)+'\nargument=sys.argv[1] if len(sys.argv)>1 else ""\n'
    actions={
        ('deb','preinst'):"if argument in ('install','upgrade'):gate.begin(manager,version,expected)",
        ('deb','prerm'):"if argument=='remove':gate.prepare_remove(manager,version)\n    elif argument in ('upgrade','deconfigure','failed-upgrade'):gate.begin(manager,version)",
        ('deb','postinst'):"if argument in ('configure','abort-upgrade','abort-remove','abort-deconfigure'):gate.finish(manager,version,expected)",
        ('deb','postrm'):"if argument in ('remove','purge','disappear'):gate.removed(manager,version)",
        ('rpm','pre'):"gate.begin(manager,version,expected)",
        ('rpm','posttrans'):"gate.finish(manager,version,expected)",
        ('rpm','preun'):"if argument=='0':gate.prepare_remove(manager,version)",
        ('rpm','postun'):"if argument=='0':gate.removed(manager,version)",
    }
    code+='try:\n    '+actions[(manager,phase)]+'\nexcept Exception as exc:raise SystemExit(str(exc))\n'
    if phase in ('postinst','posttrans','postrm','postun'):
        code+='''
# Offline installations have no udev daemon. Reload existing rules only;
# do not trigger, detach, restart or claim connected controllers here.
if Path('/run/udev/control').exists():
    import subprocess
    try:subprocess.run(['udevadm','control','--reload-rules'],check=False,timeout=5)
    except (OSError,subprocess.TimeoutExpired):pass
'''
    ast.parse(code)
    return code


def write_tree(destination,files):
    destination.mkdir(parents=True,exist_ok=False)
    for name,(data,mode) in files.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data);path.chmod(mode)
    for path in destination.rglob('*'):
        if path.is_dir():path.chmod(0o755)
    destination.chmod(0o755)


def check_metadata(maintainer,revision):
    if not re.fullmatch(r'[^<>\r\n%]+ <[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+>',maintainer):raise ValueError('Use maintainer Name <email>, without newlines or macros.')
    if type(revision) is not int or not 1<=revision<=9999:raise ValueError('Invalid package revision')


def build(manager,output,maintainer,revision=1):
    check_metadata(maintainer,revision)
    files=payloads(manager);expected=expected_files(files)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,SOURCE_DATE_EPOCH='0')
    with tempfile.TemporaryDirectory(prefix='dualsense-native-build-') as temporary:
        temporary=Path(temporary);stage=temporary/'payload';write_tree(stage,files)
        if manager=='deb':
            control=stage/'DEBIAN';control.mkdir(mode=0o755)
            (control/'control').write_text(f'''Package: {NAME}
Version: {native_version()}-{revision}
Architecture: all
Section: games
Priority: optional
Maintainer: {maintainer}
Pre-Depends: python3 (>= 3.10)
Depends: {DEB_DEPENDS}
Recommends: libayatana-appindicator3-1
Installed-Size: {sum(len(data) for data,mode in files.values())//1024+1}
Description: Uplugo controller manager (experimental)
 Play through a virtual controller, use native game access, or charge with
 exclusive USB ownership. Includes lights, rumble, trigger effects and tests.
''')
            (control/'control').chmod(0o644)
            for phase in ('preinst','postinst','prerm','postrm'):
                script=maintainer_script(manager,phase,expected)
                if phase=='postrm':
                    # postrm purge may run after Python was removed. Canonical
                    # grants are already revoked in prerm, before file removal.
                    script='#!/bin/sh\nset -e\nif ! command -v python3 >/dev/null 2>&1; then\n  printf "%s\\n" "Uplugo program removed; retaining maintenance records because Python is unavailable."\n  exit 0\nfi\nexec python3 -I - "$@" <<\'DUALSENSE_PACKAGE_SCRIPT\'\n'+script.partition('\n')[2]+'\nDUALSENSE_PACKAGE_SCRIPT\n'
                path=control/phase;path.write_text(script);path.chmod(0o755)
            for path in stage.rglob('*'):os.utime(path,(0,0))
            artifact=output/f'{NAME}_{native_version()}-{revision}_all.deb'
            subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(artifact)],env=env,check=True)
        else:
            top=temporary/'rpm'
            for name in ('SOURCES','SPECS','BUILD','BUILDROOT','RPMS','SRPMS'):(top/name).mkdir(parents=True)
            with tarfile.open(top/'SOURCES/payload.tar','w') as tar:
                for name,(data,mode) in sorted(files.items()):
                    info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;info.mtime=0
                    tar.addfile(info,io.BytesIO(data))
            spec=f'''Name: {NAME}
Version: {native_version()}
Release: {revision}
Summary: Uplugo controller manager (experimental)
License: GPL-3.0-only AND MIT
Packager: {maintainer}
BuildArch: noarch
AutoReqProv: no
Source0: payload.tar
Requires: {RPM_DEPENDS}
Requires(pre): python3 >= 3.10
Requires(posttrans): python3 >= 3.10
Requires(preun): python3 >= 3.10
Requires(postun): python3 >= 3.10
Recommends: libayatana-appindicator-gtk3
%global __brp_python_bytecompile %{{nil}}
%undefine __brp_linkdupes
%global debug_package %{{nil}}

%description
Play through a virtual controller, use native game access, or charge with
exclusive USB ownership. Includes lights, rumble, trigger effects and tests.

%prep
%build
%install
mkdir -p "%{{buildroot}}"
tar -xf "%{{SOURCE0}}" -C "%{{buildroot}}"
'''
            for phase in ('pre','posttrans','preun','postun'):
                # RPM performs macro expansion even inside Python string literals.
                body=maintainer_script(manager,phase,expected).partition('\n')[2].replace('%','%%')
                spec+='\n%'+phase+' -p /usr/bin/python3\n'+body
            owned={str(parent) for name in files for parent in Path(name).parents
                   if str(parent)=='usr/share/dualsense-usb' or str(parent).startswith(PREFIX) or str(parent)=='usr/share/doc/dualsense-usb'}
            spec+='\n%files\n%defattr(-,root,root,-)\n'+'\n'.join('%dir /'+name for name in sorted(owned))+'\n'
            spec+='\n'.join('/'+name for name in sorted(files))+'\n'
            path=top/'SPECS/dualsense-usb.spec';path.write_text(spec)
            subprocess.run(['rpmbuild','-bb','--define','_topdir '+str(top),str(path)],env=env,check=True)
            built=list((top/'RPMS').rglob('*.rpm'))
            if len(built)!=1:raise ValueError('Expected one noarch RPM')
            artifact=output/built[0].name;shutil.copyfile(built[0],artifact)
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.with_name(artifact.name+'.sha256').write_text(digest+'  '+artifact.name+'\n')
    print(artifact)
    return artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('format',choices=['deb','rpm'])
    parser.add_argument('--output',type=Path,default=BASE/'dist/native')
    parser.add_argument('--maintainer',required=True,help='Name <email>; use a clearly synthetic identity for private tests only')
    parser.add_argument('--revision',type=int,default=1)
    args=parser.parse_args()
    build(args.format,args.output,args.maintainer,args.revision)


if __name__=='__main__':main()
