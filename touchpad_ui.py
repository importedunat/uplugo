# SPDX-License-Identifier: GPL-3.0-only
"""Per-controller pointer choice; authorization and checks run off the GTK loop."""
import json
import threading
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib,Pango
from i18n import _
from layout import fit_window
from ui import label,button,style,icon
from touchpad_demo import TouchpadDemo
from touchpad_request import TouchpadBackend


def touchpad_error(code):
    return {
        'identity':_('A identidade permanente deste controle ainda não está disponível.'),
        'custom-rule':_('A regra existente foi personalizada ou tem permissões inesperadas. Ela foi preservada.'),
        'unsafe-directory':_('A pasta de configuração do sistema precisa ser conferida por um administrador.'),
        'unsafe-lock':_('O arquivo de bloqueio precisa ser conferido por um administrador.'),
        'busy':_('Outra configuração de touchpad está em andamento. Aguarde e tente novamente.'),
        'authorization':_('Use a janela de autorização do sistema para aplicar esta escolha.'),
        'apply-failed-restored':_('Não foi possível aplicar. A regra anterior foi restaurada; tente novamente.'),
        'recovery-needed':_('A atualização do Linux foi interrompida. Verifique novamente e reaplique a escolha para recuperar o touchpad.'),
        'invalid-result':_('O sistema não confirmou o resultado. Verifique novamente antes de continuar.'),
        'not-saved':_('A regra salva não corresponde à escolha. Verifique os detalhes antes de tentar novamente.'),
    }.get(code,_('Não foi possível configurar o touchpad. Confira os detalhes e tente novamente.'))


class TouchpadDialog(Gtk.Dialog):
    def __init__(self,identity,name,parent=None,backend=None):
        super().__init__(title=_('Touchpad e cursor'),transient_for=parent,modal=True)
        style(self,'dualsense');fit_window(self,610,710)
        self.backend=backend or TouchpadBackend(identity)
        self.view=None;self.busy=False;self.closed=False;self.choice='system';self.result=None
        self.connect('destroy',lambda *args:setattr(self,'closed',True))
        self.connect('delete-event',lambda *args:self.busy)
        self.connect('response',self.response_received)
        self.add_button(_('Fechar'),Gtk.ResponseType.CLOSE)
        self.primary=self.add_button(_('Aplicar ao Linux'),Gtk.ResponseType.APPLY);style(self.primary,'primary')
        self.set_default_response(Gtk.ResponseType.CLOSE)
        for control in (self.primary,self.get_widget_for_response(Gtk.ResponseType.CLOSE)):
            self.get_action_area().set_child_non_homogeneous(control,True)
            # These short action names must keep a useful natural width. GTK's
            # button box can squeeze wrapping labels into one-letter columns.
            control.get_child().set_line_wrap(False)
        content=self.get_content_area();content.set_border_width(20)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False);content.pack_start(scroll,True,True,0)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);scroll.add(body)
        body.pack_start(label(name,'controller-name',wrap=True),False,False,0)
        body.pack_start(label(_('Arraste o ponto para visualizar sua escolha.'),'muted',wrap=True),False,False,0)
        captions=Gtk.Box(homogeneous=True)
        for title in (_('Touchpad'),_('Cursor do Linux')):captions.pack_start(label(title,'small'),True,True,0)
        body.pack_start(captions,False,False,0)
        self.preview=TouchpadDemo();body.pack_start(self.preview,False,False,0)
        body.pack_start(label(_('Demonstração · não altera o controle.'),'muted','small',wrap=True),False,False,0)
        self.radios={};group=None
        for choice,title in (('game',_('Sem cursor do Linux')),('system',_('Padrão do Linux'))):
            radio=Gtk.RadioButton.new_with_label_from_widget(group,title);group=radio
            radio.get_child().set_line_wrap(True);radio.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            radio.get_child().set_max_width_chars(38)
            radio.connect('toggled',self.selected,choice);body.pack_start(radio,False,False,0);self.radios[choice]=radio
        body.pack_start(label(_('O clique e os toques continuam disponíveis nos jogos compatíveis.'),'muted','small',wrap=True),False,False,0)
        body.pack_start(label(_('Este controle · todas as contas deste PC · permanece ao fechar o app.'),'muted','small',wrap=True),False,False,0)
        scope=Gtk.Expander(label=_('Ao aplicar esta escolha'))
        scope.add(label(_('Aplicar pede autorização do sistema e atualiza apenas o dispositivo de toque. O touchpad pode parar de responder por um instante; os botões do controle permanecem conectados.\n\nA escolha também permanece ao remover o app. Para desfazer, aplique Padrão do Linux.'),'muted','small',wrap=True))
        body.pack_start(scope,False,False,0)
        body.pack_start(label(_('No Linux agora'),'setting-title'),False,False,0)
        self.saved=label('',wrap=True);body.pack_start(self.saved,False,False,0)
        self.status=label('',wrap=True);body.pack_start(self.status,False,False,0)
        self.spinner=Gtk.Spinner();self.spinner.set_halign(Gtk.Align.START);body.pack_start(self.spinner,False,False,0)
        self.refresh_button=button(_('Verificar novamente'),lambda b:self.refresh(),'quiet');body.pack_start(self.refresh_button,False,False,0)
        help_box=Gtk.Expander(label=_('O touchpad ainda vira mouse ou não funciona no jogo?'))
        help_box.set_label_widget(label(_('O touchpad ainda vira mouse ou não funciona no jogo?'),wrap=True))
        help_box.add(label(_('A Steam pode transformar o touchpad em mouse por conta própria. Confira o layout do jogo e o da área de trabalho na Steam. Configurações do jogo não desativa Steam Input. Essa escolha não adiciona suporte a um jogo que não usa o touchpad.'),'muted',wrap=True));body.pack_start(help_box,False,False,0)
        self.steam_button=button(_('Conferir acesso da Steam Snap'),lambda b:self.open_steam(identity,name),'quiet');body.pack_start(self.steam_button,False,False,0)
        self.details=Gtk.Expander(label=_('Detalhes técnicos'));self.details_text=label('','small',wrap=True)
        self.details_text.set_selectable(True);self.details.add(self.details_text);body.pack_start(self.details,False,False,0)
        self.show_all();self.refresh()

    def open_steam(self,identity,name):
        from steam_access_ui import SteamAccessDialog
        dialog=SteamAccessDialog(identity,name,self)
        dialog.run();dialog.destroy()

    def selected(self,radio,choice):
        if radio.get_active():
            self.choice=choice;self.preview.set_choice(choice)

    def response_received(self,dialog,response):
        if response==Gtk.ResponseType.APPLY:
            self.stop_emission_by_name('response');self.apply()
        elif self.busy:self.stop_emission_by_name('response')

    def controls(self):
        if hasattr(self,'steam_button'):self.steam_button.set_sensitive(not self.busy)
        for item in self.radios.values():item.set_sensitive(not self.busy)
        self.refresh_button.set_sensitive(not self.busy)
        self.get_widget_for_response(Gtk.ResponseType.CLOSE).set_sensitive(not self.busy)
        self.primary.set_sensitive(not self.busy and self.view is not None and self.view['saved']!='custom')
        if self.busy:self.spinner.start()
        else:self.spinner.stop()

    def render_saved(self):
        if self.view is None:return
        if self.view['saved']=='custom':text=_('Há uma regra personalizada. O app não irá substituí-la.')
        elif not self.view['nodes']:text=_('O touchpad não está disponível no Linux agora. Você pode salvar a escolha sem mudar o modo do controle.')
        elif any(node['ignored'] is None for node in self.view['nodes']):text=_('Não foi possível conferir a regra atual nos dispositivos de toque.')
        elif self.view['saved']=='game':
            text=_('Regra de mouse bloqueado registrada no Linux.') if all(node['ignored'] for node in self.view['nodes']) else _('Regra salva; o Linux ainda precisa recarregar este touchpad.')
        elif any(node['ignored'] for node in self.view['nodes']):text=_('A regra deste app está removida, mas outra configuração do Linux ainda bloqueia o mouse.')
        else:text=_('O Linux permite usar este touchpad como mouse.')
        self.saved.set_text(text)

    def worker(self,operation,completed):
        if self.busy or self.closed:return
        self.busy=True;self.status.set_text(_('Aguarde…'));self.controls()
        def run():
            try:value=operation();error=None
            except Exception as exc:value=None;error=exc
            GLib.idle_add(completed,value,error)
        threading.Thread(target=run,daemon=True).start()

    def refresh(self):self.worker(self.backend.inspect,self.inspected)

    def inspected(self,value,error):
        if self.closed:return False
        self.busy=False
        if error:self.view=None;self.fail(str(error))
        else:
            self.view=value;self.choice='game' if value['saved']=='game' else 'system'
            self.radios[self.choice].set_active(True);self.preview.set_choice(self.choice);self.render_saved();self.status.set_text('')
        self.controls();return False

    def fail(self,detail):
        self.status.set_text(touchpad_error(detail));self.details_text.set_text(detail[:2000]);self.details.set_expanded(True)

    def apply(self):
        if not self.primary.get_sensitive():return
        choice=self.choice
        self.worker(lambda:self.backend.apply(choice),self.applied)

    def applied(self,value,error):
        if self.closed:return False
        self.busy=False
        if error:self.fail(str(error))
        else:
            result,answer,self.view=value;self.result=result;self.render_saved()
            if result.returncode==126:self.status.set_text(_('Autorização cancelada. A escolha anterior foi mantida.'))
            elif result.returncode:
                detail=(result.stderr or result.stdout or '')[:2000]
                try:code=json.loads(detail).get('error',detail)
                except (ValueError,AttributeError):code=detail
                self.fail(str(code))
            else:
                self.details_text.set_text('');self.details.set_expanded(False)
                self.status.set_text(_('Configuração salva. Será usada quando o touchpad voltar a aparecer no Linux.') if answer['pending'] else _('Configuração enviada ao Linux. Confira o cursor e o touchpad no jogo. Se o cursor ainda se mover, confira o mapeamento da Steam.'))
        self.controls();return False
