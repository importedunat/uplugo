# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK motion tab with synthetic reports; no controller access."""
import argparse
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from i18n import set_language,_
from input_view import InputPanel,attach_input_panel
from motion_trace import motion_demo
from ui import themed_dialog
from theme import install_theme


def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)


parser=argparse.ArgumentParser();parser.add_argument('--preview',type=Path);args=parser.parse_args()
install_theme();settings=Gtk.Settings.get_default();timings=[]
for language in ('pt-BR','en','es'):
    set_language(language)
    for font in ('Sans 10','Sans 18'):
        settings.set_property('gtk-font-name',font)
        dialog=themed_dialog(_('Testar botões'),None,700)
        dialog.add_button(_('Concluir'),Gtk.ResponseType.CLOSE)
        panel=InputPanel();scroll=attach_input_panel(dialog,panel)
        dialog.show_all();panel.pages.set_visible_child_name('motion');pump()
        clock=[10.0]
        def sample(frame,motion=True):
            clock[0]+=.04
            panel.update({'buttons':[],'observed':[],'sticks':[128]*4,'triggers':[0,0],
                          'touches':[],'motion':motion_demo(frame) if motion else None},clock[0]);pump()
        assert not panel.motion.clear_button.get_sensitive()
        start=time.monotonic()
        for frame in range(80):sample(frame)
        timings.append((time.monotonic()-start)/80)
        assert '°/s' in panel.motion.values[0].get_text() and 'g' in panel.motion.values[1].get_text()
        assert len(panel.motion.trace.samples)==80
        panel.motion.detail.set_expanded(True);pump()
        area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
        dialog.resize(min(480,area.width),min(640,area.height-48));pump()
        # Allow queued GTK allocation before checking bounds.
        for allocation_tick in range(8):time.sleep(.02);pump()
        close=dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
        assert dialog.get_allocated_height()<=area.height and dialog.get_allocated_width()<=area.width,(language,font,dialog.get_size(),area.width,area.height)
        assert close.translate_coordinates(dialog,0,0)[1]+close.get_allocated_height()<=dialog.get_allocated_height()
        assert close.get_sensitive() and close.get_mapped()
        panel.pages.set_visible_child_name('controller');pump()
        assert not panel.motion.trace.samples
        sample(81);assert not panel.motion.trace.samples
        panel.pages.set_visible_child_name('motion');pump();assert len(panel.motion.trace.samples)==1
        panel.motion.clear_button.clicked();assert not panel.motion.trace.samples
        sample(82);panel.waiting('Disconnected');pump()
        assert not panel.motion.trace.samples and panel.motion.trace.current is None
        assert panel.motion.values[0].get_text()==_('Sem leitura calibrada')
        sample(83,False);assert panel.motion.trace.current is None
        for frame in range(84,100):sample(frame)
        for stalled_tick in range(16):sample(99)
        assert panel.motion.trace.stalled and not panel.motion.trace.samples
        for frame in range(100,350):sample(frame)
        if args.preview and font=='Sans 10':
            panel.motion.detail.set_expanded(False);dialog.resize(min(700,area.width),min(900,area.height-48));pump()
            for allocation_tick in range(6):time.sleep(.02);pump()
            args.preview.mkdir(exist_ok=True,parents=True)
            Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,*dialog.get_size()).savev(str(args.preview/(language+'.png')),'png',[],[])
        settings.set_property('gtk-theme-name','HighContrast');pump();sample(351)
        settings.set_property('gtk-theme-name','Adwaita');dialog.destroy();pump()
print('MOTION UI OK: three languages, font sizes 10/18, bounded scroll, readouts, traces, missing/stalled input, recovery, hidden-tab clearing and HighContrast; synthetic data only.')
print('Mean update/render seconds per scenario:',[round(value,5) for value in timings])
