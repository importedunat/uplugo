# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK and child authorization transport from a read-only runtime tree.

Run inside the isolated userspace suite. A private fake pkexec inspects but
never executes the administrative script. No real USB, permissions or settings.
"""
import hashlib
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import sys
import tempfile
import time

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))

FAKE_AUTH=r'''#!/usr/bin/python3
import ast,json,os,stat,sys
from pathlib import Path
root=Path(os.environ['DUALSENSE_READONLY_TEST'])
assert sys.argv[1:3]==['/usr/bin/python3','-I'] and len(sys.argv)==4
script=Path(sys.argv[3]);text=script.read_text();tree=ast.parse(text)
assert script.name=='install-access.py'
assert stat.S_IMODE(script.stat().st_mode)==0o600
assert stat.S_IMODE(script.parent.stat().st_mode)==0o700
payloads=[node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call)
          and isinstance(node.func,ast.Attribute) and node.func.attr=='install'
          and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)]
assert len(payloads)==1
(root/'request.json').write_text(json.dumps({'script':str(script),'pid':os.getpid()}))
outcome=(root/'outcome').read_text()
if outcome=='terminal':
    assert all(os.isatty(fd) for fd in (0,1,2)), 'Interactive authorization lost its terminal'
    assert input('Synthetic authorization (yes): ')=='yes'
    (root/'terminal-verified').write_text('ok')
    raise SystemExit(0)
if outcome=='cancel':raise SystemExit(126)
if outcome=='fail':print('fixture refused',file=sys.stderr);raise SystemExit(1)
if outcome=='ok':(root/'helper').write_text(payloads[0])
elif outcome!='lie':raise AssertionError(outcome)
'''


def child(root,source):
    from unittest.mock import patch,Mock
    import threading
    sys.path.insert(0,str(source))
    import window,access_request
    from gi.repository import Gtk
    from i18n import set_language
    set_language('pt-BR')
    def until(predicate):
        deadline=time.monotonic()+8
        while not predicate():
            while Gtk.events_pending():
                assert time.monotonic()<deadline,'GTK callbacks did not settle'
                Gtk.main_iteration_do(False)
            assert time.monotonic()<deadline,'Read-only UI test timed out'
            time.sleep(.005)
    window.core.write_json(window.core.SETTINGS,{'names':{'fixture':'My controller'},'modes':{'fixture':'charge'},'ui':{'download_photos':False}})
    before=window.core.SETTINGS.read_bytes()
    with patch.object(window.core,'USB',root/'usb'),patch.object(window,'HELPER',root/'helper'), \
         patch.object(window.Window,'start_photo_downloads',return_value=False), \
         patch.object(window.GLib,'timeout_add_seconds',return_value=0):
        app=window.Window();stream=Mock();app.streams={'fixture':stream}
        try:
            with patch.object(app,'refresh',side_effect=lambda:app.dashboard.update([],app.helper_ready())), \
                 patch.object(app,'stop_all') as stop:
                started=threading.Event();release=threading.Event()
                original=access_request.helper_source
                def prepare():
                    assert threading.current_thread() is not threading.main_thread()
                    started.set();assert release.wait(5)
                    return original()
                (root/'outcome').write_text('cancel')
                with patch.object(access_request,'helper_source',side_effect=prepare) as build:
                    app.install();until(started.is_set)
                    assert app.busy and not app.unlock.get_sensitive()
                    idle=[];window.GLib.idle_add(lambda:idle.append(True) or False)
                    until(lambda:bool(idle))  # GTK is responsive while preparing.
                    app.install();assert build.call_count==1
                    release.set();until(lambda:not app.busy)
                assert app.access_setup.phase=='cancelled';stop.assert_not_called()
                first=json.loads((root/'request.json').read_text())
                assert not Path(first['script']).parent.exists()
                for outcome,expected in (('fail','failed'),('lie','failed'),('ok','ready')):
                    (root/'outcome').write_text(outcome);app.install();until(lambda:not app.busy)
                    request=json.loads((root/'request.json').read_text())
                    assert not Path(request['script']).exists()
                    assert window.core.SETTINGS.read_bytes()==before
                    if outcome!='ok':
                        assert app.access_setup.phase==expected;stop.assert_not_called()
                    else:
                        assert (root/'helper').read_text()==original()
                        stop.assert_called_once();assert not app.dashboard.setup.get_visible()
                stream.stdin.write.assert_not_called()
                # Preserve the existing distinction between retryable reads and
                # one-shot identification after moving execution into a worker.
                replies=[]
                def done(result):
                    assert threading.current_thread() is threading.main_thread()
                    replies.append(result)
                first=subprocess.CompletedProcess([],0,json.dumps({'reading':{'status':'Unknown'}}),'')
                second=subprocess.CompletedProcess([],0,json.dumps({'reading':{'status':'Charging'}}),'')
                with patch.object(window.subprocess,'run',side_effect=[first,second]) as runner:
                    app.run(['fixture','read'],done);until(lambda:not app.busy)
                    assert runner.call_count==2 and replies[-1] is second
                with patch.object(window.subprocess,'run',return_value=first) as runner:
                    app.run(['fixture','identify'],done);until(lambda:not app.busy)
                    assert runner.call_count==1
                assert window.core.SETTINGS.read_bytes()==before
        finally:app.streams={};app.quit_app()


def main():
    from distribution import inventory
    with tempfile.TemporaryDirectory(prefix='dualsense-readonly-ui-') as temporary:
        root=Path(temporary);source=root/'program';source.mkdir()
        for name in inventory()['runtime']:
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(BASE/name,path);path.chmod(0o444)
        directories=[p for p in source.rglob('*') if p.is_dir()]+[source]
        for path in directories:path.chmod(0o555)
        before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
        for name in ('usb','commands','requests','home'): (root/name).mkdir(mode=0o700)
        fake=root/'commands/pkexec';fake.write_text(FAKE_AUTH);fake.chmod(0o700)
        env=dict(os.environ,HOME=str(root/'home'),XDG_CONFIG_HOME=str(root/'config'),
                 XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),XDG_CACHE_HOME=str(root/'cache'),
                 TMPDIR=str(root/'requests'),DUALSENSE_READONLY_TEST=str(root),PYTHONDONTWRITEBYTECODE='1',
                 PATH=str(root/'commands')+os.pathsep+os.environ['PATH'])
        try:
            subprocess.run([sys.executable,__file__,'--child',str(root),str(source)],env=env,check=True,timeout=35)
            # A real private PTY checks CLI transport without any real agent,
            # password or privilege. All three streams must remain interactive.
            (root/'outcome').write_text('terminal')
            master,slave=pty.openpty();process=None
            try:
                code='from access_request import run_access; result,_=run_access("install",interactive=True); raise SystemExit(result.returncode)'
                process=subprocess.Popen([sys.executable,'-c',code],cwd=source,env=env,stdin=slave,stdout=slave,stderr=slave)
                os.write(master,b'yes\n')
                assert process.wait(timeout=10)==0,'Interactive request failed'
                assert (root/'terminal-verified').read_text()=='ok'
            finally:
                if process and process.poll() is None:process.terminate();process.wait(timeout=5)
                os.close(master);os.close(slave)
            after={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
            assert before==after,'Runtime files were modified'
            assert not list((root/'requests').glob('dualsense-access-*')),'Request directory leaked'
        finally:
            for path in directories:path.chmod(0o755)
    print('READONLY OK: real GTK, immutable runtime, private temporary scripts, fake authorization child, private PTY for CLI, cancellation/failure/retry, verified helper, responsive preparation, preserved modes, no real USB or authorization.')


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child':child(Path(sys.argv[2]),Path(sys.argv[3]))
    else:main()
