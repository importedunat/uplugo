# SPDX-License-Identifier: GPL-3.0-only
"""Exercise battery history under Xvfb, never hardware or personal data."""
from pathlib import Path
import argparse
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from charge_watch import ChargeWatch
from charge_view import BatteryPanel,attach_battery_panel,session_change
from presentation import ControllerState
from i18n import set_language,_
from ui import themed_dialog,ASSETS

from theme import install_theme
install_theme()
parser=argparse.ArgumentParser();parser.add_argument('--preview',type=Path);args=parser.parse_args()
def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)

with tempfile.TemporaryDirectory() as temp:
    for language in ('pt-BR','en','es'):
        set_language(language)
        watch=ChargeWatch(Path(temp)/(language+'.json'))
        state=ControllerState('sample','Player 02',port='1-2',fresh=True,connected=True,
                              reading={'capacity':65,'status':'Charging','time':'12:00'})
        dialog=themed_dialog(_('Bateria e conexão'),None)
        dialog.add_button(_('Fechar'),Gtk.ResponseType.CLOSE)
        panel=BatteryPanel(state.name);attach_battery_panel(dialog,panel)
        panel.update(watch,'sample',state,1000)
        assert panel.change.get_text()==_('Ainda não há observações para este controle.')
        assert panel.plot.samples==() and not panel.plot.fresh
        for index in range(26):
            at=1000+index*100
            watch.observe('sample',str(index),{'capacity':25,'status':'Charging'},at,port='3-4')
            watch.observe('sample',str(index),{'capacity':35,'status':'Charging'},at+10,port='3-4')
        now=4000
        watch.observe('sample','current',state.reading,now,port='1-2')
        panel.update(watch,'sample',state,now)
        assert len(panel.history_box.get_children())==24
        assert panel.plot.samples==tuple((s['at'],s['capacity']) for s in watch.entries['sample']['samples'])
        assert '65%' in panel.value.get_text() and _('Carregando') in panel.value.get_text()
        assert panel.change.get_text()==session_change(watch.sessions('sample',now)[0])
        dialog.show_all();panel.history.set_expanded(True);panel.details.set_expanded(True);pump()
        previous=panel.history_box.get_children()[0]
        close=dialog.get_widget_for_response(Gtk.ResponseType.CLOSE);close.grab_focus();pump()
        panel.update(watch,'sample',state,now+3);pump()
        assert panel.history_box.get_children()[0] is previous
        assert dialog.get_focus() is close
        area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
        assert dialog.get_allocated_height()<=area.height and dialog.get_allocated_width()<=area.width
        assert close.translate_coordinates(dialog,0,0)[1]+close.get_allocated_height()<=dialog.get_allocated_height()
        panel.update(watch,'sample',state,now+7)
        assert _('Leitura anterior') in panel.value.get_text()
        assert not panel.plot.fresh and _('Leitura anterior') in panel.plot.get_accessible().get_description()
        assert panel.observation.get_text()==_('Sem leitura USB recente; aguardando o controle.')
        state.connected=False;state.fresh=False
        panel.update(watch,'sample',state,now+8)
        assert _('desconectado') in panel.connection.get_text()
        assert len(panel.history_box.get_children())==24
        assert panel.plot.samples==((now,65),), 'Chart bridged separate observations'
        for font in ('Sans 10','Sans 18'):
            Gtk.Settings.get_default().set_property('gtk-font-name',font)
            editor=panel.edit_note();pump()
            editor.entry.set_text('Cabo azul · sem hub')
            sid=editor.session_id
            # The timer continues to refresh without touching the editor draft.
            panel.update(watch,'sample',state,now+9);pump()
            assert editor.entry.get_text()=='Cabo azul · sem hub'
            editor.response(Gtk.ResponseType.CANCEL);pump()
            assert watch.sessions('sample',now+9)[0]['note']==''
            editor=panel.edit_note();editor.entry.set_text('Cabo azul · sem hub');pump()
            area=editor.get_display().get_monitor_at_window(editor.get_window()).get_workarea()
            assert editor.get_allocated_width()<=area.width and editor.get_allocated_height()<=area.height
            for response in (Gtk.ResponseType.CANCEL,Gtk.ResponseType.APPLY):
                action=editor.get_widget_for_response(response)
                x,y=action.translate_coordinates(editor,0,0)
                assert x>=0 and y>=0 and x+action.get_allocated_width()<=editor.get_allocated_width()
                assert y+action.get_allocated_height()<=editor.get_allocated_height()
            if args.preview and font=='Sans 10':
                args.preview.mkdir(parents=True,exist_ok=True)
                Gdk.pixbuf_get_from_window(editor.get_window(),0,0,editor.get_allocated_width(),editor.get_allocated_height()).savev(str(args.preview/(language+'.png')),'png',[],[])
            with patch.object(watch,'flush',side_effect=OSError('disk full')):
                editor.response(Gtk.ResponseType.APPLY);pump()
            assert editor.get_visible() and editor.entry.get_text()=='Cabo azul · sem hub'
            assert editor.error.get_text()==_('Não foi possível salvar. Sua anotação continua aqui; tente novamente.')
            # Saving after reconnection must annotate the old period, never the new cable.
            now+=100
            watch.observe('sample',str(now),state.reading,now,port='9-1')
            panel.update(watch,'sample',state,now);pump()
            editor.response(Gtk.ResponseType.APPLY);pump()
            periods=watch.sessions('sample',now)
            assert periods[0]['note']=='' and periods[1]['session_id']==sid
            assert periods[1]['note']=='Cabo azul · sem hub'
            restored=ChargeWatch(watch.path)
            assert restored.sessions('sample',now)[1]['note']=='Cabo azul · sem hub'
            editor=panel.edit_note(periods[1]);editor.entry.set_text('');editor.response(Gtk.ResponseType.APPLY);pump()
            assert watch.sessions('sample',now)[1]['note']==''
        Gtk.Settings.get_default().set_property('gtk-font-name','Sans 10')
        dialog.destroy();pump()
print('BATTERY OK: empty/live/stale/disconnected, retained sessions, stable focus, note drafts/cancel/retry/reconnect/save/remove, private persistence, font 10/18 and scrollable actions in three languages; no USB.')
