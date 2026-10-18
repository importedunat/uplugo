# SPDX-License-Identifier: GPL-3.0-only
"""Real multi-process GTK/D-Bus lifecycle; synthetic USB and private data only.

Run with dbus-run-session. Never attach this test to the user's session bus.
"""
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))


def host(root):
    import window
    from session import run_application
    from gi.repository import GLib
    root=Path(root)
    def event(text):
        with (root/'events').open('a') as stream:stream.write(text+'\n')
    class TestWindow(window.Window):
        def __init__(self,application=None):
            super().__init__(application)
            event('created')
            GLib.idle_add(self.close)
        def hide_to_tray(self,*args):
            with patch.object(self.tray,'available',return_value=True):result=super().hide_to_tray(*args)
            event('hidden' if not self.get_visible() else 'unexpected-visible')
            return result
        def reveal(self):
            event('activated')
            return super().reveal()
        def stop_all(self):
            event('stopped')
            return super().stop_all()
    popen=subprocess.Popen
    def no_hardware(command,*args,**kwargs):
        if any('pkexec' in str(arg) or 'dualsense-usb-helper' in str(arg) for arg in command):
            raise AssertionError('No hardware subprocesses in this test')
        return popen(command,*args,**kwargs)
    with patch.object(window.core,'USB',root/'usb'), \
         patch.object(window,'HELPER',root/'no-helper'), \
         patch.object(window.subprocess,'Popen',side_effect=no_hardware):
        GLib.timeout_add_seconds(20,lambda:os.kill(os.getpid(),signal.SIGTERM))
        return run_application(TestWindow)


def main():
    import session
    from maintenance import Locations, installation_lock
    # A private bus from dbus-run-session has a random /tmp socket; reject the
    # host user's regular bus and any existing real app before starting.
    address=os.environ.get('DBUS_SESSION_BUS_ADDRESS','')
    if not address.startswith('unix:path=/tmp/'):
        raise SystemExit('Execute com dbus-run-session em um barramento privado.')
    if session.activate_existing():raise SystemExit('Há um app nesta sessão. Não executar o teste aqui.')
    with tempfile.TemporaryDirectory(prefix='dualsense-session-') as temporary:
        root=Path(temporary);(root/'usb').mkdir()
        env=dict(os.environ,XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'),GIO_USE_VFS='local',GTK_USE_PORTAL='0',NO_AT_BRIDGE='1')
        locations=Locations(root/'data',root/'config')
        notification=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        notification.bind(str(root/'notify'));notification.settimeout(2)
        env['NOTIFY_SOCKET']=str(root/'notify')
        preferences=root/'config/dualsense-usb/controllers.json'
        preferences.parent.mkdir(parents=True)
        preferences.write_text('{"ui":{"download_photos":false},"modes":{"sample":"charge"}}')
        before=preferences.read_bytes()
        def events():return (root/'events').read_text().splitlines() if (root/'events').exists() else []
        def until(predicate,process):
            deadline=time.monotonic()+8
            while not predicate():
                if process.poll() is not None:raise AssertionError('Primary app exited early')
                if time.monotonic()>deadline:raise AssertionError('Timed out: '+repr(events()))
                time.sleep(.05)
        command=[sys.executable,__file__,'--host',str(root)]
        with (root/'process.log').open('w+') as log:
            primary=subprocess.Popen(command,env=env,stdout=log,stderr=log)
            try:
                until(lambda:'hidden' in events(),primary)
                assert notification.recv(128)==b'READY=1'
                try:
                    with installation_lock(locations):
                        raise AssertionError('An active app must prevent maintenance')
                except RuntimeError:pass
                # Five simultaneous openings must reuse the hidden primary.
                children=[subprocess.Popen(command,env=env,stdout=log,stderr=log) for _ in range(5)]
                try:
                    for child in children:assert child.wait(timeout=10)==0
                finally:
                    for child in children:
                        if child.poll() is None:child.terminate();child.wait(timeout=5)
                until(lambda:events().count('activated')==5,primary)
                assert events().count('created')==1 and 'stopped' not in events(),events()
                # Exercise the menu launcher too: it must not invoke systemd.
                with patch('launch.systemd_available',side_effect=AssertionError('Must reuse owner')):
                    import launch
                    launch.open_app()
                until(lambda:events().count('activated')==6,primary)
                assert preferences.read_bytes()==before
                primary.send_signal(signal.SIGUSR2)
                until(lambda:events().count('hidden')==2,primary)
                assert 'stopped' not in events()
                primary.send_signal(signal.SIGTERM)
                assert primary.wait(timeout=8)==0
                assert events().count('stopped')==1,events()
                assert not session.activate_existing()
                # Maintenance prevents startup before the first window/helper.
                with installation_lock(locations):
                    blocked=subprocess.run(command,env=env,capture_output=True,timeout=8)
                    assert blocked.returncode!=0 and b'manuten' in blocked.stderr
                    assert events().count('created')==1
                # A later start must obtain ownership after clean shutdown.
                primary=subprocess.Popen(command,env=env,stdout=log,stderr=log)
                until(lambda:events().count('hidden')==3,primary)
                assert notification.recv(128)==b'READY=1'
                primary.send_signal(signal.SIGTERM)
                assert primary.wait(timeout=8)==0
                assert events().count('created')==2 and events().count('stopped')==2
                assert preferences.read_bytes()==before
                # No D-Bus must fail before opening hardware, not silently run
                # a non-unique application.
                failed=subprocess.run(command,env=dict(env,DBUS_SESSION_BUS_ADDRESS='unix:path='+str(root/'missing-bus')),capture_output=True,timeout=8)
                assert failed.returncode!=0
                assert events().count('created')==2
                # GTK signal handlers must propagate startup failures as a
                # failed process, so systemd does not accept a false success.
                broken=[sys.executable,'-c',
                        'from session import run_application\n'
                        'def fail(**kwargs): raise RuntimeError("startup fixture failure")\n'
                        'raise SystemExit(run_application(fail))']
                failed=subprocess.run(broken,cwd=BASE,env=env,capture_output=True,timeout=8)
                assert failed.returncode!=0 and b'startup fixture failure' in failed.stderr
                with installation_lock(locations):pass  # No leaked startup lock.
                # A pending installation must stop startup before Window/USB.
                locations.pending.write_text('{}')
                failed=subprocess.run(command,env=env,capture_output=True,timeout=8)
                assert failed.returncode!=0 and b'PendingInstallation' in failed.stderr
                assert events().count('created')==2 and preferences.read_bytes()==before
                locations.pending.unlink()
                with installation_lock(locations):pass

                print('SESSION OK: simultaneous launches, close to tray, reopen, no duplicate USB owners, maintenance exclusion, systemd readiness, cleanup, restart, missing bus, unchanged settings.')
            except BaseException:
                log.flush();log.seek(0);print(log.read(),file=sys.stderr);raise
            finally:
                if primary.poll() is None:primary.terminate();primary.wait(timeout=8)
                notification.close()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--host':raise SystemExit(host(sys.argv[2]))
    main()
