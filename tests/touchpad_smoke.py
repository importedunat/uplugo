# SPDX-License-Identifier: GPL-3.0-only
"""Touchpad GTK interactions with simulated authorization; no host rule or USB."""
import argparse
import copy
from pathlib import Path
import subprocess
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from touchpad_ui import TouchpadDialog
from i18n import _,set_language
from theme import install_theme
from tests.accessibility_smoke import key


def pump(delay=.06):
    end=time.monotonic()+delay
    while True:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        if time.monotonic()>=end:return
        time.sleep(.005)


def until(done):
    end=time.monotonic()+10
    while not done():pump();assert time.monotonic()<end,'Touchpad dialog timed out'
    pump()


class Backend:
    def __init__(self):
        self.state={'identity':'02:00:00:00:00:01','saved':'system','nodes':[{'event':'event4','ignored':False}]}
        self.code=0;self.calls=[];self.reached=None;self.release=None;self.pending=False
    def inspect(self):return copy.deepcopy(self.state)
    def apply(self,choice):
        self.calls.append(choice)
        if self.reached:self.reached.set();assert self.release.wait(8)
        if not self.code:self.state['saved']=choice;self.state['nodes']=[{'event':'event4','ignored':choice=='game'}] if not self.pending else []
        result=subprocess.CompletedProcess([],self.code,'','{"error":"apply-failed-restored"}' if self.code==1 else '')
        return result,{'pending':self.pending,'refreshed':0 if self.pending else 1,'choice':choice},self.inspect()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',type=Path);args=parser.parse_args();install_theme()
    for code,font in ((code,font) for code in ('pt-BR','en','es') for font in ('Sans 10','Sans 18')):
        Gtk.Settings.get_default().set_property('gtk-font-name',font)
        set_language(code);backend=Backend();dialog=TouchpadDialog('hid:'+backend.state['identity'],'Meu DualSense',backend=backend)
        try:
            until(lambda:not dialog.busy)
            area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
            dialog.resize(min(480,area.width),min(560,area.height-48));pump()
            assert dialog.radios['system'].get_active() and dialog.primary.get_sensitive()
            demo=dialog.preview
            demo.move(.2,.3);assert demo.cursor==demo.position
            demo.grab_focus();key(dialog,Gdk.KEY_Right);assert abs(demo.position[0]-.3)<.001
            before=demo.position
            event=Gdk.Event.new(Gdk.EventType.BUTTON_PRESS);event.button=1
            event.x=100*demo.get_allocated_width()/560;event.y=70*demo.get_allocated_width()/560
            demo.emit('button-press-event',event);assert demo.dragging and demo.position!=before
            event=Gdk.Event.new(Gdk.EventType.BUTTON_RELEASE);event.button=1
            demo.emit('button-release-event',event);assert not demo.dragging
            dialog.radios['game'].set_active(True);pump();assert backend.calls==[]
            assert demo.choice=='game' and demo.cursor==(.5,.5)
            demo.move(.9,.8);assert demo.cursor==(.5,.5)
            dialog.radios['system'].set_active(True);assert demo.cursor==demo.position
            dialog.radios['game'].set_active(True);assert backend.calls==[]
            area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
            width,height=dialog.get_size();assert width<=area.width and height<=area.height,(code,font,width,height,area.width,area.height)
            for control in (dialog.primary,dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)):
                x,y=control.translate_coordinates(dialog,0,0)
                assert control.get_mapped() and x>=0 and y>=0 and x+control.get_allocated_width()<=width and y+control.get_allocated_height()<=height
                assert control.get_child().get_layout().get_line_count()<=2,'Action label became an unreadable narrow column'
            if args.preview and font=='Sans 10':
                args.preview.mkdir(parents=True,exist_ok=True)
                Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height).savev(str(args.preview/(code+'.png')),'png',[],[])
            backend.code=126;dialog.response(Gtk.ResponseType.APPLY);until(lambda:not dialog.busy)
            assert dialog.status.get_text()==_('Autorização cancelada. A escolha anterior foi mantida.')
            assert backend.state['saved']=='system' and not dialog.closed
            backend.code=1;dialog.apply();until(lambda:not dialog.busy)
            assert dialog.status.get_text()==_('Não foi possível aplicar. A regra anterior foi restaurada; tente novamente.')
            assert dialog.details.get_expanded()
            backend.code=0;backend.reached=threading.Event();backend.release=threading.Event()
            dialog.apply();until(backend.reached.is_set)
            assert dialog.busy and not dialog.primary.get_sensitive()
            received=[];token=dialog.connect('response',lambda *a:received.append(True))
            dialog.response(Gtk.ResponseType.CLOSE);assert not received and not dialog.closed
            dialog.disconnect(token);backend.release.set();until(lambda:not dialog.busy)
            assert backend.state['saved']=='game' and dialog.saved.get_text()==_('Regra de mouse bloqueado registrada no Linux.')
            assert not dialog.details.get_expanded()
            backend.reached=None;backend.pending=True;dialog.radios['system'].set_active(True);dialog.apply();until(lambda:not dialog.busy)
            assert backend.state['saved']=='system' and dialog.status.get_text()==_('Configuração salva. Será usada quando o touchpad voltar a aparecer no Linux.')
            backend.state['saved']='custom';dialog.refresh();until(lambda:not dialog.busy)
            assert not dialog.primary.get_sensitive()
            count=len(backend.calls);dialog.apply();assert len(backend.calls)==count
        finally:dialog.destroy();pump()
    print('TOUCHPAD UI OK: pt-BR/en/es, draft choice, cancelled/failed authorization, responsive apply, custom policy preservation, disconnected controller, bounded actions. Authorization and system refresh simulated.')


if __name__=='__main__':main()
