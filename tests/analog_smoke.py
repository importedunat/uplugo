# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the guided GTK workflow with deterministic samples, never USB."""
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk
from i18n import set_language, _
from input_view import InputPanel, attach_input_panel
from ui import themed_dialog, ASSETS

from theme import install_theme
install_theme()


def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)


for language in ('pt-BR','en','es'):
    set_language(language)
    dialog=themed_dialog(_('Testar botões'),None,700)
    dialog.add_button(_('Concluir'),Gtk.ResponseType.CLOSE)
    panel=InputPanel();attach_input_panel(dialog,panel)
    clock=[10.0];guide=panel.analog;guide.clock=lambda:clock[0]
    dialog.show_all();panel.pages.set_visible_child_name('analogs');pump()
    assert not guide.primary.get_sensitive()
    def sample(values):
        clock[0]+=.04
        panel.update({'buttons':[],'observed':[],'sticks':values,'triggers':[0,0],'touches':[]},clock[0])
        pump()
    sample([128]*4);assert guide.primary.get_sensitive()
    guide.primary.clicked();assert guide.session.phase=='rest'
    assert not guide.primary.get_sensitive()
    for index in range(127):sample([128+(index%2),127,128,128])
    assert guide.session.phase=='ready'
    assert guide.primary.get_label()==_('Medir alcance')
    assert 'X +0.8%' in guide.centers[0].get_text()
    assert '+1.2%' in guide.spreads[0].get_text()
    rest_count=guide.session.rest.count
    guide.primary.clicked();assert guide.session.phase=='travel'
    for index in range(91):
        angle=index*math.pi/45
        sample([round(127.5+127.5*math.cos(angle)),round(127.5+127.5*math.sin(angle)),
                round(127.5+120*math.sin(angle)),round(127.5+120*math.cos(angle))])
    assert guide.session.rest.count==rest_count
    assert all(len(guide.session.travel.directions(stick))==4 for stick in range(2))
    guide.primary.clicked();assert guide.session.phase=='done'
    saved=guide.session.travel.count
    sample([0]*4);assert guide.session.travel.count==saved
    guide.detail.set_expanded(True);pump()
    close=dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
    area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
    assert close.translate_coordinates(dialog,0,0)[1]+close.get_allocated_height()<=dialog.get_allocated_height()
    assert dialog.get_allocated_height()<=area.height and dialog.get_allocated_width()<=area.width
    panel.waiting('No live input');pump()
    assert guide.session.phase=='done' and guide.session.travel.count==saved
    assert guide.heading.get_text()==_('Resultado anterior · sem leitura atual')
    assert not guide.primary.get_sensitive()
    sample([128]*4);guide.primary.clicked();sample([128]*4)
    panel.waiting('Disconnected');pump()
    assert guide.session.phase=='interrupted' and guide.session.rest.count==0
    sample([128]*4);assert guide.session.phase=='interrupted'
    guide.primary.clicked();sample([128]*4)
    panel.pages.set_visible_child_name('controller');pump()
    assert guide.session.phase=='interrupted'
    panel.pages.set_visible_child_name('analogs');pump()
    guide.clear.clicked();assert guide.session.phase=='idle'
    assert guide.session.travel.count==0 and not guide.session.trails[0]
    dialog.destroy();pump()
set_language('pt-BR')
print('ANALOG OK: guided rest/range, frozen results, stale/reconnect, tab interruption, clear, three languages and bounded dialog; no USB.')
