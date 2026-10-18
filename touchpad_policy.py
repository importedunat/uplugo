# SPDX-License-Identifier: GPL-3.0-only
"""Fixed DualSense pointer policy and read-only discovery. No input is grabbed.

The udev property excludes only libinput's pointer consumer. HID reports and
evdev capabilities are not changed. Steam mappings remain independent.
"""
import os
from pathlib import Path
import re
import stat

TOUCHPAD_ADMIN='usr/libexec/dualsense-usb-touchpad'
TOUCHPAD_POLICY='usr/share/polkit-1/actions/org.local.dualsense.usb.touchpad.policy'
TOUCHPAD_RULES='etc/udev/rules.d'
TOUCHPAD_LOCK='run/dualsense-usb/touchpad.lock'
TOUCHPAD_PRODUCTS=('0ce6','0df2')


def touchpad_identity(value):
    if not isinstance(value,str):raise ValueError('identity')
    for prefix in ('hid:','serial:'):
        if value.startswith(prefix):value=value[len(prefix):];break
    value=value.lower()
    if re.fullmatch('[0-9a-f]{12}',value):value=':'.join(value[i:i+2] for i in range(0,12,2))
    if not re.fullmatch('[0-9a-f]{2}(:[0-9a-f]{2}){5}',value):raise ValueError('identity')
    return value


def touchpad_rule_path(identity):
    return TOUCHPAD_RULES+'/99-dualsense-usb-touchpad-'+touchpad_identity(identity).replace(':','')+'.rules'


def touchpad_rule(identity):
    identity=touchpad_identity(identity)
    header='# DualSense USB touchpad policy v1; computer-wide for this controller.\n'
    return (header+''.join('ACTION!="remove", SUBSYSTEM=="input", KERNEL=="event[0-9]*", '
        'ATTRS{id/bustype}=="0003", ATTRS{id/vendor}=="054c", ATTRS{id/product}=="'+product+'", '
        'ATTRS{name}=="*DualSense*Touchpad", ATTRS{uniq}=="'+identity+'", '
        'ENV{LIBINPUT_IGNORE_DEVICE}="1"\n' for product in TOUCHPAD_PRODUCTS)).encode()


def touchpad_read(path,limit=65536):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('unexpected-file')
        data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('unexpected-file')
    return data


def touchpad_matches(event,identity):
    try:
        device=event/'device'
        def attr(name):return touchpad_read(device/name,4096).decode().strip()
        return (attr('id/bustype')=='0003' and attr('id/vendor')=='054c' and
            attr('id/product') in TOUCHPAD_PRODUCTS and attr('uniq').lower()==touchpad_identity(identity) and
            'DualSense' in attr('name') and attr('name').endswith(' Touchpad'))
    except (OSError,ValueError,UnicodeError):return False


def touchpad_nodes(identity,sys_root=Path('/sys')):
    identity=touchpad_identity(identity);directory=Path(sys_root)/'class/input'
    if not directory.is_dir():return []
    return [path for path in sorted(directory.iterdir()) if re.fullmatch('event[0-9]+',path.name) and touchpad_matches(path,identity)]


def touchpad_snapshot(identity,root=Path('/'),sys_root=Path('/sys')):
    identity=touchpad_identity(identity);root=Path(root)
    try:
        data=touchpad_read(root/touchpad_rule_path(identity),4096)
        saved='game' if data==touchpad_rule(identity) else 'custom'
    except FileNotFoundError:saved='system'
    except (OSError,ValueError):saved='custom'
    nodes=[]
    for path in touchpad_nodes(identity,sys_root):
        ignored=None
        try:
            device=touchpad_read(path/'dev',4096).decode().strip()
            if re.fullmatch('[0-9]+:[0-9]+',device):
                text=touchpad_read(root/'run/udev/data'/('c'+device)).decode()
                props=dict(line[2:].split('=',1) for line in text.splitlines() if line.startswith('E:') and '=' in line)
                ignored=props.get('LIBINPUT_IGNORE_DEVICE','0')!='0'
        except (OSError,ValueError,UnicodeError):pass
        nodes.append({'event':path.name,'ignored':ignored})
    # This is the udev database, not proof of what an already-open compositor
    # or Steam currently does. UI must keep that distinction visible.
    return {'identity':identity,'saved':saved,'nodes':nodes}
