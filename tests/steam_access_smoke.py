# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK permission choices; backend, authorization and devices are simulated."""
import argparse,copy,subprocess,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from i18n import _,set_language
from theme import install_theme
from steam_access_ui import SteamAccessDialog
from tests.touchpad_smoke import pump,until


class Backend:
    def __init__(self):
        self.state={'identity':'00:11:22:33:44:55','saved':'system','nodes':[{'node':'hidraw0','tagged':False}],
                    'environment':{'available':True,'reason':'ready','helper':'usr/lib/snapd/snap-device-helper'}}
        self.calls=[];self.code=0;self.pending=False;self.reached=self.release=None
    def inspect(self):return copy.deepcopy(self.state)
    def apply(self,choice):
        self.calls.append(choice)
        if self.reached:self.reached.set();assert self.release.wait(8)
        if not self.code:
            self.state['saved']=choice
            self.state['nodes']=[] if self.pending else [{'node':'hidraw0','tagged':choice=='allow'}]
        return subprocess.CompletedProcess([],self.code,'','{"error":"apply-failed-restored"}' if self.code==1 else ''),{'choice':choice,'pending':self.pending,'refreshed':0 if self.pending else 1},self.inspect()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',type=Path);args=parser.parse_args();install_theme()
    for language in ('pt-BR','en','es'):
        set_language(language)
        for font in ('Sans 10','Sans 18'):
            Gtk.Settings.get_default().set_property('gtk-font-name',font)
            backend=Backend();dialog=SteamAccessDialog('hid:'+backend.state['identity'],'Meu DualSense',backend=backend)
            try:
                until(lambda:not dialog.busy)
                assert not dialog.primary.get_sensitive(),'Removing an absent grant must not ask for authorization'
                self_close=dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
                dialog.radios['allow'].set_active(True);pump();assert not backend.calls
                area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
                dialog.resize(min(480,area.width),min(600,area.height-48));pump()
                width,height=dialog.get_size();assert width<=area.width and height<=area.height
                for control in (dialog.primary,self_close):
                    x,y=control.translate_coordinates(dialog,0,0)
                    assert control.get_mapped() and x>=0 and y>=0 and x+control.get_allocated_width()<=width and y+control.get_allocated_height()<=height
                    assert control.get_child().get_layout().get_line_count()<=2
                if args.preview and font=='Sans 10':
                    args.preview.mkdir(parents=True,exist_ok=True)
                    Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height).savev(str(args.preview/(language+'.png')),'png',[],[])
                backend.code=126;dialog.response(Gtk.ResponseType.APPLY);until(lambda:not dialog.busy)
                assert backend.state['saved']=='system' and dialog.status.get_text()==_('Autorização cancelada. A escolha anterior foi mantida.')
                backend.code=1;dialog.apply();until(lambda:not dialog.busy);assert dialog.details.get_expanded()
                backend.code=0;backend.reached=threading.Event();backend.release=threading.Event()
                dialog.apply();until(backend.reached.is_set)
                assert dialog.busy and not dialog.primary.get_sensitive() and not self_close.get_sensitive()
                received=[];token=dialog.connect('response',lambda *a:received.append(True))
                dialog.response(Gtk.ResponseType.CLOSE);assert not received;dialog.disconnect(token)
                backend.release.set();until(lambda:not dialog.busy);assert backend.state['saved']=='allow'
                assert dialog.saved.get_text()==_('Permissão salva e reconhecida pelo Linux. Reabra a Steam e confira o clique no jogo.')
                backend.reached=None;backend.pending=True;dialog.radios['system'].set_active(True);dialog.apply();until(lambda:not dialog.busy)
                assert backend.state['saved']=='system' and not backend.state['nodes']
                backend.state['environment']={'available':False,'reason':'no-snap','helper':None}
                dialog.refresh();until(lambda:not dialog.busy)
                dialog.radios['allow'].set_active(True);assert not dialog.primary.get_sensitive()
                dialog.radios['system'].set_active(True);assert not dialog.primary.get_sensitive()
                backend.state['saved']='allow';dialog.refresh();until(lambda:not dialog.busy)
                dialog.radios['system'].set_active(True);assert dialog.primary.get_sensitive(),'Owned grant must remain removable without Snap'
                backend.state['saved']='custom';dialog.refresh();until(lambda:not dialog.busy)
                assert not dialog.primary.get_sensitive();calls=len(backend.calls);dialog.apply();assert len(backend.calls)==calls
                backend.state['saved']='system';backend.state['nodes']=[{'node':'hidraw0','tagged':True}]
                dialog.refresh();until(lambda:not dialog.busy)
                assert dialog.saved.get_text()==_('Este app não tem uma permissão salva, mas outra configuração já registra acesso para a Steam. Ela será preservada.')
                Gtk.Settings.get_default().set_property('gtk-theme-name','HighContrast');pump()
                assert not dialog.closed
            finally:
                dialog.destroy();Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita');pump()
    print('STEAM ACCESS UI OK: pt-BR/en/es, fonts 10/18, bounded actions, draft/cancel/error/responsive apply, grant/revoke, absent Snap, absent controller, custom/external grants preserved. Simulated backend only.')


if __name__=='__main__':main()
