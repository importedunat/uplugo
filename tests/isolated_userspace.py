#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run userspace checks in an already provisioned Linux rootfs, without root.

Requires bubblewrap on the host. The image needs Python/GTK app dependencies,
D-Bus, Xvfb, xauth, desktop-file-utils and systemd-analyze (unit validation only).
The rootfs and checkout are mounted read-only; no host USB, bus, network or home.
This is not a polkit, USB passthrough or graphical-login certification.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rootfs',type=Path)
    parser.add_argument('--report',type=Path,help='Save results to this host file.')
    args=parser.parse_args()
    root=args.rootfs.resolve()
    if not (root/'usr/bin/python3').exists():parser.error('rootfs sem /usr/bin/python3')
    source=Path(__file__).resolve().parents[1]
    report_args=[]
    mounts=[]
    if args.report:
        report=args.report.resolve()
        report.parent.mkdir(parents=True,exist_ok=True)
        report.touch()
        mounts=['--bind',str(report),'/run/results.json']
        report_args=['--report','/run/results.json']
    command=['bwrap','--unshare-all','--die-with-parent','--new-session',
             '--uid',str(os.getuid()),'--gid',str(os.getgid()),
             '--ro-bind',str(root),'/',
             '--dev','/dev','--proc','/proc','--tmpfs','/tmp',
             '--ro-bind',str(source),'/tmp/source','--tmpfs','/run',*mounts,
             '--tmpfs','/home','--dir','/home/tester','--tmpfs','/sys',
             '--clearenv','--setenv','PATH','/usr/bin:/bin:/usr/sbin:/sbin',
             '--setenv','HOME','/home/tester','--setenv','LANG','C.UTF-8',
             '--setenv','XDG_RUNTIME_DIR','/tmp/runtime','--setenv','GDK_BACKEND','x11',
             '--setenv','GIO_USE_VFS','local','--setenv','NO_AT_BRIDGE','1',
             '--setenv','PYTHONDONTWRITEBYTECODE','1','--chdir','/tmp/source',
             '/usr/bin/python3','tests/run_userspace.py',*report_args]
    # D-Bus resolves the current UID through the guest password database.
    # Minimal images need not contain the host's UID; don't modify the image
    # or copy the host's users into it just to run the GUI tests.
    with tempfile.TemporaryDirectory(prefix='dualsense-test-account-') as temporary:
        account_mounts=[]
        for filename,number,entry in (
                ('passwd',os.getuid(),f'dualsense-test-{os.getuid()}:x:{os.getuid()}:{os.getgid()}:Test:/home/tester:/bin/sh'),
                ('group',os.getgid(),f'dualsense-test-{os.getgid()}:x:{os.getgid()}:')):
            content=(root/'etc'/filename).read_text()
            if not any(len(fields:=line.split(':'))>2 and fields[2]==str(number) for line in content.splitlines()):
                content=content.rstrip()+'\n'+entry+'\n'
            path=Path(temporary)/filename;path.write_text(content)
            account_mounts+=['--ro-bind',str(path),'/etc/'+filename]
        executable=command.index('/usr/bin/python3')
        command[executable:executable]=account_mounts
        return subprocess.run(command).returncode


if __name__=='__main__':raise SystemExit(main())
