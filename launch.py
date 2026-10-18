#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Open or reveal the persistent app, with optional systemd supervision."""
import os
import subprocess
from pathlib import Path
from dualsense import CONFIG_DIR, STATE_DIR
from session import UNIT, activate_existing, instance_running, systemd_available
from autostart import request_hidden_start, HIDDEN
from i18n import _
from maintenance import Locations
from deployment import inspect_deployment, legacy_conflicts, SYSTEM_UNIT, SYSTEM_UNIT_PATH


def open_app(directory=None, detach=False, background=False):
    if os.geteuid()==0:raise SystemExit(_('Abra o app como seu usuário, sem sudo.'))
    if background:
        # Login autostart: never reveal a window that is already running.
        if instance_running():return
        request_hidden_start(STATE_DIR)
    else:
        # A manual launch always shows the window, even right after login.
        try:(STATE_DIR/HIDDEN).unlink()
        except FileNotFoundError:pass
    directory = Path(directory) if directory is not None else Path(__file__).resolve().parent
    profile=inspect_deployment(directory)
    locations=Locations.current()
    if profile.system and legacy_conflicts(locations):
        # Show the conflict without running a legacy service or deleting it.
        os.execv('/usr/bin/python3',['/usr/bin/python3',str(directory/'setup.py')])
        return
    # Also covers an app started from a terminal or without systemd supervision.
    if activate_existing(**({'expected_directory':directory} if profile.system else {})):return
    if locations.pending.exists() or locations.pending.is_symlink():
        os.execv('/usr/bin/python3',['/usr/bin/python3',str(directory/'recovery_ui.py')])
        return
    if systemd_available():
        from install import install, import_desktop_environment
        if profile.system:
            subprocess.run(['systemctl','--user','daemon-reload'],check=True)
            result=subprocess.run(['systemctl','--user','show',SYSTEM_UNIT,
                                   '--property=FragmentPath','--property=DropInPaths'],
                                  check=True,capture_output=True,text=True)
            properties=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
            if properties.get('FragmentPath')!=str(SYSTEM_UNIT_PATH) or properties.get('DropInPaths')!='':
                raise RuntimeError(_('O serviço do pacote está ausente ou foi substituído por uma configuração local. Confira a instalação antes de abrir o app.'))
            import_desktop_environment()
            try:subprocess.run(['systemctl','--user','start',SYSTEM_UNIT],check=True,capture_output=True,text=True)
            except subprocess.CalledProcessError:
                if activate_existing(expected_directory=directory):return
                raise
            return
        if not (CONFIG_DIR.parent/'systemd/user'/UNIT).exists():
            install(launch=False,files_only=True)
            subprocess.run(['systemctl','--user','daemon-reload'],check=True)
        import_desktop_environment()
        running=subprocess.run(['systemctl','--user','is-active','--quiet',UNIT]).returncode==0
        try:subprocess.run(['systemctl','--user','start',UNIT],check=True,capture_output=True,text=True)
        except subprocess.CalledProcessError:
            # A simultaneous terminal launch may have acquired the D-Bus name.
            # Reuse it; never fall back to spawning a second hardware session.
            if activate_existing():return
            raise
        # Migration: the previous GTK Window-only release has no D-Bus name.
        if running:
            subprocess.run(['systemctl','--user','kill','--kill-whom=main','--signal=SIGUSR1',UNIT],check=True)
        return
    command=['/usr/bin/python3',str(directory/'window.py')]
    if not detach:
        os.execv(command[0],command)
    else:
        STATE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
        log_fd=os.open(STATE_DIR/'app.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(log_fd,'w') as log:
            subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)


if __name__=='__main__':
    import sys
    try:open_app(background='--background' in sys.argv[1:])
    except Exception as exc:
        import sys
        from startup_notice import report_startup_failure
        raise SystemExit(report_startup_failure(exc,reason='launch',retry=[sys.executable,__file__,*sys.argv[1:]]))
