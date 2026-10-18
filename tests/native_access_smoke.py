# SPDX-License-Identifier: GPL-3.0-only
"""Native access GTK flows with private grants and simulated authorization.

Root program execution is tested separately by native_admin_namespace.py.
This test never queries the host polkit daemon or starts a controller helper.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]


def exercise(root):
    sys.path.insert(0,str(BASE))
    import window,access_request,deployment,native_status,setup_state
    from build_helper import native_payloads,native_helper_source
    from native_grant import NativeGrantFiles,native_rule,NATIVE_ADMIN_PATH,NATIVE_HELPER_PATH
    from native_access import NativeAccess
    from setup_ui import SetupDialog
    from gi.repository import Gtk,GLib
    from i18n import set_language,_
    from distribution import inventory
    from app_info import VERSION
    import hashlib
    files=NativeGrantFiles(root/'system',os.getuid());files.root.mkdir()
    payloads=native_payloads()
    expected={}
    for name,(data,mode) in payloads.items():
        path=files.path(name,create=True);path.write_bytes(data);path.chmod(mode)
        if name!=NATIVE_ADMIN_PATH:expected[name]=(hashlib.sha256(data).hexdigest(),mode)
    admin=NativeAccess(files,expected);actor=(1000,'fixture');other=(1001,'other')
    admin.apply('install',other);other_before=files.read(files.relative('rule',1001))
    program=root/'program';program.mkdir()
    for name in inventory()['runtime']:
        target=program/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,target)
    (program/deployment.MARKER).write_text(json.dumps({'format':1,'manager':'deb','version':VERSION}))
    helper=files.root/NATIVE_HELPER_PATH
    window.core.write_json(window.core.SETTINGS,{'names':{'fixture':'Meu controle'},'modes':{'fixture':'charge'},'ui':{'download_photos':False}})
    def authorized():
        saved=files.read(files.relative('rule',1000))
        return saved is not None and saved[0]==native_rule(actor)
    def pump():
        while Gtk.events_pending():Gtk.main_iteration_do(False)
    def until(done):
        end=time.monotonic()+12
        while not done():
            pump();assert time.monotonic()<end,'Native access UI timed out'
            time.sleep(.005)
    def finished(dialog):until(lambda:not dialog.running and not dialog.checking)
    root.joinpath('usb').mkdir()
    outcome=['cancel'];calls=[]
    def request(action,**kwargs):
        calls.append(action)
        code=126 if outcome[0]=='cancel' else 0
        if outcome[0]=='ok':admin.apply(action,actor)
        return subprocess.CompletedProcess([],code,'',''),native_helper_source() if action=='install' else None
    popen=subprocess.Popen
    def no_hardware(command,*args,**kwargs):
        if any('pkexec' in str(arg) or 'pkcheck' in str(arg) or 'dualsense-usb-helper' in str(arg) for arg in command):
            raise AssertionError('No USB/authorization subprocesses in GTK fixture')
        return popen(command,*args,**kwargs)
    with patch.object(window,'DEPLOYMENT',deployment.Deployment(program,'deb')), \
         patch.object(window,'HELPER',helper),patch.object(window.core,'USB',root/'usb'), \
         patch.object(window.GLib,'timeout_add_seconds',return_value=0), \
         patch.object(native_status,'native_authorized',side_effect=authorized), \
         patch.object(access_request,'run_access',side_effect=request), \
         patch.object(window.subprocess,'Popen',side_effect=no_hardware):
        main=window.Window();before=window.core.SETTINGS.read_bytes()
        try:
            until(lambda:not main.native_authorization._running)
            assert not main.helper_ready(),'Installing a helper alone must not authorize this account'
            with patch.object(main,'stop_all') as stop:
                main.install();until(lambda:not main.busy)
                assert main.access_setup.phase=='cancelled' and not authorized()
                outcome[0]='lie';main.install();until(lambda:not main.busy)
                assert main.access_setup.phase=='failed' and not authorized()
                outcome[0]='ok'
                entered=threading.Event();release=threading.Event()
                def paused_probe():
                    if authorized():entered.set();assert release.wait(5)
                    return authorized()
                main.native_authorization.probe=paused_probe
                main.install();until(entered.is_set)
                ticks=[];GLib.idle_add(lambda:ticks.append('responsive'))
                until(lambda:bool(ticks));assert main.busy
                count=len(calls);main.install();assert len(calls)==count
                release.set();until(lambda:not main.busy)
                main.native_authorization.probe=authorized
                assert main.helper_ready() and main.access_setup.phase=='idle'
                granted=files.read(files.relative('rule',1000))
                main.install();until(lambda:not main.busy)
                assert files.read(files.relative('rule',1000))==granted
                stop.assert_not_called()
                assert before==window.core.SETTINGS.read_bytes()
        finally:main.destroy();pump()
    # Native setup can revoke just this account, after its app has stopped.
    with patch.object(deployment,'SYSTEM_APP',program), \
         patch.object(setup_state,'checks',return_value=[]), \
         patch.object(setup_state,'running_app') as running, \
         patch.object(access_request,'run_access',side_effect=request):
        for language in ('pt-BR','en','es'):
            set_language(language);admin.apply('install',actor)
            backend=setup_state.SetupBackend(program)
            running.return_value=[42]
            dialog=SetupDialog(backend);dialog.show_all();dialog.refresh();finished(dialog)
            try:
                assert not dialog.revoke_button.get_sensitive()
                count=len(calls);dialog.revoke_access();assert len(calls)==count
                running.return_value=[];dialog.refresh();finished(dialog)
                assert dialog.revoke_button.get_sensitive() and not dialog.primary.get_visible()
                outcome[0]='cancel';dialog.revoke_button.clicked();finished(dialog)
                assert authorized() and dialog.status.get_text()==_('Autorização cancelada. A concessão de acesso foi mantida.')
                outcome[0]='ok';dialog.refresh();finished(dialog)
                dialog.revoke_button.clicked();finished(dialog)
                assert not authorized() and not dialog.revoke_button.get_sensitive()
                assert dialog.status.get_text()==_('Acesso USB revogado para esta conta. Para usar os controles novamente, abra o app e configure o acesso.')
                assert files.read(files.relative('rule',1001))==other_before
                assert before==window.core.SETTINGS.read_bytes()
            finally:dialog.destroy();pump()
    assert all((files.root/name).read_bytes()==data for name,(data,mode) in payloads.items())
    print('NATIVE ACCESS UI OK: helper alone is not authorization, cancel, false success, responsive confirmation, no stream restart, per-account revoke, active-app guard, three languages, preferences/other grants/package files preserved; simulated authentication, no USB.',flush=True)


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--child':return exercise(Path(sys.argv[2]))
    with tempfile.TemporaryDirectory(prefix='dualsense-native-ui-') as temporary:
        root=Path(temporary);env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        for key,name in [('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),
                         ('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache')]:
            path=root/name;path.mkdir();env[key]=str(path)
        subprocess.run([sys.executable,__file__,'--child',str(root)],env=env,check=True)


if __name__=='__main__':main()
