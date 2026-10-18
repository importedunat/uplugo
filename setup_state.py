# SPDX-License-Identifier: GPL-3.0-only
"""Read-only setup preview and fixed commands; existing installers own writes."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import tempfile
from distribution import inventory, source_file
from maintenance import Locations, no_links, removal_plan, running_app
from doctor import checks
from dualsense import xdg_directory
from session import systemd_available
from deployment import inspect_deployment, legacy_conflicts, require_user_maintenance
from app_info import VERSION
from i18n import _

BASE=Path(__file__).resolve().parent


def spawn_logged(command,log_name,**kwargs):
    folder=xdg_directory('XDG_STATE_HOME','.local/state')/'dualsense-usb'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temporary=tempfile.mkstemp(prefix='.setup-launch-',dir=folder)
    try:
        with os.fdopen(fd,'w') as log:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                                     start_new_session=True,**kwargs)
        os.replace(temporary,folder/log_name)
    finally:Path(temporary).unlink(missing_ok=True)
    return process


def launch_assistant(directory=BASE):
    """Give setup its own lifecycle so quitting the app cannot kill maintenance."""
    if os.geteuid()==0:raise ValueError('Run as your own user, without sudo.')
    directory=Path(directory).resolve()
    if not (directory/'setup.py').is_file():raise FileNotFoundError(directory/'setup.py')
    command=['/usr/bin/python3','setup.py']
    if systemd_available():
        # A new POSIX session alone does not escape the app service's cgroup.
        # A scope inherits the desktop environment while surviving that service.
        # Relative script + explicit cwd keep $, %, spaces literal in paths, even
        # across systemd versions with different argument-expansion defaults.
        command=['systemd-run','--user','--scope','--quiet','--collect','--',*command]
    return spawn_logged(command,'setup-assistant.log',cwd=directory)


@dataclass
class Overview:
    destination: str=''
    version: str=''
    installed: bool=False
    launchable: bool=False
    root: bool=False
    running: bool=False
    pending: bool=False
    source_error: str=''
    removal_error: str=''
    dependencies: list=field(default_factory=list)
    remove: list=field(default_factory=list)
    preserve: dict=field(default_factory=dict)
    system_package: str=''
    conflicts: list=field(default_factory=list)
    install_error: str=''
    migration_action: str=''
    migration_token: str=''
    migration_files: list=field(default_factory=list)
    migration_backups: list=field(default_factory=list)
    migration_data: list=field(default_factory=list)
    migration_error: str=''
    legacy_access: bool=False

    def allowed(self,action,remove_access=False):
        if self.root or self.running or self.source_error:return False
        if self.system_package:
            return (action=='revoke' or
                    (action=='remove_legacy_access' and self.legacy_access and not self.conflicts and not self.migration_error) or
                    (action in ('migrate','resume_migration','recover_legacy') and action==self.migration_action and not self.migration_error))
        if self.pending:return action=='recover'
        if action=='install':return not self.install_error and all(item['ok'] or not item['required'] for item in self.dependencies)
        if action=='remove':return not self.removal_error and (bool(self.remove) or remove_access)
        return False


class SetupBackend:
    def __init__(self,source=BASE,locations=None):
        self.source=Path(source).resolve()
        self.locations=locations or Locations.current()

    def inspect(self):
        loc=self.locations
        try:profile=inspect_deployment(self.source)
        except ValueError as exc:return Overview(destination=str(self.source),system_package='system',source_error=str(exc),root=os.geteuid()==0)
        if profile.system:
            conflicts=legacy_conflicts(loc)
            result=Overview(destination=str(profile.directory),version=VERSION,installed=True,
                root=os.geteuid()==0,system_package=profile.manager,conflicts=conflicts,
                launchable=not conflicts and (self.source/'launch.py').is_file(),
                running=bool(running_app(loc,directory=profile.directory) or running_app(loc)))
            try:
                from migration import preview
                plan=preview(loc)
                result.migration_action=plan['action'];result.migration_token=plan['token']
                result.migration_files=plan['files'];result.migration_backups=plan['backups']
                result.migration_data=plan['data_imports']
            except (OSError,ValueError,RuntimeError) as exc:result.migration_error=str(exc)
            try:
                for name in inventory(self.source)['runtime']:source_file(self.source,name)
            except (OSError,ValueError) as exc:
                result.source_error=str(exc);result.launchable=False
            result.dependencies=checks(session=False,native=True)
            from access_request import legacy_access_present
            result.legacy_access=legacy_access_present()
            return result
        result=Overview(destination=str(loc.app),installed=loc.app.exists(),root=os.geteuid()==0,
                        pending=loc.pending.exists() or loc.pending.is_symlink())
        result.launchable=(loc.app/'launch.py').is_file() and not result.pending
        try:
            for name in inventory(self.source)['runtime']:source_file(self.source,name)
        except (OSError,ValueError) as exc:result.source_error=str(exc)
        result.dependencies=checks(session=False)
        try:require_user_maintenance(self.source,installing=True)
        except RuntimeError as exc:result.install_error=str(exc)
        result.running=bool(running_app(loc))
        try:
            no_links(loc.base,loc.data);no_links(loc.receipt,loc.data)
            if loc.receipt.exists():
                if loc.receipt.stat().st_size>128*1024:raise ValueError('Invalid installation record')
                record=json.loads(loc.receipt.read_text())
                if not isinstance(record,dict) or not isinstance(record.get('version'),str):raise ValueError('Invalid installation record')
                result.version=record['version'][:80]
            if not result.pending:
                plan=removal_plan(loc)
                result.remove=[str(loc.target(key)) for key in plan['remove']]
                result.preserve={str(loc.target(key)):reason for key,reason in plan['preserve'].items()}
        except (OSError,ValueError,RuntimeError) as exc:result.removal_error=str(exc)
        return result

    def execute(self,action,remove_access=False,migration_token=None):
        # Re-check at execution, not just while displaying the preview. The
        # existing CLI takes the exclusive lock again, covering later races.
        current=self.inspect()
        if not current.allowed(action,remove_access):
            raise RuntimeError('Setup conditions changed; refresh the preview before continuing.')
        if action in ('migrate','resume_migration','recover_legacy'):
            from migration import migrate
            result=migrate(self.source,self.locations,migration_token)
            message=_('Recuperação concluída. Verifique a prévia antes de migrar.') if result['recovered'] else _('Migração concluída. A instalação anterior foi guardada nestes locais:')
            return subprocess.CompletedProcess([],0,message+'\n'+'\n'.join(result['backups']),'')
        if action=='revoke':
            from access_request import run_access
            result,expected_helper=run_access('remove',directory=self.source)
            return result
        if action=='remove_legacy_access':
            from access_request import remove_legacy_access
            return remove_legacy_access(self.source)
        if action=='install':command=['/usr/bin/python3',str(self.source/'install.py'),'--no-launch']
        elif action=='recover':command=['/usr/bin/python3',str(self.source/'install.py'),'--recover']
        elif action=='remove':
            command=['/usr/bin/python3',str(self.source/'uninstall.py'),'--yes']
            if remove_access:command.append('--remove-access')
        else:raise ValueError('Unknown setup action')
        environment=dict(os.environ,XDG_DATA_HOME=str(self.locations.data),XDG_CONFIG_HOME=str(self.locations.config))
        result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,env=environment)
        return result

    def open_app(self):
        if os.geteuid()==0:raise ValueError('Run as your own user, without sudo.')
        profile=inspect_deployment(self.source)
        if profile.system:
            if not self.inspect().launchable:raise RuntimeError('Resolve installation conflicts before opening the app.')
            path=self.source/'launch.py'
        else:
            path=self.locations.app/'launch.py'
            no_links(path,self.locations.data)
        if not path.is_file():raise FileNotFoundError(path)
        # Desktop launch is a request, not a claim that the app completed startup.
        # Do not wait for an older launcher which stays alive with its window.
        environment=dict(os.environ,XDG_DATA_HOME=str(self.locations.data),XDG_CONFIG_HOME=str(self.locations.config))
        spawn_logged(['/usr/bin/python3',str(path)],'setup-launch.log',env=environment)
        return subprocess.CompletedProcess([],0,'','')
