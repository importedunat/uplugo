# SPDX-License-Identifier: GPL-3.0-only
"""Graphical setup states and real private install/update/remove; no host USB."""
import argparse
from contextlib import redirect_stderr
import io
from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from setup_state import SetupBackend,Overview,BASE
from setup_ui import SetupDialog
from maintenance import Locations
from distribution import inventory
from i18n import _,set_language
from theme import install_theme


def pump(delay=.06):
    start=time.monotonic()
    while True:
        while Gtk.events_pending():
            assert time.monotonic()-start<5,'GTK callbacks did not settle'
            Gtk.main_iteration_do(False)
        if time.monotonic()-start>=delay:return
        time.sleep(.005)


def until(done,timeout=20):
    end=time.monotonic()+timeout
    while not done():
        pump();assert time.monotonic()<end,'Setup test timed out'


def finished(dialog):until(lambda:not dialog.running and not dialog.checking)


def check_bounds(dialog):
    pump();area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
    width,height=dialog.get_size()
    if width>area.width:
        def walk(widget):
            minimum,natural=widget.get_preferred_width()
            if natural>area.width-100:print('WIDE:',type(widget).__name__,minimum,natural,getattr(widget,'get_text',lambda:'' )(),flush=True)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():walk(child)
        walk(dialog)
    assert width<=area.width and height<=area.height,(width,height,area.width,area.height)
    for control in (dialog.primary,dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)):
        x,y=control.translate_coordinates(dialog,0,0)
        assert control.get_mapped() and x>=0 and y>=0 and x+control.get_allocated_width()<=width and y+control.get_allocated_height()<=height


def fixture_states(output):
    for code in ('pt-BR','en','es'):
        set_language(code)
        for theme,font in (('Adwaita','Sans 10'),('HighContrast','Sans 16')):
            print('SETUP:',code,theme,font,flush=True)
            Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
            Gtk.Settings.get_default().set_property('gtk-font-name',font)
            initial=Overview(destination='/home/example/.local/share/dualsense-usb/app',
                dependencies=[{'name':'libusb','ok':True,'required':True},{'name':'Bandeja AppIndicator','ok':False,'required':False}])
            backend=Mock();backend.inspect.return_value=initial
            dialog=SetupDialog(backend);dialog.show_all();dialog.refresh();finished(dialog)
            try:
                assert dialog.primary.get_sensitive();backend.execute.assert_not_called()
                dialog.languages.set_active_id('es' if code!='es' else 'en');pump()
                assert dialog.get_title()==_('Instalação e remoção')
                dialog.languages.set_active_id(code);pump()
                check_bounds(dialog)
                dialog.resize(480,min(520,dialog.get_display().get_primary_monitor().get_workarea().height-48));check_bounds(dialog)
                for view in (replace(initial,running=True),replace(initial,root=True),replace(initial,source_error='Missing fixture'),
                             replace(initial,dependencies=[{'name':'libusb','ok':False,'required':True}])):
                    backend.inspect.return_value=view;dialog.refresh();finished(dialog)
                    assert not dialog.primary.get_sensitive();dialog.start();backend.execute.assert_not_called();check_bounds(dialog)
                backend.inspect.return_value=replace(initial,pending=True)
                dialog.refresh();finished(dialog);assert dialog.primary.get_label()==_('Recuperar instalação');check_bounds(dialog)
                backend.inspect.return_value=initial;dialog.refresh();finished(dialog)
                entered=threading.Event();release=threading.Event()
                def failure(*args):
                    entered.set();assert release.wait(5)
                    return subprocess.CompletedProcess([],1,'','Simulated failure: '+'detail '*300)
                backend.execute.side_effect=failure
                dialog.start();until(entered.is_set)
                assert dialog.running and not dialog.primary.get_sensitive()
                replies=[];dialog.connect('response',lambda d,r:replies.append(r))
                dialog.response(Gtk.ResponseType.CANCEL);assert not replies,'Closed in the middle of installation'
                release.set();finished(dialog)
                assert dialog.result.returncode and dialog.details.get_expanded();check_bounds(dialog)
                backend.execute.side_effect=None;backend.execute.return_value=subprocess.CompletedProcess([],0,'installed','')
                backend.inspect.return_value=replace(initial,installed=True,launchable=True,version='test')
                dialog.start();finished(dialog)
                assert dialog.primary.get_label()==_('Abrir app') and not dialog.finish_requested
                assert backend.execute.call_count==2
                backend.open_app.return_value=subprocess.CompletedProcess([],1,'','Launch failed')
                dialog.start();finished(dialog)
                assert dialog.primary.get_label()==_('Abrir app') and dialog.result.returncode
                backend.open_app.return_value=subprocess.CompletedProcess([],0,'','')
                dialog.start();finished(dialog)
                assert dialog.finish_requested and dialog.primary.get_label()==_('Concluir')
                dialog.start();assert backend.execute.call_count==2,'Finish repeated installation'
                dialog.choice.set_active_id('remove');assert not dialog.primary.get_sensitive()
                dialog.access.set_active(True);assert dialog.primary.get_sensitive();check_bounds(dialog)
                dialog.start();finished(dialog)
                assert backend.execute.call_args.args==('remove',True)
                assert dialog.finish_requested
                if output and code=='pt-BR':
                    dialog.choice.set_active_id('install');backend.inspect.return_value=initial;dialog.refresh();finished(dialog)
                    dialog.dependencies.set_expanded(False);dialog.details.set_expanded(False)
                    dialog.resize(min(660,dialog.get_display().get_primary_monitor().get_workarea().width),min(650,dialog.get_display().get_primary_monitor().get_workarea().height-48));pump()
                    output.mkdir(parents=True,exist_ok=True);w,h=dialog.get_size()
                    Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,w,h).savev(str(output/f'setup-{theme}-{dialog.get_scale_factor()}x.png'),'png',[],[])
            finally:dialog.destroy();pump()


def real_files():
    with tempfile.TemporaryDirectory(prefix='dualsense-setup-ui-') as temporary:
        root=Path(temporary);source=root/'download with spaces';source.mkdir()
        for name in inventory()['runtime']:
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,path)
        locations=Locations(root/'data',root/'config')
        private=[locations.config/'dualsense-usb/controllers.json',locations.base/'appearance-library/my-photo.png',root/'state/dualsense-usb/charge-history.json']
        for path in private:path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
        before={p:p.read_bytes() for p in private}
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(locations.data),'XDG_CONFIG_HOME':str(locations.config),'XDG_STATE_HOME':str(root/'state')}):
            backend=SetupBackend(source,locations)
            set_language('pt-BR');Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita');Gtk.Settings.get_default().set_property('gtk-font-name','Sans 10')
            dialog=SetupDialog(backend);dialog.show_all();dialog.refresh();finished(dialog)
            try:
                assert not locations.receipt.exists(),'Opening the assistant installed files'
                assert not dialog.access.get_active()
                dialog.start();finished(dialog)
                assert dialog.result.returncode==0,dialog.log
                assert locations.target('desktop').exists() and (locations.app/'setup.py').exists()
                # Update from the same pristine package; preserve all private data.
                dialog.refresh();finished(dialog);dialog.start();finished(dialog)
                assert dialog.result.returncode==0,dialog.log
                for path,data in before.items():assert path.read_bytes()==data
                edited=locations.app/'README.md';edited.write_text(edited.read_text()+'\nUser modification\n')
                unknown=locations.app/'notes.txt';unknown.write_text('personal note')
                # Continue from the installed copy after the download is gone.
                shutil.rmtree(source);dialog.backend=SetupBackend(locations.app,locations)
                dialog.choice.set_active_id('remove');dialog.refresh();finished(dialog)
                assert str(edited) in dialog.overview.preserve
                # The real uninstaller refuses deletion if admin authorization
                # is cancelled. Only a private fake pkexec can run in this test.
                commands=root/'commands';commands.mkdir();marker=root/'authorization-requested'
                fake=commands/'pkexec';fake.write_text('#!/usr/bin/python3\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text("called")\nraise SystemExit(126)\n');fake.chmod(0o700)
                dialog.access.set_active(True)
                with patch.dict(os.environ,{'PATH':str(commands)+os.pathsep+os.environ['PATH']}):
                    dialog.start();finished(dialog)
                assert marker.exists() and dialog.result.returncode!=0 and not dialog.finish_requested
                assert (locations.app/'window.py').exists() and locations.target('desktop').exists()
                for path,data in before.items():assert path.read_bytes()==data
                dialog.access.set_active(False)
                dialog.start();finished(dialog)
                assert dialog.result.returncode==0,dialog.log
                assert dialog.finish_requested and not locations.target('desktop').exists()
                assert not (locations.app/'window.py').exists()
                assert edited.exists() and unknown.read_text()=='personal note'
                for path,data in before.items():assert path.read_bytes()==data
            finally:dialog.destroy();pump()
        print('SETUP FILES OK: real clean install, update, removal from installed copy; simulated admin cancellation prevents deletion; edited/unknown files and private data preserved; no real admin or app launch.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    install_theme();Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
    failures=[];old=sys.excepthook
    def hook(*args):failures.append(args[1]);old(*args)
    sys.excepthook=hook
    try:
        import setup as bootstrap
        with patch.object(sys,'argv',['setup.py']),patch.object(Gtk,'init_check',return_value=(False,[])),redirect_stderr(io.StringIO()) as error:
            assert bootstrap.main()==1 and _('Abra o assistente dentro da sua sessão gráfica.') in error.getvalue()
        with patch.object(sys,'argv',['setup.py']),patch.dict(sys.modules,{'setup_ui':None}),patch.object(Gtk,'MessageDialog') as message:
            assert bootstrap.main()==1
            message.return_value.run.assert_called_once();message.return_value.destroy.assert_called_once()
        fixture_states(args.output);real_files();assert not failures,'GTK callback failure'
        from tests.setup_lifecycle import exercise
        print('SETUP LIFECYCLE:',exercise())
    finally:sys.excepthook=old
    print('SETUP OK: three languages, small/large-font/high-contrast UI, blocked states, guarded progress, failure/retry, launch request, explicit admin removal choice and real private files.')


if __name__=='__main__':main()
