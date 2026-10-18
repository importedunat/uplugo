# SPDX-License-Identifier: GPL-3.0-only
"""Per-controller Steam Snap device tagging. Discovery never opens HID or Steam."""
import os
from pathlib import Path
import re
import stat
import subprocess
from touchpad_policy import touchpad_identity,touchpad_read

STEAM_ADMIN='usr/libexec/dualsense-usb-steam-access'
STEAM_POLICY='usr/share/polkit-1/actions/org.local.dualsense.usb.steam-access.policy'
STEAM_HELPERS=('usr/lib/snapd/snap-device-helper','usr/libexec/snapd/snap-device-helper')
STEAM_TAG='snap_steam_steam'


def steam_rule_path(identity):
    return 'etc/udev/rules.d/71-dualsense-usb-steam-'+touchpad_identity(identity).replace(':','')+'.rules'


def steam_rule(identity,helper):
    identity=touchpad_identity(identity)
    if helper not in STEAM_HELPERS:raise ValueError('snap-helper')
    header='# DualSense USB Steam Snap access v1; computer-wide for this controller.\n'
    rule=''
    for product in ('0CE6','0DF2'):
        match='ACTION!="remove", SUBSYSTEM=="hidraw", KERNELS=="0003:054C:'+product+'.*", '
        rule+=match+'IMPORT{parent}="HID_UNIQ"\n'
        rule+=match+'ENV{HID_UNIQ}=="'+identity+'", TAG+="'+STEAM_TAG+'"\n'
    rule+='TAG=="'+STEAM_TAG+'", SUBSYSTEM=="hidraw", RUN+="/'+helper+' $env{ACTION} '+STEAM_TAG+' $devpath $major:$minor"\n'
    return (header+rule).encode()


def steam_matches(node,identity):
    try:
        text=touchpad_read(node/'device/uevent',4096).decode()
        props=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
        return (props.get('HID_ID') in ('0003:0000054C:00000CE6','0003:0000054C:00000DF2') and
                props.get('HID_UNIQ','').lower()==touchpad_identity(identity))
    except (OSError,ValueError,UnicodeError):return False


def steam_nodes(identity,sys_root=Path('/sys')):
    identity=touchpad_identity(identity);folder=Path(sys_root)/'class/hidraw'
    if not folder.is_dir():return []
    return [node for node in sorted(folder.iterdir()) if re.fullmatch('hidraw[0-9]+',node.name) and steam_matches(node,identity)]


def steam_connections(text):
    return any(len(fields:=line.split())>=3 and fields[0]=='steam-support' and
               fields[1]=='steam:steam-support' and fields[2]==':steam-support' for line in text.splitlines())


def steam_environment(root=Path('/'),runner=None):
    root=Path(root);runner=runner or subprocess.run
    helper=next((name for name in STEAM_HELPERS if (root/name).is_file()),None)
    if not (root/'usr/bin/snap').is_file():return {'available':False,'reason':'no-snap','helper':helper}
    try:
        result=runner([str(root/'usr/bin/snap'),'connections','steam'],stdin=subprocess.DEVNULL,
                      capture_output=True,text=True,timeout=10,env=dict(os.environ,LC_ALL='C'))
        connected=result.returncode==0 and steam_connections(result.stdout)
        reason='ready' if connected and helper else ('snap-helper' if connected else 'snap-connection')
    except (OSError,subprocess.TimeoutExpired):reason='snap-unavailable'
    return {'available':reason=='ready','reason':reason,'helper':helper}


def steam_snapshot(identity,root=Path('/'),sys_root=Path('/sys'),runner=None):
    identity=touchpad_identity(identity);root=Path(root)
    try:
        data=touchpad_read(root/steam_rule_path(identity),4096)
        saved='allow' if data in [steam_rule(identity,h) for h in STEAM_HELPERS] else 'custom'
    except FileNotFoundError:saved='system'
    except (OSError,ValueError):saved='custom'
    nodes=[]
    for node in steam_nodes(identity,sys_root):
        tagged=None
        try:
            device=touchpad_read(node/'dev',4096).decode().strip()
            if re.fullmatch('[0-9]+:[0-9]+',device):
                lines=touchpad_read(root/'run/udev/data'/('c'+device)).decode().splitlines()
                tagged=('Q:'+STEAM_TAG in lines) # Current tags, not historical G: tags.
        except (OSError,ValueError,UnicodeError):pass
        nodes.append({'node':node.name,'tagged':tagged})
    return {'identity':identity,'saved':saved,'nodes':nodes,'environment':steam_environment(root,runner)}
