# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, fixed-scope Steam Snap grant. Never launches Steam or resets USB."""
import json
import os
import pwd
import re
import stat
from pathlib import Path
from touchpad_policy import touchpad_identity
from touchpad_admin import TouchpadAdmin
from steam_access import (STEAM_HELPERS,steam_rule_path,steam_rule,steam_environment,steam_nodes,steam_matches)


class SteamAccessAdmin(TouchpadAdmin):
    # Use the same protected filesystem transaction and lock as pointer policy:
    # only one device-permission operation may run at a time.
    def refresh(self,identity):
        self.command('control','--reload-rules')
        count=0
        for node in steam_nodes(identity,self.sys_root):
            try:node=node.resolve(strict=True)
            except FileNotFoundError:continue
            node.relative_to(self.sys_root.resolve())
            if not steam_matches(node,identity):continue
            filters=['--settle','--subsystem-match=hidraw','--sysname-match='+node.name,str(node)]
            # Remove/add updates Snap's device filter on both grant and revoke.
            # This is a udev notification, never USB unbind/reset or input grab.
            try:self.command('trigger','--action=remove',*filters)
            finally:
                if steam_matches(node,identity):self.command('trigger','--action=add',*filters)
            count+=1
        return count

    def apply(self,identity,choice):
        identity=touchpad_identity(identity)
        if choice not in ('allow','system'):raise ValueError('choice')
        relative=steam_rule_path(identity)
        with self.lock():
            before=self.read(relative)
            if before is not None and before[0] not in [steam_rule(identity,h) for h in STEAM_HELPERS]:raise ValueError('custom-rule')
            desired=None
            if choice=='allow':
                snap=self.path('usr/bin/snap')
                try:info=snap.lstat()
                except FileNotFoundError:raise ValueError('no-snap') from None
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022 or not info.st_mode&0o111:raise ValueError('snap-helper')
                environment=steam_environment(self.root,self.runner)
                if not environment['available']:raise ValueError(environment['reason'])
                helper=environment['helper'];path=self.path(helper);info=path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_mode&0o022 or not info.st_mode&0o111:raise ValueError('snap-helper')
                desired=(steam_rule(identity,helper),0o644)
            try:
                if before!=desired:self.write(relative,desired)
                count=self.refresh(identity)
            except Exception as exc:
                try:self.write(relative,before);self.refresh(identity)
                except Exception:raise RuntimeError('recovery-needed') from exc
                raise RuntimeError('apply-failed-restored') from exc
        return {'choice':choice,'refreshed':count,'pending':count==0}


def steam_access_main(arguments):
    if os.geteuid()!=0:raise ValueError('authorization')
    uid=os.environ.get('PKEXEC_UID','')
    if not re.fullmatch('[1-9][0-9]{0,9}',uid) or int(uid)>=2**32-1:raise ValueError('authorization')
    pwd.getpwuid(int(uid))
    if len(arguments)!=2 or arguments[0] not in ('allow','system'):raise ValueError('choice')
    print(json.dumps(SteamAccessAdmin().apply(arguments[1],arguments[0])))
