# SPDX-License-Identifier: GPL-3.0-only
"""Execute generated admin programs inside an unprivileged disposable namespace.

The supplied rootfs stays read-only. /etc, /var, /run, sysfs, package output
directories and the password database are private. No host bus/network/devices.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rootfs',type=Path)
    parser.add_argument('--touchpad',action='store_true',help='Exercise generated touchpad administrators with synthetic input nodes and a private udev simulator.')
    parser.add_argument('--steam-access',action='store_true',help='Exercise Steam access administrators with private Snap/udev fixtures.')
    args=parser.parse_args()
    if args.touchpad and args.steam_access:parser.error('Select one administrator fixture.')
    if os.geteuid()==0:parser.error('Run as a regular user, not root.')
    root=args.rootfs.resolve();source=Path(__file__).resolve().parents[1]
    if not (root/'usr/bin/python3').exists():parser.error('Missing /usr/bin/python3 in rootfs')
    with tempfile.TemporaryDirectory(prefix='dualsense-admin-namespace-') as temporary:
        data=Path(temporary)
        (data/'marker').write_text('disposable namespace\n')
        (data/'passwd').write_text('root:x:0:0:Root:/root:/bin/sh\nalice:x:1000:1000:Alice:/home/alice:/bin/sh\nbob:x:1001:1001:Bob:/home/bob:/bin/sh\n')
        (data/'group').write_text('root:x:0:\nalice:x:1000:\nbob:x:1001:\n')
        (data/'nsswitch.conf').write_text('passwd: files\ngroup: files\nhosts: files\n')
        if args.touchpad:
            fixture=data/'udevadm';fixture.write_bytes((source/'tests/touchpad_udev_fixture.py').read_bytes());fixture.chmod(0o755)
        if args.steam_access:
            fixture=data/'steam-fixture';fixture.write_bytes((source/'tests/steam_access_fixture.py').read_bytes());fixture.chmod(0o755)
        command=['bwrap','--unshare-all','--die-with-parent','--new-session','--uid','0','--gid','0',
            '--ro-bind',str(root),'/', '--dev','/dev','--proc','/proc','--tmpfs','/tmp',
            '--ro-bind',str(source),'/tmp/source','--tmpfs','/run','--tmpfs','/var','--tmpfs','/sys',
            '--dir','/sys/bus/usb/devices','--tmpfs','/home','--tmpfs','/root',
            '--tmpfs','/etc','--tmpfs','/usr']
        for entry in sorted((root/'usr').iterdir()):
            if entry.name in ('libexec','lib','share') or (args.steam_access and entry.name=='bin'):continue
            command+=['--ro-bind',str(entry),'/usr/'+entry.name]
        # OCI layers were extracted without privileges and may have inherited
        # the host umask on intermediate directories. Create protected package
        # ancestors privately; do not chmod or otherwise mutate the rootfs.
        command+=['--dir','/usr/libexec','--dir','/usr/lib','--dir','/usr/share']
        for entry in sorted((root/'usr/lib').iterdir()):
            if entry.name!='udev':command+=['--ro-bind',str(entry),'/usr/lib/'+entry.name]
        command+=['--dir','/usr/share/polkit-1/actions','--dir','/usr/lib/udev/rules.d']
        for name in ('passwd','group','nsswitch.conf'):
            # passwd is writable for the rename fixture; copies are private.
            command+=['--bind',str(data/name),'/etc/'+name]
        command+=['--ro-bind',str(data/'marker'),'/run/dualsense-native-admin-test',
            '--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/root',
            '--setenv','LANG','C.UTF-8','--setenv','PYTHONDONTWRITEBYTECODE','1',
            '--chdir','/tmp/source']
        if args.touchpad:command+=['--ro-bind',str(data/'udevadm'),'/usr/bin/udevadm']
        if args.steam_access:
            command+=['--dir','/usr/bin','--ro-bind',str((root/'usr/bin/python3').resolve()),'/usr/bin/python3',
                      '--ro-bind',str(data/'steam-fixture'),'/usr/bin/snap','--ro-bind',str(data/'steam-fixture'),'/usr/bin/udevadm']
        command+=['/usr/bin/python3','tests/steam_access_admin_smoke.py' if args.steam_access else ('tests/touchpad_admin_smoke.py' if args.touchpad else 'tests/native_admin_smoke.py')]
        return subprocess.run(command).returncode


if __name__=='__main__':raise SystemExit(main())
