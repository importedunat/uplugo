# SPDX-License-Identifier: GPL-3.0-only
"""Explicit Steam Snap permission, separate from pointer and game mappings."""
import json
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Pango
from i18n import _
from layout import fit_window
from ui import label,button,style
from touchpad_ui import TouchpadDialog,touchpad_error
from steam_access_request import SteamAccessBackend


def steam_access_error(code):
    return {
        'no-snap':_('O Snap não está instalado. Esta opção não se aplica à sua instalação da Steam.'),
        'snap-connection':_('A Steam Snap não está instalada ou sua conexão steam-support não está ativa. Confira as permissões da Steam no gerenciador de aplicativos.'),
        'snap-helper':_('O componente de acesso a dispositivos do Snap está ausente ou precisa de reparo.'),
        'snap-unavailable':_('Não foi possível consultar o Snap agora. Tente verificar novamente.'),
        'busy':_('Outra configuração de acesso está em andamento. Aguarde e tente novamente.'),
        'recovery-needed':_('A atualização da permissão foi interrompida. Verifique novamente e reaplique. Feche e reabra a Steam antes de testar.'),
    }.get(code,touchpad_error(code))


class SteamAccessDialog(TouchpadDialog):
    def __init__(self,identity,name,parent=None,backend=None):
        Gtk.Dialog.__init__(self,title=_('Acesso da Steam Snap'),transient_for=parent,modal=True)
        style(self,'dualsense');fit_window(self,610,680)
        self.backend=backend or SteamAccessBackend(identity)
        self.view=None;self.busy=False;self.closed=False;self.choice='system';self.result=None;self.retry=False
        self.connect('destroy',lambda *args:setattr(self,'closed',True))
        self.connect('delete-event',lambda *args:self.busy);self.connect('response',self.response_received)
        self.add_button(_('Fechar'),Gtk.ResponseType.CLOSE)
        self.primary=self.add_button(_('Aplicar'),Gtk.ResponseType.APPLY);style(self.primary,'primary')
        self.set_default_response(Gtk.ResponseType.CLOSE)
        for control in (self.primary,self.get_widget_for_response(Gtk.ResponseType.CLOSE)):
            self.get_action_area().set_child_non_homogeneous(control,True);control.get_child().set_line_wrap(False)
        content=self.get_content_area();content.set_border_width(20)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False);content.pack_start(scroll,True,True,0)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);scroll.add(body)
        body.pack_start(label(name,'controller-name',wrap=True),False,False,0)
        body.pack_start(label(_('A Steam instalada por Snap pode reconhecer os botões básicos e não receber o clique do touchpad. Esta opção permite acesso aos dados completos deste controle por USB.'),wrap=True),False,False,0)
        self.environment=label('','muted',wrap=True);body.pack_start(self.environment,False,False,0)
        self.radios={};group=None
        for choice,title in (('allow',_('Permitir acesso completo a este controle na Steam Snap')),('system',_('Remover a permissão adicionada por este app'))):
            radio=Gtk.RadioButton.new_with_label_from_widget(group,title);group=radio
            radio.get_child().set_line_wrap(True);radio.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            radio.get_child().set_max_width_chars(38)
            radio.connect('toggled',self.selected,choice);body.pack_start(radio,False,False,0);self.radios[choice]=radio
        body.pack_start(label(_('A autorização vale para este controle em todas as contas do computador. Não altera seu modo, o bloqueio do cursor nem o layout dos jogos. Outras permissões do Linux permanecem.'),'muted',wrap=True),False,False,0)
        body.pack_start(label(_('Após aplicar ou remover, salve seu jogo e feche e reabra a Steam. O app não fará isso automaticamente. A configuração permanece ao fechar ou remover este app.'),'muted',wrap=True),False,False,0)
        self.saved=label('',wrap=True);body.pack_start(self.saved,False,False,0)
        self.status=label('',wrap=True);body.pack_start(self.status,False,False,0)
        self.spinner=Gtk.Spinner();self.spinner.set_halign(Gtk.Align.START);body.pack_start(self.spinner,False,False,0)
        self.refresh_button=button(_('Verificar novamente'),lambda b:self.refresh(),'quiet');body.pack_start(self.refresh_button,False,False,0)
        note=Gtk.Expander(label=_('O que esta opção resolve?'))
        note.add(label(_('Ela corrige a permissão de leitura da Steam Snap. O jogo ainda precisa ter uma ação para o touchpad, e a Steam precisa usar o layout adequado. O estado abaixo confirma a configuração do Linux, não o funcionamento dentro do jogo.'),'muted',wrap=True));body.pack_start(note,False,False,0)
        self.details=Gtk.Expander(label=_('Detalhes técnicos'));self.details_text=label('','small',wrap=True)
        self.details_text.set_selectable(True);self.details.add(self.details_text);body.pack_start(self.details,False,False,0)
        self.show_all();self.refresh()

    def selected(self,radio,choice):
        if radio.get_active():
            self.choice=choice
            if hasattr(self,'refresh_button'):self.controls()

    def controls(self):
        super().controls()
        if self.view is not None and self.choice=='allow' and not self.view['environment']['available']:self.primary.set_sensitive(False)
        if self.view is not None and self.choice=='system' and self.view['saved']=='system' and not self.retry:self.primary.set_sensitive(False)

    def inspected(self,value,error):
        if self.closed:return False
        self.busy=False
        if error:self.view=None;self.fail(str(error))
        else:
            self.view=value;self.choice='allow' if value['saved']=='allow' else 'system'
            self.radios[self.choice].set_active(True);self.render_saved();self.status.set_text('')
        self.controls();return False

    def render_saved(self):
        if self.view is None:return
        environment=self.view['environment']
        self.environment.set_text(_('Steam Snap encontrada com a conexão de suporte ativa.') if environment['available'] else steam_access_error(environment['reason']))
        saved=self.view['saved'];nodes=self.view['nodes']
        if saved=='custom':text=_('Há uma regra personalizada. O app não irá substituí-la.')
        elif not nodes:text=_('O controle físico não está disponível para a Steam agora. A regra será usada quando ele aparecer em Configurações do jogo. O modo escolhido não muda.')
        elif saved=='allow':
            text=_('Permissão salva e reconhecida pelo Linux. Reabra a Steam e confira o clique no jogo.') if all(n['tagged'] for n in nodes) else _('Permissão salva; a marca de acesso ainda não foi confirmada nos dispositivos. Verifique novamente ou reaplique.')
        elif any(n['tagged'] for n in nodes):text=_('Este app não tem uma permissão salva, mas outra configuração já registra acesso para a Steam. Ela será preservada.')
        else:text=_('Nenhuma permissão adicional deste app está salva para a Steam Snap.')
        self.saved.set_text(text)

    def fail(self,detail):
        self.retry=detail in ('recovery-needed','apply-failed-restored','invalid-result','not-saved')
        self.status.set_text(steam_access_error(detail));self.details_text.set_text(detail[:2000]);self.details.set_expanded(True)

    def applied(self,value,error):
        if self.closed:return False
        self.busy=False
        if error:self.fail(str(error))
        else:
            result,answer,self.view=value;self.result=result;self.render_saved()
            if result.returncode==126:self.status.set_text(_('Autorização cancelada. A escolha anterior foi mantida.'))
            elif result.returncode:
                detail=(result.stderr or result.stdout or '')[:2000]
                try:detail=json.loads(detail).get('error',detail)
                except (ValueError,AttributeError):pass
                self.fail(str(detail))
            else:
                self.retry=False
                self.details_text.set_text('');self.details.set_expanded(False)
                self.status.set_text(_('Configuração salva. Salve seu jogo e feche e reabra a Steam para testar. Não é necessário tirar o cabo.'))
        self.controls();return False
