#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Private udev simulator, executable only in the marked namespace fixture."""
import json
import os
from pathlib import Path
import sys
assert os.geteuid()==0 and Path('/run/dualsense-native-admin-test').read_text()=='disposable namespace\n'
assert Path('/proc/self/uid_map').read_text().split()[1]!='0'
args=sys.argv[1:]
with Path('/run/touchpad-commands.jsonl').open('a') as log:log.write(json.dumps(args)+'\n')
if args==['control','--reload-rules']:raise SystemExit(0)
assert len(args)==6 and args[0]=='trigger' and args[1] in ('--action=remove','--action=add')
assert args[2:4]==['--settle','--subsystem-match=input']
node=Path(args[-1]);node.relative_to('/sys/devices/fixture/input')
assert args[4]=='--sysname-match='+node.name and node.name.startswith('event')
identity=(node/'device/uniq').read_text().strip();device=(node/'dev').read_text().strip()
database=Path('/run/udev/data')/('c'+device);database.parent.mkdir(parents=True,exist_ok=True)
if args[1]=='--action=remove':
    database.unlink(missing_ok=True)
    flag=Path('/run/touchpad-fail-remove')
    if flag.exists():flag.unlink();raise SystemExit(1)
else:
    rule=Path('/etc/udev/rules.d')/('99-dualsense-usb-touchpad-'+identity.replace(':','')+'.rules')
    database.write_text('E:ID_INPUT_TOUCHPAD=1\n'+('E:LIBINPUT_IGNORE_DEVICE=1\n' if rule.exists() else ''))
