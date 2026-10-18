#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fake Snap/udev only in the marked disposable admin namespace."""
import json,os,sys
from pathlib import Path
assert os.geteuid()==0 and Path('/run/dualsense-native-admin-test').read_text()=='disposable namespace\n'
assert Path('/proc/self/uid_map').read_text().split()[1]!='0'
args=sys.argv[1:]
if Path(sys.argv[0]).name=='snap':
    assert args==['connections','steam']
    if Path('/run/steam-disconnected').exists():raise SystemExit(1)
    print('Interface Plug Slot Notes\nsteam-support steam:steam-support :steam-support -');raise SystemExit(0)
assert Path(sys.argv[0]).name=='udevadm'
with Path('/run/steam-commands.jsonl').open('a') as stream:stream.write(json.dumps(args)+'\n')
if args==['control','--reload-rules']:raise SystemExit(0)
assert len(args)==6 and args[0]=='trigger' and args[1] in ('--action=remove','--action=add')
assert args[2:4]==['--settle','--subsystem-match=hidraw']
node=Path(args[-1]);node.relative_to('/sys/devices/fixture')
assert args[4]=='--sysname-match='+node.name
props=dict(line.split('=',1) for line in (node/'device/uevent').read_text().splitlines() if '=' in line)
identity=props['HID_UNIQ'];device=(node/'dev').read_text().strip()
database=Path('/run/udev/data')/('c'+device);database.parent.mkdir(parents=True,exist_ok=True)
if args[1]=='--action=remove':
    database.unlink(missing_ok=True)
    flag=Path('/run/steam-fail-remove')
    if flag.exists():flag.unlink();raise SystemExit(1)
else:
    rule=Path('/etc/udev/rules.d')/('71-dualsense-usb-steam-'+identity.replace(':','')+'.rules')
    database.write_text('Q:snap_steam_steam\n' if rule.exists() or Path('/run/steam-external').exists() else '')
