#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Interactive offline lab: synthetic controllers, no service/USB/network access."""
from i18n import _
import math
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from presentation import ControllerState
from ui import Dashboard, ContentClamp, EffectsEditor, style, label, themed_dialog, ASSETS
from input_view import InputPanel, attach_input_panel
from input_state import BUTTON_NAMES
from motion_trace import motion_demo


SCENARIOS = [('normal', 'Dois controles'), ('empty', 'Sem controles'),
             ('unplug', 'Controle desconectado'), ('stale', 'Leitura desatualizada'),
             ('error', 'Falha de conexão'), ('setup', 'Acesso não configurado')]


class DevelopmentWindow(Gtk.Window):
    preview = True
    busy = False

    def __init__(self):
        super().__init__(title=_('Uplugo · Laboratório sem USB'))
        style(self, 'dualsense')
        from layout import fit_window,AdaptiveBox
        fit_window(self,1040,940)
        self.generation = 0
        self.pending = set()
        self.models = {}
        self.effects = {}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = style(AdaptiveBox(spacing=12), 'notice');bar.set_border_width(12)
        bar.pack_start(label(_('LABORATÓRIO · dados simulados · sem USB'), 'setting-title',wrap=True), True, True, 0)
        self.scenario = Gtk.ComboBoxText()
        for key,title in SCENARIOS:self.scenario.append(key,_(title))
        self.scenario.set_active_id('normal')
        bar.pack_end(self.scenario, False, False, 0)
        box.pack_start(bar, False, False, 0)
        self.dashboard = Dashboard(self)
        self.dashboard.footer_note.set_text(_('Simulação isolada. Fechar encerra este laboratório.'))
        box.pack_start(ContentClamp(self.dashboard), True, True, 0)
        self.add(box)
        self.scenario.connect('changed',lambda widget:self.reset(widget.get_active_id()))
        self.connect('destroy',lambda widget:self.cleanup())
        self.reset('normal')

    def reset(self, scenario):
        self.current_scenario = scenario
        self.generation += 1
        for source in self.pending:GLib.source_remove(source)
        self.pending.clear()
        self.models = {f'simulated:{i}': ControllerState(f'simulated:{i}',_('Controle de teste {0}').format(i+1),
                      port=f'0-{i+1}',requested=mode,effective=mode,confirmed=True,fresh=True,
                      appearance=appearance,reading={'capacity':capacity,'status':status,'time':_('Simulado')})
                      for i,(mode,appearance,capacity,status) in enumerate([
                          ('proxy','black',75,'Discharging'),('charge','white',35,'Charging')])}
        first = self.models['simulated:0']
        if scenario=='empty':self.models={}
        elif scenario=='unplug':first.connected=False;first.fresh=False;first.confirmed=False
        elif scenario=='stale':first.fresh=False;first.confirmed=False
        elif scenario=='error':first.error=_('Falha simulada. Escolha Dois controles para recuperar.')
        elif scenario=='setup':
            for model in self.models.values():model.helper_ready=False;model.confirmed=False
        self.dashboard.notice.set_text('')
        self.render()

    def render(self):
        self.dashboard.update(list(self.models.values()), self.current_scenario!='setup')
        self.dashboard.count.set_text(_('SIMULAÇÃO · seus controles reais permanecem como estão'))

    def request_mode(self, identity, mode):
        model=self.models.get(identity)
        if not model or not model.can_change:return
        model.requested=mode;model.transition=True;model.confirmed=False
        self.render();generation=self.generation
        def confirm():
            self.pending.discard(source)
            if self.generation==generation and self.models.get(identity) is model:
                model.effective=mode;model.transition=False;model.confirmed=True
                self.render()
            return False
        source=GLib.timeout_add(600,confirm);self.pending.add(source)

    def card_action(self, identity, action):
        model=self.models.get(identity)
        if not model:return
        if action=='input':
            dialog=themed_dialog(_('Testar botões · simulação'),self,700)
            dialog.add_button(_('Concluir'),Gtk.ResponseType.CLOSE)
            dialog.get_content_area().pack_start(label(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'),'warning',wrap=True),False,False,0)
            panel=InputPanel();attach_input_panel(dialog,panel)
            frame=0
            def animate():
                nonlocal frame
                frame+=1
                held=[BUTTON_NAMES[(frame//15)%len(BUTTON_NAMES)]] if frame%15<10 else []
                sticks=([128+round(math.sin(frame/9)),127,128,128]
                        if panel.analog.session.phase in ('rest','ready') else
                        [round(127.5+127.5*math.sin(frame/25+phase)) for phase in (0,1.57,3.14,4.71)])
                panel.update({'buttons':held,'observed':held,
                              'motion':motion_demo(frame),
                              'sticks':sticks,
                              'triggers':[round(127.5+127.5*math.sin(frame/40+phase)) for phase in (0,3.14)],
                              'touches':[{'slot':slot,'id':slot,'x':round(959.5+800*math.sin(frame/40+slot*3.14)),
                                          'y':round(539.5+400*math.cos(frame/50+slot*3.14))}
                                         for slot in range(2) if frame%150<110]})
                return True
            timer=GLib.timeout_add(33,animate)
            try:dialog.show_all();dialog.run()
            finally:GLib.source_remove(timer);dialog.destroy()
        elif action=='details':
            import tempfile
            import time
            from pathlib import Path
            from charge_watch import ChargeWatch
            from charge_view import BatteryPanel, attach_battery_panel
            with tempfile.TemporaryDirectory() as temporary:
                watch=ChargeWatch(Path(temporary)/'synthetic.json')
                watch.flush=lambda:None
                now=time.time()
                watch.observe(identity,'previous',{'capacity':25,'status':'Charging'},now-120,port='2-1')
                watch.observe(identity,'previous',{'capacity':35,'status':'Charging'},now-110,port='2-1')
                dialog=themed_dialog(_('Bateria e conexão'),self)
                dialog.add_button(_('Fechar'),Gtk.ResponseType.CLOSE)
                panel=BatteryPanel(model.name)
                banner=label(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'),'warning',wrap=True)
                panel.pack_start(banner,False,False,0);panel.reorder_child(banner,1)
                attach_battery_panel(dialog,panel)
                def update_battery():
                    if model.connected and model.fresh:
                        watch.observe(identity,'current',model.reading,port='1-2')
                    panel.update(watch,identity,model)
                    return True
                update_battery();timer=GLib.timeout_add_seconds(1,update_battery)
                try:dialog.show_all();dialog.run()
                finally:GLib.source_remove(timer);dialog.destroy()
        elif action=='effects':
            dialog=themed_dialog(_('Luzes e efeitos · simulação'),self,590)
            dialog.add_buttons(_('Cancelar'),Gtk.ResponseType.CANCEL,_('Salvar na simulação'),Gtk.ResponseType.OK)
            editor=EffectsEditor(self.effects.get(identity,{'rgb':[0,120,255],'vibration':'game','triggers':'game'}))
            dialog.get_content_area().pack_start(label(_('Rascunho local desta simulação. Sem comandos USB.'),'warning',wrap=True),False,False,0)
            dialog.get_content_area().pack_start(editor,False,False,0)
            dialog.show_all()
            if dialog.run()==Gtk.ResponseType.OK:self.effects[identity]=editor.values()
            dialog.destroy()
        else:self.dashboard.notice.set_text(_('Ação simulada: ')+action+_('. Nenhuma preferência ou controle real foi alterado.'))

    def install(self):self.reset('normal');self.scenario.set_active_id('normal')
    def profiles_dialog(self):self.dashboard.notice.set_text(_('Regras de jogos reais não são executadas no laboratório.'))
    def about_dialog(self):pass
    def photos_dialog(self):pass
    def development_dialog(self):pass
    def quit_app(self):self.destroy()
    def cleanup(self):
        for source in self.pending:GLib.source_remove(source)
        self.pending.clear()


def main():

    from theme import install_theme
    install_theme()
    window=DevelopmentWindow();window.connect('destroy',Gtk.main_quit)
    window.show_all();window.render();Gtk.main()


if __name__=='__main__':main()
