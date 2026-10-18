# SPDX-License-Identifier: GPL-3.0-only
"""Best-effort detection of other user processes with a controller open.

A denied open() leaves no descriptor and cannot be detected here. This observer
is not an input firewall; exclusive charging is what hides the controller.
"""
import os
import time
from pathlib import Path


def controller_nodes(device, identity, sys_class=Path('/sys/class')):
    physical=device.resolve()
    uniq=identity.removeprefix('hid:').lower()
    def matches(entry):
        path=entry.resolve()
        if physical in path.parents:return True
        if not identity.startswith('hid:'):return False
        for parent in path.parents:
            if parent.name.startswith('0003:054C:'):
                try:
                    values=dict(line.split('=',1) for line in (parent/'uevent').read_text().splitlines() if '=' in line)
                    return values.get('HID_UNIQ','').lower()==uniq
                except OSError:return False
        return False
    nodes=set()
    for kind,pattern in [('hidraw','hidraw*'),('input','event*'),('input','js*')]:
        for entry in (sys_class/kind).glob(pattern):
            if matches(entry):nodes.add('/dev/'+('input/' if kind=='input' else '')+entry.name)
    try:
        nodes.add(f"/dev/bus/usb/{int((device/'busnum').read_text()):03}/{int((device/'devnum').read_text()):03}")
    except (OSError,ValueError):pass
    return nodes


def active_clients(targets, proc=Path('/proc'), own_pid=None):
    own_pid=os.getpid() if own_pid is None else own_pid
    clients=set()
    if not targets:return clients
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name)==own_pid:continue
        try:
            # Only the user's desktop applications, never inspect other users.
            if process.stat().st_uid!=os.getuid():continue
            for descriptor in (process/'fd').iterdir():
                try:target=os.readlink(descriptor)
                except OSError:continue
                if target.removesuffix(' (deleted)') in targets:
                    name=(process/'comm').read_text().strip()
                    clients.add(''.join(c for c in name if c.isprintable())[:60] or 'Outro aplicativo')
                    break
        except (OSError,PermissionError):continue
    return clients


class AccessGuard:
    def __init__(self):self.next_scan=0

    def check(self, devices, identities, preferences, now=None):
        now=time.monotonic() if now is None else now
        if not preferences.get('enabled') or now<self.next_scan:return {}
        self.next_scan=now+2
        paused=preferences.get('play_exceptions',[])
        targets={}
        for device in devices:
            identity=identities.get(device.name)
            if identity and identity not in paused:
                targets[identity]=controller_nodes(device,identity)
        # Associate accesses with the matching physical controller only.
        if not targets:return {}
        result={}
        for identity,nodes in targets.items():
            clients=active_clients(nodes)
            if clients:result[identity]=', '.join(sorted(clients))
        return result
