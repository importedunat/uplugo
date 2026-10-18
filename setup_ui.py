# SPDX-License-Identifier: GPL-3.0-only
"""GTK setup interface. Workers inspect/run the existing maintenance commands."""
import subprocess
import threading
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib,Pango
from app_info import VERSION
from i18n import _,LANGUAGES,language,set_language
from layout import AdaptiveBox,fit_window
from setup_state import SetupBackend
from ui import label,button,style,accessible,ASSETS


def dependency_help(name):
    return {
        'Python 3.10+':_('Executa o aplicativo.'),
        'pkexec':_('Mostra a autorização do sistema para configurar o acesso USB.'),
        'pkcheck':_('Confere a autorização desta sessão sem pedir senha.'),
        'udevadm':_('Atualiza as regras de acesso aos dispositivos USB.'),
        'libusb':_('Permite a comunicação com os controles por USB.'),
        'GTK 3 / PyGObject':_('Exibe a interface do aplicativo.'),
        'Imagens SVG':_('Exibe o logotipo, as ilustrações e o blueprint.'),
        'Bandeja AppIndicator':_('Mantém o ícone na bandeja. Sem ele, o app pode ser minimizado.'),
        'systemctl (supervisão opcional)':_('Pode reiniciar o app após uma falha. O app também abre sem ele.'),
    }.get(name,'')


class SetupDialog(Gtk.Dialog):
    def __init__(self,backend=None):
        super().__init__(title=_('Instalação e remoção'),modal=True)
        style(self,'dualsense');fit_window(self,660,650)
        try:self.set_icon_from_file(str(ASSETS/'dualsense-usb.svg'))
        except GLib.Error:pass  # Still show diagnostics when an asset is missing.
        self.backend=backend or SetupBackend()
        self.overview=None;self.running=False;self.checking=False;self.closed=False
        self.last_action=None;self.result=None;self.log='';self.selected='install';self.remove_access=False
        self.add_button(_('Fechar'),Gtk.ResponseType.CANCEL)
        self.primary=self.add_button(_('Instalar'),Gtk.ResponseType.OK);style(self.primary,'primary')
        for control in (self.primary,self.get_widget_for_response(Gtk.ResponseType.CANCEL)):
            self.get_action_area().set_child_non_homogeneous(control,True)
            control.get_child().set_line_wrap(True);control.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            control.get_child().set_max_width_chars(22)
        outer=self.get_content_area();outer.set_border_width(22)
        self.content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        outer.pack_start(self.content,True,True,0)
        self.connect('delete-event',lambda *a:self.running)
        self.connect('response',self.guard_response)
        self.connect('destroy',lambda *a:setattr(self,'closed',True))
        self.build()

    def build(self):
        outer=self.content
        for child in outer.get_children():child.destroy()
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_overlay_scrolling(False)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        scroll.add(body);outer.pack_start(scroll,True,True,0)
        top=AdaptiveBox(spacing=10)
        top.pack_start(label('Uplugo · '+VERSION,'controller-name',wrap=True),True,True,0)
        self.languages=Gtk.ComboBoxText()
        for code,name in LANGUAGES.items():self.languages.append(code,name)
        self.languages.set_active_id(language());accessible(self.languages,_('Idioma do assistente'))
        self.languages.set_tooltip_text(_('O idioma do app pode ser escolhido nas preferências.'))
        self.languages.connect('changed',self.change_language)
        top.pack_end(self.languages,False,False,0);body.pack_start(top,False,False,0)
        self.intro=label(_('Instale para sua conta, atualize ou remova o aplicativo pelo mesmo assistente.'),'muted',wrap=True)
        body.pack_start(self.intro,False,False,0)
        self.choice=Gtk.ComboBoxText()
        self.choice.append('install',_('Instalar ou atualizar'));self.choice.append('remove',_('Remover da minha conta'))
        self.choice.set_active_id(self.selected);accessible(self.choice,_('O que você quer fazer?'))
        self.choice.connect('changed',self.choose);body.pack_start(self.choice,False,False,0)
        self.summary=label('',wrap=True);body.pack_start(self.summary,False,False,0)
        body.pack_start(label(_('Seus nomes, preferências, fotos e histórico serão preservados.'),'muted',wrap=True),False,False,0)
        self.access=Gtk.CheckButton(label=_('Remover também o suporte USB e suas permissões'))
        self.access.get_child().set_line_wrap(True);self.access.get_child().set_max_width_chars(36)
        self.access.set_active(self.remove_access);self.access.set_no_show_all(True)
        self.access.connect('toggled',self.access_changed);body.pack_start(self.access,False,False,0)
        self.access_note=label(_('Essa opção pede autorização administrativa. Sem ela, o suporte USB fica instalado para uso futuro.'),'muted','small',wrap=True)
        self.access_note.set_no_show_all(True);body.pack_start(self.access_note,False,False,0)
        self.native_access_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.native_access_box.pack_start(label(_('Você pode retirar somente a autorização USB desta conta. O aplicativo, seus dados e o acesso de outras contas serão mantidos.'),'muted',wrap=True),False,False,0)
        self.revoke_button=button(_('Revogar acesso USB desta conta'),lambda b:self.revoke_access(),'destructive-action')
        self.native_access_box.pack_start(self.revoke_button,False,False,0)
        self.native_access_box.show_all();self.native_access_box.set_no_show_all(True);self.native_access_box.hide()
        body.pack_start(self.native_access_box,False,False,0)
        self.legacy_access_box=Gtk.Expander(label=_('Limpar suporte USB antigo (opcional)'))
        legacy=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        legacy.pack_start(label(_('O suporte USB da instalação antiga pode ser removido separadamente, com autorização administrativa. O suporte da versão do sistema e as suas cópias de segurança serão mantidos.'),'muted',wrap=True),False,False,0)
        self.legacy_remove=button(_('Remover suporte USB antigo'),lambda b:self.remove_legacy_access(),'destructive-action')
        legacy.pack_start(self.legacy_remove,False,False,0);self.legacy_access_box.add(legacy)
        self.legacy_access_box.show_all();self.legacy_access_box.set_no_show_all(True);self.legacy_access_box.hide()
        body.pack_start(self.legacy_access_box,False,False,0)
        self.status=label('',wrap=True);body.pack_start(self.status,False,False,0)
        self.spinner=Gtk.Spinner();self.spinner.set_halign(Gtk.Align.START);body.pack_start(self.spinner,False,False,0)
        actions=AdaptiveBox(spacing=10)
        self.refresh_button=button(_('Verificar novamente'),lambda b:self.refresh(),'quiet')
        actions.pack_start(self.refresh_button,False,False,0)
        self.open_button=button(_('Abrir app'),lambda b:self.open_app(),'quiet');self.open_button.set_no_show_all(True)
        actions.pack_start(self.open_button,False,False,0);body.pack_start(actions,False,False,0)
        self.dependencies=Gtk.Expander(label=_('Requisitos do sistema'))
        self.dependency_text=label('','small',wrap=True);self.dependency_text.set_selectable(True)
        self.dependencies.add(self.dependency_text);body.pack_start(self.dependencies,False,False,0)
        self.details=Gtk.Expander(label=_('Arquivos e detalhes técnicos'))
        self.details_text=label('','small',wrap=True);self.details_text.set_selectable(True)
        self.details.add(self.details_text);body.pack_start(self.details,False,False,0)
        self.set_title(_('Instalação e remoção'))
        self.get_widget_for_response(Gtk.ResponseType.CANCEL).set_label(_('Fechar'))
        body.show_all();scroll.show_all();self.render()

    def guard_response(self,dialog,response):
        if self.running or (self.checking and response==Gtk.ResponseType.OK):self.stop_emission_by_name('response')

    @property
    def finish_requested(self):
        return bool(self.result is not None and self.result.returncode==0 and self.last_action in ('remove','open'))

    def change_language(self,choice):
        if not self.running and not self.checking and choice.get_active_id()!=language():
            set_language(choice.get_active_id());self.build()

    def choose(self,choice):
        self.selected=choice.get_active_id();self.result=None;self.log='';self.render()

    def access_changed(self,check):
        self.remove_access=check.get_active();self.result=None;self.render()

    def render(self):
        view=self.overview;busy=self.running or self.checking
        removed_source=bool(self.finish_requested and view and view.source_error)
        for control in (self.choice,self.access,self.languages,self.refresh_button):control.set_sensitive(not busy and not removed_source)
        self.get_widget_for_response(Gtk.ResponseType.CANCEL).set_sensitive(not self.running)
        self.access.set_visible(self.selected=='remove');self.access_note.set_visible(self.selected=='remove')
        self.open_button.set_visible(bool(view and view.launchable and self.last_action!='remove'))
        self.open_button.set_sensitive(not busy and not (view and view.root))
        if busy:self.spinner.start()
        else:self.spinner.stop()
        self.primary.set_sensitive(False)
        self.native_access_box.set_visible(bool(view and view.system_package))
        self.legacy_access_box.set_visible(bool(view and view.system_package and view.legacy_access and not view.conflicts))
        if view is None:
            self.summary.set_text(_('Verificando os arquivos e o sistema…'));return
        self.primary.set_no_show_all(bool(view.system_package))
        self.primary.set_visible(not view.system_package)
        self.choice.set_visible(not view.system_package)
        if view.system_package:
            self.render_system(view,busy);return
        installed=_('Versão instalada: {0}').format(view.version) if view.version else (_('Instalação anterior encontrada.') if view.installed else _('O app ainda não está instalado nesta conta.'))
        if self.selected=='remove':
            self.summary.set_text(_('{0} arquivos do programa serão removidos. {1} arquivos alterados serão mantidos.').format(len(view.remove),len(view.preserve)))
            self.primary.set_label(_('Remover da minha conta'))
        else:
            self.summary.set_text(installed+'\n'+_('O app será copiado para sua conta e aparecerá no menu de aplicativos. O acesso USB é configurado depois, dentro do app.'))
            self.primary.set_label(_('Atualizar instalação') if view.installed else _('Instalar'))
        if self.result is not None and self.result.returncode==0:
            if self.last_action=='remove':self.summary.set_text(_('Arquivos registrados removidos. {0} arquivos alterados foram mantidos.').format(len(view.preserve)))
            elif self.last_action in ('install','open'):self.summary.set_text(installed+'\n'+_('O aplicativo está disponível no menu da sua conta.'))
        action='recover' if view.pending else self.selected
        if view.pending:self.primary.set_label(_('Recuperar instalação'))
        self.primary.set_sensitive(not busy and view.allowed(action,self.remove_access))
        opening=bool(self.result is not None and ((self.last_action=='install' and not self.result.returncode) or self.last_action=='open'))
        if opening:
            self.primary.set_label(_('Abrir app'));self.primary.set_sensitive(not busy and view.launchable and not view.root)
            self.open_button.hide()
        if self.finish_requested:
            self.primary.set_label(_('Concluir'));self.primary.set_sensitive(not busy)
        destructive=self.selected=='remove' and not view.pending and not self.finish_requested
        context=self.primary.get_style_context()
        context.remove_class('primary' if destructive else 'destructive-action')
        context.add_class('destructive-action' if destructive else 'primary')
        dependencies=[]
        for item in view.dependencies:
            state=_('Disponível') if item['ok'] else (_('Necessário') if item['required'] else _('Opcional'))
            dependencies.append(state+' · '+_(item['name'])+'\n'+dependency_help(item['name']))
        self.dependency_text.set_text('\n\n'.join(dependencies))
        detail=[_('Destino: {0}').format(view.destination)]
        if self.selected=='remove':
            detail.extend(view.remove)
            detail.extend(_('Preservado: {0}').format(path) for path in view.preserve)
        detail.extend(text for text in (view.source_error,view.removal_error,view.install_error,self.log) if text)
        self.details_text.set_text('\n\n'.join(detail)[-24000:])
        if busy:
            self.status.set_text(_('Aguarde a conclusão. Os arquivos estão sendo processados.') if self.running else _('Verificando os arquivos e o sistema…'))
        elif self.result is not None:
            if self.result.returncode:
                self.status.set_text(_('A operação não foi concluída. Confira os detalhes, verifique novamente e tente outra vez.'))
                self.details.set_expanded(True)
            else:
                messages={'install':_('Instalação concluída. Você pode abrir o app pelo botão abaixo ou pelo menu.'),
                          'remove':_('Remoção concluída. Seus dados e os arquivos alterados foram preservados.'),
                          'recover':_('Recuperação concluída. Confira o estado da instalação antes de continuar.'),
                          'open':_('A abertura do app foi solicitada.')}
                self.status.set_text(messages[self.last_action])
        elif view.root:self.status.set_text(_('Abra o assistente como seu usuário, sem sudo.'))
        elif view.running:self.status.set_text(_('Encerre o app em Preferências → Encerrar e liberar controles e depois clique em Verificar novamente. Fechar a janela mantém o app na bandeja.'))
        elif view.source_error:self.status.set_text(_('Faltam arquivos neste pacote. Extraia novamente o download completo e abra o assistente dessa pasta.'))
        elif view.pending:self.status.set_text(_('Uma atualização foi interrompida. Recupere os arquivos antes de instalar ou remover.'))
        elif self.selected=='remove' and view.removal_error:self.status.set_text(_('Não foi possível preparar a remoção. Confira os detalhes; uma instalação antiga pode precisar ser atualizada primeiro.'))
        elif self.selected=='install' and view.install_error:self.status.set_text(view.install_error)
        elif self.selected=='install' and not view.allowed('install'):
            self.status.set_text(_('Instale os requisitos marcados como necessários seguindo o README da pasta do download. Depois clique em Verificar novamente.'))
            self.dependencies.set_expanded(True)
        elif self.selected=='remove' and not view.remove and not self.remove_access:self.status.set_text(_('Não há arquivos registrados para remover.'))
        else:self.status.set_text(_('Confira a escolha e use o botão abaixo para continuar.'))

    def render_system(self,view,busy):
        self.access.hide();self.access_note.hide()
        revoked=bool(self.result is not None and not self.result.returncode and self.last_action=='revoke')
        self.revoke_button.set_sensitive(not busy and not revoked and view.allowed('revoke'))
        self.legacy_remove.set_sensitive(not busy and view.allowed('remove_legacy_access'))
        self.intro.set_text(_('Instalado pelo sistema'))
        self.summary.set_text(_('Versão instalada: {0}').format(view.version)+'\n'+
            _('Para atualizar ou remover, use o gerenciador de pacotes da sua distribuição. O app abre os arquivos do sistema e mantém seus dados na sua conta.'))
        if view.migration_action:
            self.primary.set_no_show_all(False);self.primary.show()
            self.primary.set_label({'migrate':_('Migrar para a versão do sistema'),
                'resume_migration':_('Concluir migração'),
                'recover_legacy':_('Recuperar instalação antiga')}[view.migration_action])
            self.primary.set_sensitive(not busy and view.allowed(view.migration_action))
            self.summary.set_text(_('Há uma instalação antiga nesta conta. Vamos guardar a pasta inteira, os atalhos e o serviço antigo, incluindo arquivos modificados. Seus nomes, fotos e histórico continuam nos mesmos lugares.'))
            self.native_access_box.hide()
            if view.migration_data:self.summary.set_text(self.summary.get_text()+'\n'+_('Dados que ainda estão na pasta antiga serão copiados para sua conta. Preferências atuais não serão substituídas.'))
        self.dependency_text.set_text('\n\n'.join(
            (_('Disponível') if item['ok'] else (_('Necessário') if item['required'] else _('Opcional')))+
            ' · '+_(item['name'])+'\n'+dependency_help(item['name']) for item in view.dependencies))
        self.details_text.set_text('\n\n'.join([_('Destino: {0}').format(view.destination),
            view.system_package,*view.conflicts,view.source_error,view.migration_error,
            *view.migration_backups,*view.migration_data,self.log])[-24000:])
        if busy:self.status.set_text(_('Verificando os arquivos e o sistema…'))
        elif self.result is not None:
            if revoked:self.status.set_text(_('Acesso USB revogado para esta conta. Para usar os controles novamente, abra o app e configure o acesso.'))
            elif self.last_action=='remove_legacy_access' and self.result.returncode==126:
                self.status.set_text(_('Limpeza cancelada. O suporte USB antigo foi mantido.'))
            elif self.last_action=='remove_legacy_access' and not self.result.returncode:
                self.status.set_text(_('Suporte USB antigo removido. O suporte da versão do sistema foi mantido.'))
            elif not self.result.returncode and self.last_action in ('migrate','resume_migration'):
                self.status.set_text(_('Migração concluída. Abra o app e configure o acesso USB da versão do sistema. As cópias antigas estão nos detalhes.'))
                self.details.set_expanded(True)
            elif not self.result.returncode and self.last_action=='recover_legacy':
                self.status.set_text(_('A instalação antiga foi recuperada. Confira os arquivos antes de iniciar a migração.'))
            elif self.result.returncode==126:self.status.set_text(_('Autorização cancelada. A concessão de acesso foi mantida.'))
            else:self.status.set_text(_('A abertura do app foi solicitada.') if not self.result.returncode else
                    _('A operação não foi concluída. Confira os detalhes, verifique novamente e tente outra vez.'))
        elif view.root:self.status.set_text(_('Abra o assistente como seu usuário, sem sudo.'))
        elif view.running:self.status.set_text(_('Encerre o app em Preferências → Encerrar e liberar controles e depois clique em Verificar novamente. Fechar a janela mantém o app na bandeja.'))
        elif view.source_error:self.status.set_text(_('Os arquivos da instalação do sistema estão incompletos ou fora do local esperado. Reinstale o pacote pelo gerenciador da distribuição.'))
        elif view.migration_error:
            self.status.set_text(_('Não foi possível preparar a migração. Os arquivos foram preservados; confira os detalhes.'))
            self.details.set_expanded(True)
        elif view.migration_action=='recover_legacy':
            self.status.set_text(_('Há uma atualização antiga interrompida. Primeiro recupere essa instalação; depois confira a prévia da migração.'))
        elif view.migration_action=='resume_migration':
            self.status.set_text(_('A migração foi interrompida. As cópias já guardadas serão mantidas e o processo continuará de onde parou.'))
            self.details.set_expanded(True)
        elif view.migration_action=='migrate':
            self.status.set_text(_('Confira os arquivos nos detalhes e clique em Migrar para a versão do sistema. Esta etapa não pede senha. O suporte USB antigo será mantido.'))
            self.details.set_expanded(True)
        elif view.conflicts:
            self.status.set_text(_('Foi encontrada uma instalação por usuário. Use o assistente dessa instalação para recuperar uma atualização pendente e remover os arquivos antigos. Depois, verifique novamente. Nomes, fotos e histórico devem ser mantidos.'))
            self.details.set_expanded(True)
        else:self.status.set_text(_('O programa é gerenciado pelo sistema. Nenhuma cópia adicional será criada nesta conta.'))

    def refresh(self):
        if self.running or self.checking or self.closed:return
        self.checking=True;self.result=None;self.render()
        self.worker(self.backend.inspect,self.inspected)

    def worker(self,operation,completed):
        def run():
            try:value=operation();error=None
            except Exception as exc:value=None;error=exc
            GLib.idle_add(completed,value,error)
        threading.Thread(target=run,daemon=True).start()

    def inspected(self,value,error):
        if self.closed:return False
        self.checking=False
        if error:
            self.overview=None
            self.log=str(error);self.result=subprocess.CompletedProcess([],1,'',self.log)
            self.last_action='check'
        else:self.overview=value
        self.render()
        if error:
            self.status.set_text(_('Não foi possível verificar a instalação. Confira os detalhes e tente novamente.'))
            self.details_text.set_text(self.log);self.details.set_expanded(True)
        return False

    def start(self):
        if self.running or self.checking or not self.overview:return
        if self.finish_requested:return
        if self.overview.system_package:
            action=self.overview.migration_action
            if self.overview.allowed(action):self.perform(action)
            return
        if self.result is not None and ((self.last_action=='install' and not self.result.returncode) or self.last_action=='open'):
            self.open_app();return
        action='recover' if self.overview.pending else self.selected
        if not self.overview.allowed(action,self.remove_access):return
        self.perform(action,self.remove_access)

    def revoke_access(self):
        if self.running or self.checking or not self.overview or not self.overview.allowed('revoke'):return
        self.perform('revoke')

    def remove_legacy_access(self):
        if self.running or self.checking or not self.overview or not self.overview.allowed('remove_legacy_access'):return
        self.perform('remove_legacy_access')

    def perform(self,action,access=False):
        migration_token=self.overview.migration_token if self.overview else None
        self.last_action=action;self.running=True;self.result=None;self.log='';self.render()
        def operation():
            if action in ('migrate','resume_migration','recover_legacy'):
                try:result=self.backend.execute(action,access,migration_token=migration_token)
                except Exception as exc:result=subprocess.CompletedProcess([],1,'',str(exc))
            else:result=self.backend.execute(action,access)
            return result,self.backend.inspect()
        self.worker(operation,self.completed)

    def completed(self,value,error):
        if self.closed:return False
        self.running=False
        if error:self.result=subprocess.CompletedProcess([],1,'',str(error))
        else:self.result,self.overview=value
        self.log=((self.result.stdout or '')+'\n'+(self.result.stderr or '')).strip()[-16000:]
        self.render();return False

    def open_app(self):
        if self.running or self.checking or not self.overview or not self.overview.launchable or self.overview.root:return
        self.running=True;self.last_action='open';self.render()
        self.worker(lambda:(self.backend.open_app(),self.backend.inspect()),self.completed)
