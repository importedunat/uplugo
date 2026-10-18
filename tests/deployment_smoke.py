# SPDX-License-Identifier: GPL-3.0-only
"""Read-only system-runtime routing, real GTK and D-Bus; no physical USB.

Default: redirect only the system-program and USB constants into a private copy.
--installed: use /usr/share/dualsense-usb in a disposable namespace with empty
/sys (no substitutions). Neither mode installs packages or authorizes access.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SOURCE=Path(__file__).resolve().parents[1]


def exercise(program,root):
    from unittest.mock import patch
    sys.path.insert(0,str(program))
    import deployment,session,dualsense,setup_state
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gio,GLib,Gdk
    from setup_ui import SetupDialog
    from i18n import _,set_language
    from theme import install_theme
    from maintenance import Locations
    assert os.environ.get('DBUS_SESSION_BUS_ADDRESS','').startswith('unix:path=/tmp/'), 'Private D-Bus required'
    assert not session.activate_existing(), 'Do not reuse an existing app'
    assert deployment.inspect_deployment().system
    assert deployment.inspect_deployment().helper==Path('/usr/libexec/dualsense-usb-helper')
    # Even the direct window subprocess sees an empty USB directory.
    assert not dualsense.USB.exists() or not list(dualsense.USB.iterdir()), 'USB must be isolated'
    loc=Locations.current()
    dualsense.write_json(dualsense.SETTINGS,{'names':{'fixture':'Meu controle'},'modes':{'fixture':'charge'},'ui':{'download_photos':False}})
    photos=loc.base/'appearance-library';photos.mkdir(parents=True);(photos/'keep.txt').write_text('personal photo fixture')
    before={p.relative_to(program):p.read_bytes() for p in program.rglob('*') if p.is_file()}
    install_theme()
    def pump():
        while Gtk.events_pending():Gtk.main_iteration_do(False)
    def until(done):
        end=time.monotonic()+10
        while not done():
            pump();assert time.monotonic()<end,'Native-runtime test timed out'
            time.sleep(.02)
    for code in ('pt-BR','en','es'):
        set_language(code)
        backend=setup_state.SetupBackend(program,loc)
        dialog=SetupDialog(backend);dialog.show_all();dialog.refresh()
        until(lambda:not dialog.checking)
        try:
            dialog.resize(480,520);pump()
            assert not dialog.primary.get_visible() and not dialog.choice.get_visible()
            assert not dialog.access.get_visible() and dialog.open_button.get_sensitive()
            assert dialog.intro.get_text()==_('Instalado pelo sistema')
            area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
            width,height=dialog.get_size();assert width<=area.width and height<=area.height
            with patch.object(backend,'execute',side_effect=AssertionError('No native user-maintenance')):
                dialog.start();assert not dialog.running
            for conflict in (loc.target('desktop'),loc.target('service'),loc.pending):
                conflict.parent.mkdir(parents=True,exist_ok=True);conflict.symlink_to(root/'missing')
                dialog.refresh();until(lambda:not dialog.checking)
                assert str(conflict) in dialog.details_text.get_text()
                assert not dialog.open_button.get_visible()
                assert not dialog.primary.get_visible()
                dialog.start();assert not dialog.running and conflict.is_symlink()
                conflict.unlink()
            dialog.refresh();until(lambda:not dialog.checking)
            assert dialog.open_button.get_visible()
            if os.environ.get('DUALSENSE_DEPLOYMENT_PREVIEW'):
                time.sleep(.12);pump()
                output=Path(os.environ['DUALSENSE_DEPLOYMENT_PREVIEW']);output.mkdir(parents=True,exist_ok=True)
                window=dialog.get_window();width,height=dialog.get_size()
                Gdk.pixbuf_get_from_window(window,0,0,width,height).savev(str(output/(code+'.png')),'png',[],[])
        finally:dialog.destroy();pump()
    # The actual window entrypoint acquires the same bus name; the launcher must
    # verify its program location and reveal it without copying files/services.
    log_path=root/'native-window.log'
    with log_path.open('w+') as log:
        process=subprocess.Popen(['/usr/bin/python3',str(program/'window.py')],stdout=log,stderr=log)
        try:
            def owned():
                assert process.poll() is None,'Native window exited early'
                bus=session.session_bus()
                return bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
                    'NameHasOwner',GLib.Variant('(s)',(session.APP_ID,)),GLib.VariantType('(b)'),
                    Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
            until(owned)
            assert session.activate_existing(expected_directory=program)
            try:session.activate_existing(expected_directory=root/'different-installation')
            except RuntimeError:pass
            else:raise AssertionError('Wrong installation was activated')
            import launch
            with patch.object(launch,'systemd_available',side_effect=AssertionError('Existing owner should be reused')):
                launch.open_app(program)
            assert process.poll() is None
            process.send_signal(signal.SIGTERM);assert process.wait(timeout=10)==0
            assert not session.activate_existing()
        except BaseException:
            log.flush();log.seek(0);print(log.read(),file=sys.stderr);raise
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
    assert before=={p.relative_to(program):p.read_bytes() for p in program.rglob('*') if p.is_file()}
    assert not loc.app.exists() and not loc.receipt.exists()
    assert not loc.target('desktop').exists() and not loc.target('service').exists()
    assert (photos/'keep.txt').read_text()=='personal photo fixture'
    settings=json.loads(dualsense.SETTINGS.read_text())
    assert settings['names']['fixture']=='Meu controle' and settings['modes']['fixture']=='charge'
    print('DEPLOYMENT OK: read-only native runtime; three-language GTK; legacy conflicts preserved; real D-Bus owner path; no user program copy; personal data preserved.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed',action='store_true')
    parser.add_argument('--preview',type=Path)
    parser.add_argument('--child',nargs=2,metavar=('PROGRAM','ROOT'))
    args=parser.parse_args()
    if args.child:return exercise(*map(Path,args.child))
    sys.path.insert(0,str(SOURCE))
    from distribution import inventory
    from app_info import VERSION
    with tempfile.TemporaryDirectory(prefix='dualsense-native-runtime-') as temporary:
        root=Path(temporary);(root/'usb').mkdir()
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GIO_USE_VFS='local',NO_AT_BRIDGE='1')
        if args.preview:env['DUALSENSE_DEPLOYMENT_PREVIEW']=str(args.preview.resolve())
        for key,name in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),
                         ('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache')]:
            path=root/name;path.mkdir(mode=0o700);env[key]=str(path)
        if args.installed:
            program=Path('/usr/share/dualsense-usb')
        else:
            program=root/'program';program.mkdir()
            for name in inventory()['runtime']:
                target=program/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(SOURCE/name,target)
            (program/'system-package.json').write_text(json.dumps({'format':1,'manager':'deb','version':VERSION}))
            path=program/'deployment.py'
            path.write_text(path.read_text().replace("SYSTEM_APP = Path('/usr/share/dualsense-usb')",'SYSTEM_APP = Path('+repr(str(program))+')'))
            path=program/'dualsense.py'
            path.write_text(path.read_text().replace("USB = Path('/sys/bus/usb/devices')",'USB = Path('+repr(str(root/'usb'))+')'))
            for path in program.rglob('*'):path.chmod(0o555 if path.is_dir() else 0o444)
            program.chmod(0o555)
        try:
            subprocess.run([sys.executable,__file__,'--child',str(program),str(root)],env=env,check=True)
        finally:
            if not args.installed:
                program.chmod(0o755)
                for path in program.rglob('*'):
                    if path.is_dir():path.chmod(0o755)


if __name__=='__main__':main()
