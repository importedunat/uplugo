# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK + per-account files for native migration; no USB or real pkexec."""
import argparse
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
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',type=Path);args=parser.parse_args()
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk
    from setup_ui import SetupDialog
    from setup_state import SetupBackend
    from distribution import inventory
    from maintenance import Locations
    from app_info import VERSION
    from i18n import _,set_language
    from theme import install_theme
    import migration,deployment,setup_state,access_request
    install_theme()
    def pump(delay=.06):
        start=time.monotonic()
        while True:
            while Gtk.events_pending():
                assert time.monotonic()-start<5,'GTK callbacks did not settle'
                Gtk.main_iteration_do(False)
            if time.monotonic()-start>=delay:return
            time.sleep(.005)
    def until(done):
        end=time.monotonic()+15
        while not done():pump();assert time.monotonic()<end,'Migration UI timed out';time.sleep(.02)
        pump()
    with tempfile.TemporaryDirectory(prefix='dualsense-migration-ui-') as temporary:
        root=Path(temporary);program=root/'system';program.mkdir()
        for name in inventory()['runtime']:
            path=program/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,path)
        (program/'system-package.json').write_text(json.dumps({'format':1,'version':VERSION,'manager':'deb'}))
        before={p.relative_to(program):p.read_bytes() for p in program.rglob('*') if p.is_file()}
        for code in ('pt-BR','en','es'):
            set_language(code);loc=Locations(root/code/'data',root/code/'config')
            loc.app.mkdir(parents=True);(loc.app/'modified.py').write_text('modified code');(loc.app/'unknown.txt').write_text('keep')
            (loc.app/'controllers.json').write_text('{"names":{"fixture":"Meu controle"},"modes":{"fixture":"charge"}}')
            for key in ('desktop','icon','service'):
                path=loc.target(key);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('old '+key)
            photo=loc.base/'appearance-library/photo.png';photo.parent.mkdir();photo.write_bytes(b'photo')
            access_exists=[True]
            with patch.object(deployment,'SYSTEM_APP',program),patch.object(migration,'systemd_available',return_value=False),patch.object(setup_state,'checks',return_value=[]),patch.object(access_request,'legacy_access_present',side_effect=lambda:access_exists[0]),patch.dict(os.environ,{'XDG_STATE_HOME':str(root/code/'state')}):
                backend=SetupBackend(program,loc);dialog=SetupDialog(backend);dialog.show_all();dialog.refresh();until(lambda:not dialog.checking)
                try:
                    dialog.resize(480,520);pump()
                    assert dialog.primary.get_label()==_('Migrar para a versão do sistema') and dialog.primary.get_sensitive()
                    assert str(loc.app) in dialog.details_text.get_text()
                    assert not dialog.open_button.get_visible() and not dialog.native_access_box.get_visible()
                    area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
                    width,height=dialog.get_size();assert width<=area.width and height<=area.height
                    for control in (dialog.primary,dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)):
                        x,y=control.translate_coordinates(dialog,0,0)
                        assert control.get_mapped() and x>=0 and y>=0
                        assert x+control.get_allocated_width()<=width and y+control.get_allocated_height()<=height
                    if args.preview:
                        args.preview.mkdir(parents=True,exist_ok=True);time.sleep(.1);pump()
                        Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height).savev(str(args.preview/(code+'.png')),'png',[],[])
                    # Failure after a real file move refreshes the preview to a
                    # resumable action, and the UI stays responsive throughout.
                    reached=threading.Event();release=threading.Event()
                    def stop(name):
                        if name=='moved-service':
                            reached.set();assert release.wait(8);raise OSError('simulated interruption')
                    with patch.object(migration,'checkpoint',side_effect=stop):
                        dialog.start();until(reached.is_set)
                        assert dialog.running and not dialog.primary.get_sensitive()
                        dialog.response(Gtk.ResponseType.CANCEL);assert not dialog.closed
                        release.set();until(lambda:not dialog.running)
                    assert dialog.result.returncode!=0 and dialog.overview.migration_action=='resume_migration'
                    assert dialog.primary.get_label()==_('Concluir migração')
                    dialog.start();until(lambda:not dialog.running)
                    assert dialog.result.returncode==0 and not dialog.primary.get_visible(),(dialog.log,dialog.overview,dialog.primary.get_visible())
                    assert dialog.open_button.get_visible() and dialog.open_button.get_sensitive()
                    assert dialog.legacy_access_box.get_visible()
                    assert not loc.app.exists() and photo.read_bytes()==b'photo'
                    preferences=json.loads((loc.config/'dualsense-usb/controllers.json').read_text())
                    assert preferences['names']['fixture']=='Meu controle' and preferences['modes']['fixture']=='charge'
                    record=json.loads(next((loc.base/'migrations').glob('*.json')).read_text())
                    assert (migration.backup_for(loc,'app',record['id'])/'unknown.txt').read_text()=='keep'
                    with patch.object(access_request,'remove_legacy_access',return_value=subprocess.CompletedProcess([],126,'','cancelled')) as removal:
                        dialog.remove_legacy_access();until(lambda:not dialog.running)
                        removal.assert_called_once_with(program)
                        assert dialog.status.get_text()==_('Limpeza cancelada. O suporte USB antigo foi mantido.')
                    def remove(directory):
                        access_exists[0]=False;return subprocess.CompletedProcess([],0,'removed','')
                    with patch.object(access_request,'remove_legacy_access',side_effect=remove):
                        dialog.remove_legacy_access();until(lambda:not dialog.running)
                    assert dialog.status.get_text()==_('Suporte USB antigo removido. O suporte da versão do sistema foi mantido.')
                    assert not dialog.legacy_access_box.get_visible()
                finally:dialog.destroy();pump()
        assert before=={p.relative_to(program):p.read_bytes() for p in program.rglob('*') if p.is_file()}
    print('MIGRATION UI OK: pt-BR/en/es; preview, responsive interrupted/resumed file moves, names/photos/modes retained, native program unchanged; old USB cleanup authorization simulated.')


if __name__=='__main__':main()
