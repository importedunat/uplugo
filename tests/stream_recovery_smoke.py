# SPDX-License-Identifier: GPL-3.0-only
"""GTK stream lifecycle with controlled processes; no USB or authorization."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class InputPipe:
    def __init__(self):self.closed=False;self.sent=[];self.broken=False
    def write(self,text):
        if self.broken:raise BrokenPipeError('helper stopped reading')
        if self.closed:raise ValueError('closed')
        self.sent.append(json.loads(text))
    def flush(self):pass
    def close(self):self.closed=True


class Process:
    def __init__(self):
        self.stdin=InputPipe();self.stdout=[];self.stderr=io.StringIO('');self.returncode=None;self.waits=[]
    def poll(self):return self.returncode
    def wait(self,timeout=None):
        self.waits.append(timeout)
        if self.returncode is None:raise subprocess.TimeoutExpired('fixture',timeout)
        return self.returncode


def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)


with tempfile.TemporaryDirectory(prefix='dualsense-stream-recovery-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    from gi.repository import Gtk
    from i18n import set_language,_
    set_language('pt-BR')
    window.core.write_json(window.core.SETTINGS,{'ui':{'download_photos':False},'modes':{'hid:fixture-a':'play','hid:fixture-b':'charge'}})
    usb=root/'usb';usb.mkdir();a=usb/'1-1';b=usb/'1-2'
    connections={a.name:'boot:1-1:1',b.name:'boot:1-2:2'}
    threads=[];processes=[];commands=[]
    class DeferredThread:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):threads.append(self.target)
    def spawn(command,**kwargs):
        commands.append(command);p=Process();processes.append(p);return p
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',root/'missing-helper'):
        with patch.object(window.GLib,'timeout_add_seconds',return_value=0):app=window.Window()
        try:
            original_settings=window.core.SETTINGS.read_bytes()
            a.mkdir();b.mkdir();interface=root/'interface';interface.mkdir();(interface/'authorized').write_text('1')
            with patch.object(window.core,'fingerprint',side_effect=lambda p:connections.get(p.name,'')),\
                 patch.object(window.core,'key',side_effect=lambda p:'hid:fixture-a' if p==a else 'hid:fixture-b'),\
                 patch.object(window.core,'supported',return_value=True),\
                 patch.object(window.core,'interfaces',return_value=[interface]),\
                 patch.object(window.core,'battery',return_value=None),\
                 patch.object(window.core,'raw_device',return_value=None),\
                 patch.object(app,'helper_ready',return_value=True),\
                 patch.object(app.access_guard,'check',return_value={}),\
                 patch.object(window,'running_game',return_value=None),\
                 patch.object(window.subprocess,'Popen',side_effect=spawn),\
                 patch.object(window.threading,'Thread',DeferredThread):
                app.refresh()
                old,other=processes;old_reader=threads[0]
                # Reconnection is visible only as a changed USB address, without
                # an intervening empty enumeration. The old owner must exit first.
                app.stream_errors[a.name]='old failure';app.stream_status[a.name]={'mode':'proxy'}
                app.live[a.name]={'capacity':75};app.input_watch=(a.name,connections[a.name]);app.input_sample=({'buttons':['cross']},1)
                connections[a.name]='boot:1-1:3';app.refresh()
                assert len(processes)==2 and app.streams[a.name] is old
                assert old.stdin.sent[-1]=={'stop':True} and not old.waits
                assert a.name not in app.live and a.name not in app.stream_status and app.input_sample is None
                for iteration in range(10):app.reconcile_streams([a,b]);app.ensure_stream(a,'play')
                assert sum('stop' in r for r in old.stdin.sent)==1 and len(processes)==2 and not old.waits
                assert other.stdin.sent==[{'mode':'charge','config':None}]
                # A slow old service is shown as pending, with no competing owner.
                with patch.object(window.time,'monotonic',return_value=app.stream_stopping[a.name]+4):app.reconcile_streams([a,b])
                assert app.stream_errors[a.name]==_('O serviço USB ainda está encerrando. Aguarde antes de tentar novamente.')
                old.returncode=0;app.refresh()
                assert len(processes)==3 and a.name not in app.stream_errors
                assert app.stream_connections[a.name]==connections[a.name]
                assert app.streams[b.name] is other
                # Late stdout and completion from the old process cannot poison
                # its replacement's battery, monitor or error state.
                old.stdout=[json.dumps({'input':{'observed':['cross']}}),json.dumps({'identity':'hid:fixture-a','reading':{'capacity':75,'status':'Charging'}})]
                old.stderr=io.StringIO('obsolete error');old_reader()
                with patch.object(window.core,'save_reading') as save,patch.object(window.core,'remember') as remember:
                    pump();save.assert_not_called();remember.assert_not_called()
                assert a.name not in app.stream_errors and a.name not in app.live and app.input_sample is None
                # A mode change on the same connection also waits asynchronously.
                direct=processes[-1];app.ensure_stream(a,'charge')
                assert len(processes)==3 and not direct.waits
                direct.returncode=0;app.reconcile_streams([a,b]);app.ensure_stream(a,'charge')
                assert len(processes)==4 and commands[-1][-3:]==['--exclusive',a.name,'charge']
                # A genuine failure on an unchanged connection does not retry
                # authorization every refresh. A new connection gets one retry.
                failed=processes[-1];failed.returncode=1;failed.stderr=io.StringIO('permission refused');threads[-1]();pump()
                assert app.stream_errors[a.name]=='permission refused'
                for iteration in range(10):app.reconcile_streams([a,b]);app.ensure_stream(a,'charge')
                assert len(processes)==4
                connections[a.name]='boot:1-1:4';app.reconcile_streams([a,b]);app.ensure_stream(a,'charge')
                assert len(processes)==5 and a.name not in app.stream_errors
                # Disappearance clears current information but keeps the chosen modes.
                final=processes[-1];app.reconcile_streams([b]);assert a.name in app.stream_stopping
                final.returncode=0;app.reconcile_streams([b]);assert a.name not in app.stream_connections
                assert a.name not in app.streams and app.streams[b.name] is other
                connections[a.name]='';app.reconcile_streams([a,b]);app.ensure_stream(a,'play');assert len(processes)==5
                assert window.core.SETTINGS.read_bytes()==original_settings
                # One-shot identification also waits off the GTK thread and
                # discards results if a port is reused during that operation.
                connections[a.name]='boot:1-1:5';app.reconcile_streams([a,b]);app.ensure_stream(a,'play')
                direct=processes[-1];operations=[];completed=[]
                with patch.object(app,'run_operation',side_effect=lambda operation,done,*args:(operations.append(operation),completed.append(done))),\
                     patch.object(window.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{}','')) as one_shot:
                    app.action(a.name,'identify')
                    assert len(operations)==1 and direct.stdin.closed
                    operation=operations[0]
                    assert operation().returncode==1;one_shot.assert_not_called()
                    direct.returncode=0
                    assert operation().returncode==0;assert one_shot.call_count==1
                    connections[a.name]='boot:1-1:6'
                    assert operation().returncode==1;assert one_shot.call_count==1
                    connections[a.name]='boot:1-1:5'
                    def replace_during_action(*args,**kwargs):
                        connections[a.name]='boot:1-1:6'
                        return subprocess.CompletedProcess([],0,'{}','')
                    one_shot.side_effect=replace_during_action
                    assert operation().returncode==1;assert one_shot.call_count==2
                    with patch.object(window.core,'remember') as remember,patch.object(window.core,'save_reading') as save:
                        completed[0](subprocess.CompletedProcess([],0,'{}',''))
                        remember.assert_not_called();save.assert_not_called()
                    assert app.notice.get_text()==_('A conexão mudou. Abra a ação novamente no controle correto.')
                    connections[a.name]='boot:1-1:5';one_shot.side_effect=None
                    one_shot.return_value=subprocess.CompletedProcess([],0,'{"reading":{"status":"Unknown"}}','')
                    app.run(['fixture','read'],lambda result:None,connection=(a,'boot:1-1:5'))
                    def reconnect_during_pause(seconds):connections[a.name]='boot:1-1:6'
                    with patch.object(window.time,'sleep',side_effect=reconnect_during_pause):
                        assert operations[-1]().returncode==1
                    assert one_shot.call_count==3,'Retry after reconnection must not run'
                app.models['hid:fixture-a']=window.ControllerState(identity='hid:fixture-a',name='Fixture',port=a.name,
                    connected=True,confirmed=True,fresh=True,helper_ready=True,effective='play')
                with patch.object(window.core,'key',return_value='hid:replacement'),patch.object(app,'action') as action:
                    app.card_action('hid:fixture-a','identify');action.assert_not_called()
                    assert app.notice.get_text()==_('A conexão mudou. Abra a ação novamente no controle correto.')
                app.stop_stream(a.name)
                other.stdin.broken=True
                assert not app.stop_stream(b.name)
                assert other.stdin.closed and app.streams[b.name] is other and not other.waits
                other.returncode=0
                app.stop_all();assert not app.streams and other.waits==[3]
            print('STREAM RECOVERY OK: same-port reconnect without empty tick, old owner exit before replacement, nonblocking stop, timeout and late packets, mode transition, no repeated authorization on same failure, other controller and saved modes preserved. Simulated processes; no USB/suspend.')
        finally:
            for p in processes:p.returncode=0
            app.quit_app();app.destroy();pump()
