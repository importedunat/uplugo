# SPDX-License-Identifier: GPL-3.0-only
"""Visible recovery states in three languages. All operations are fixtures."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from maintenance import Locations
from recovery_ui import RecoveryDialog
from i18n import set_language,_
from ui import ASSETS

from theme import install_theme
install_theme()
def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)
def until(done):
    deadline=time.monotonic()+5
    while not done():
        pump()
        assert time.monotonic()<deadline,'Timed out'
        time.sleep(.01)

with tempfile.TemporaryDirectory() as temporary:
    locations=Locations(Path(temporary)/'data',Path(temporary)/'config')
    locations.app.mkdir(parents=True)
    for code in ('pt-BR','en','es'):
        set_language(code)
        release=threading.Event()
        def operation():
            assert release.wait(3)
            return subprocess.CompletedProcess([],1,'','Simulated failure: '+'detail '*200)
        dialog=RecoveryDialog(locations,operation);dialog.show_all();pump()
        responses=[];dialog.connect('response',lambda d,r:responses.append(r))
        dialog.start();pump()
        assert dialog.running and not dialog.primary.get_sensitive()
        assert not dialog.get_widget_for_response(Gtk.ResponseType.CANCEL).get_sensitive()
        dialog.response(Gtk.ResponseType.CANCEL);assert responses==[]
        release.set();until(lambda:not dialog.running)
        assert not dialog.recovered and dialog.details.get_visible()
        assert dialog.primary.get_label()==_('Tentar novamente')
        pump()
        area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
        close=dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
        assert dialog.get_allocated_height()<=area.height and dialog.get_allocated_width()<=area.width
        assert close.translate_coordinates(dialog,0,0)[1]+close.get_allocated_height()<=dialog.get_allocated_height()
        (locations.app/'launch.py').write_text('# fixture')
        dialog.operation=lambda:subprocess.CompletedProcess([],0,'restored','')
        dialog.start();until(lambda:not dialog.running)
        assert dialog.recovered and dialog.can_open and dialog.primary.get_label()==_('Abrir app')
        assert dialog.heading.get_text()==_('Tudo pronto para abrir o app')
        dialog.destroy();pump()
        (locations.app/'launch.py').unlink()
        dialog=RecoveryDialog(locations,lambda:subprocess.CompletedProcess([],0,'removed',''))
        dialog.show_all();dialog.start();until(lambda:not dialog.running)
        assert dialog.recovered and not dialog.can_open and not dialog.primary.get_visible()
        dialog.destroy();pump()
print('RECOVERY OK: responsive progress, guarded close, failure/retry, restored app and removed first installation, three languages; no real maintenance or USB.')
