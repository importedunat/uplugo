#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
try:
    gi.require_version('GLibUnix', '2.0')
    from gi.repository import GLibUnix
    add_unix_signal = getattr(GLibUnix, 'signal_add', None)
except (ImportError, ValueError):
    add_unix_signal = None
if add_unix_signal is None:
    add_unix_signal = GLib.unix_signal_add
from pathlib import Path
import subprocess
import threading
import json
import time
import signal
import os
import socket
import dualsense as core
from tray import Tray
from charge_watch import ChargeWatch
from charge_view import BatteryPanel, attach_battery_panel
from access_guard import AccessGuard
from game_profiles import GameDetector, running_game, parse_profiles, effective_mode, installed_games
from presentation import ControllerState, confirmed_mode, MODES, AccessSetup
from ui import icon, Dashboard, ContentClamp, EffectsEditor, themed_dialog, label, button, style
from ui import AppearanceEditor
from layout import fit_window, AdaptiveBox
import artwork
from app_info import VERSION, REPOSITORY
from deployment import inspect_deployment
from i18n import _, set_language, language
from input_view import InputPanel, attach_input_panel
from input_state import INPUT_MONITOR_VERSION
from photo_download import PhotoDownloads, status_text

BASE = Path(__file__).resolve().parent
DEPLOYMENT = inspect_deployment(BASE)
HELPER = DEPLOYMENT.helper

class Window(Gtk.Window):
    def __init__(self, application=None):
        core.migrate_legacy()
        super().__init__(title='Uplugo', application=application)
        style(self, 'dualsense')
        from layout import fit_window
        fit_window(self,1000,700)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(str(BASE/'assets/dualsense-usb.svg'))
        self.connect('destroy', lambda w:self.quit_app())
        self.busy = False
        if DEPLOYMENT.system:
            from native_status import NativeAuthorization
            self.native_authorization=NativeAuthorization()
        self.access_setup = AccessSetup()
        from access_request import HelperRevision
        self.support_revision=HelperRevision(HELPER,native=DEPLOYMENT.system)
        self.closed = False
        self.terminated = False
        self.photo_gallery = None
        self.photo_controls = None
        self.photos = PhotoDownloads(lambda key,state:GLib.idle_add(self.photos_changed,key,state))
        self.streams, self.stream_kinds, self.stream_requests = {}, {}, {}
        self.stream_status, self.stream_errors = {}, {}
        self.stream_connections, self.stream_stopping = {}, {}
        self.models, self.transitions = {}, {}
        self.input_watch = None
        self.input_sample = None
        self.game_detector = GameDetector()
        self.access_guard = AccessGuard()
        self.native_game = None
        self.next_game_scan = 0
        self.games = installed_games()
        self.live, self.measured = {}, {}
        self.charge_watch = ChargeWatch(core.STATE_DIR/'charge-history.json')
        self.tray = Tray(self.reveal, self.quit_app)
        self.connect('delete-event', self.hide_to_tray)
        add_unix_signal(GLib.PRIORITY_DEFAULT,signal.SIGUSR1,self.reveal)
        add_unix_signal(GLib.PRIORITY_DEFAULT,signal.SIGUSR2,self.request_close)
        add_unix_signal(GLib.PRIORITY_DEFAULT,signal.SIGTERM,self.quit_app)
        from theme import install_theme
        install_theme()
        self.build_dashboard()
        self.refresh()
        GLib.timeout_add_seconds(1, self.refresh)
        from autostart import consume_hidden_start
        hidden=consume_hidden_start(core.STATE_DIR)
        if hidden and self.tray.available():
            # Opened at login: stay in the tray until the user opens the window.
            self.get_child().show_all()
            self.dashboard.update(list(self.models.values()), self.helper_ready())
            print('Iniciado na bandeja ao entrar na sessão.', flush=True)
        else:
            self.show_all()
            self.dashboard.update(list(self.models.values()), self.helper_ready())
            self.present()
            if hidden:self.iconify()
        GLib.idle_add(self.start_photo_downloads)
        notify=os.environ.get('NOTIFY_SOCKET')
        if notify:
            with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as connection:
                connection.connect('\0'+notify[1:] if notify.startswith('@') else notify)
                connection.sendall(b'READY=1')

    def build_dashboard(self):
        self.dashboard = Dashboard(self)
        self.add(ContentClamp(self.dashboard))
        self.cards, self.notice = self.dashboard.cards, self.dashboard.notice
        self.unlock, self.protect = self.dashboard.unlock, self.dashboard.protect
        ui_settings = core.settings()['ui']
        self.dashboard.above.set_active(ui_settings.get('keep_above', False))
        self.set_keep_above(self.dashboard.above.get_active())
        self.protect.set_active(ui_settings.get('custom_effects', True))
        protection=core.settings()['protection']
        self.dashboard.guard.set_active(protection.get('enabled',False))
        self.dashboard.allow_play.set_active(protection.get('allow_manual_play',True))
        self.setup_autostart()
        self.dashboard.above.connect('toggled', self.ui_changed)
        self.protect.connect('toggled', self.ui_changed)
        self.dashboard.guard.connect('toggled',self.ui_changed)
        self.dashboard.allow_play.connect('toggled',self.ui_changed)

    def setup_autostart(self):
        import autostart
        from maintenance import Locations
        choice=self.dashboard.autostart
        self.autostart_launcher=BASE/'launch.py'
        installed=DEPLOYMENT.system or BASE==Locations.current().app
        try:choice.set_active(autostart.enabled())
        except OSError:choice.set_active(False)
        if not installed:
            choice.set_sensitive(False)
            choice.set_tooltip_text(_('Disponível no app instalado. Esta cópia foi aberta direto da pasta do projeto.'))
        self.autostart_handler=choice.connect('toggled',self.autostart_changed)

    def autostart_changed(self, choice):
        import autostart
        wanted=choice.get_active()
        try:
            autostart.set_enabled(wanted,self.autostart_launcher)
            self.notice.set_text(_('O app vai abrir na bandeja quando você entrar no computador.') if wanted
                                 else _('O app não vai mais abrir sozinho ao ligar o computador.'))
        except (OSError,ValueError) as exc:
            choice.handler_block(self.autostart_handler)
            try:choice.set_active(autostart.enabled())
            except OSError:choice.set_active(not wanted)
            choice.handler_unblock(self.autostart_handler)
            self.notice.set_text(_('Não foi possível mudar a abertura automática: ')+str(exc))

    def change_language(self, code):
        if not code or code == language():return
        set_language(code)
        data=core.settings();data['ui']['language']=language()
        core.write_json(core.SETTINGS,data)
        # Rebuild text widgets only; streams, modes and timer subscriptions survive.
        selected=self.dashboard.selected
        self.get_child().destroy()
        self.build_dashboard()
        self.tray.retranslate()
        self.show_all()
        self.dashboard.update(list(self.models.values()),self.helper_ready())
        if selected in self.dashboard.items:self.dashboard.select_controller(selected)
        self.photos_changed(None,self.photos.state)

    def helper_ready(self):
        try:
            text=HELPER.read_text()
            if "BROKER_VERSION = 'uhid-1'" not in text:return False
            if DEPLOYMENT.system:
                return 'NATIVE_ACCESS_VERSION = 1' in text and self.native_authorization.ready()
            return True
        except OSError: return False

    def review_access(self):
        self.access_setup.reviewing=True
        self.dashboard.update(list(self.models.values()),self.helper_ready())

    def dismiss_access(self):
        if self.busy:return
        self.access_setup=AccessSetup()
        self.dashboard.update(list(self.models.values()),self.helper_ready())

    def open_demo(self):
        subprocess.Popen(['/usr/bin/python3',str(BASE/'development.py')],close_fds=True)

    def open_setup(self):
        def failed():
            if not self.closed:
                self.notice.set_text(_('Não foi possível abrir o assistente. Execute python3 setup.py na pasta do download. Detalhes em setup-assistant.log na pasta de estado do app.'))
            return False
        def worker():
            try:
                from setup_state import launch_assistant
                if launch_assistant(BASE).wait():GLib.idle_add(failed)
            except Exception:GLib.idle_add(failed)
        threading.Thread(target=worker,daemon=True).start()

    def ui_changed(self, _):
        data=core.settings()
        data['ui'].update(keep_above=self.dashboard.above.get_active(), custom_effects=self.protect.get_active())
        data['protection'].update(enabled=self.dashboard.guard.get_active(),allow_manual_play=self.dashboard.allow_play.get_active())
        if not self.dashboard.allow_play.get_active():data['protection']['play_exceptions']=[]
        core.write_json(core.SETTINGS,data)
        self.set_keep_above(self.dashboard.above.get_active())
        self.refresh()

    def reveal(self):
        self.show_all()
        self.present()
        print('Janela exibida; sessões USB preservadas.', flush=True)
        return True

    def request_close(self):
        self.close()
        return True

    def hide_to_tray(self, *args):
        if not self.tray.available():
            self.notice.set_text(_('Sua área de trabalho não tem bandeja disponível. O app continua aberto; minimize a janela ou encerre em Preferências.'))
            self.iconify()
            return True
        self.hide()
        print('Janela ocultada na bandeja; sessões USB preservadas.', flush=True)
        return True

    def stop_resources(self):
        if self.terminated:return
        self.terminated = True
        self.stop_photos()
        self.tray.close()
        self.stop_all()

    def quit_app(self):
        self.stop_resources()
        application=self.get_application()
        if application:application.quit()
        elif Gtk.main_level():Gtk.main_quit()
        return False

    def stop_photos(self):
        self.closed = True
        self.photos.stop()

    def start_photo_downloads(self):
        if self.closed or not core.settings()['ui'].get('download_photos',False):return False
        self.photos.start(core.settings()['appearance'].values())
        return False

    def photos_changed(self,key,state):
        if self.closed:return False
        self.dashboard.photo_status.set_text(_('Fotos {0}/{1}').format(state['done'], state['total']) if state['active'] else (_('Fotos pendentes') if state['failed'] else ''))
        self.dashboard.photo_status.set_tooltip_text(status_text(state)+_('\nPreferências → Fotos dos controles.'))
        if key and self.photo_gallery:self.photo_gallery.refresh_picture(key)
        if self.photo_controls:
            progress,status,retry=self.photo_controls
            progress.set_fraction(state['done']/max(1,state['total']))
            status.set_text(status_text(state))
            enabled=core.settings()['ui'].get('download_photos',False)
            retry.set_sensitive(enabled and not state['active'])
            retry.set_label(_('Verificar fotos faltantes') if not state['failed'] else _('Tentar novamente'))
        if not state['active'] and state['stopped'] and core.settings()['ui'].get('download_photos',False):
            GLib.timeout_add(250,self.start_photo_downloads)
        return False

    def photos_dialog(self,parent=None,model='neutral'):
        dialog=themed_dialog(_('Fotos dos controles'),parent or self,560)
        fit_window(dialog,560,620)
        dialog.add_buttons(_('Fechar'),Gtk.ResponseType.CLOSE)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        dialog.get_content_area().pack_start(scroll,True,True,0)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=15);scroll.add(content)
        content.pack_start(label(_('Fotos do seu controle'),'controller-name'),False,False,0)
        content.pack_start(label(_('Esta biblioteca é compartilhada por todos os controles do mesmo modelo. As alterações de fotos são salvas aqui, ao adicionar.'),'muted','small',wrap=True),False,False,0)
        if model in artwork.BY_ID:
            content.pack_start(label(_('Foto para {0}').format(_(artwork.model(model)['name'])),'mode-title',wrap=True),False,False,0)
            photo_status=label(_('Use uma foto de frente, com fundo branco ou transparente.'),'muted','small',wrap=True)
            add=button(_('Adicionar ou substituir foto…'),lambda b:self.import_picture(dialog,model,photo_status))
            content.pack_start(add,False,False,0);content.pack_start(photo_status,False,False,0)
        enabled=Gtk.CheckButton(label=_('Baixar fotos automaticamente'))
        enabled.get_child().set_line_wrap(True);enabled.get_child().set_max_width_chars(32)
        enabled.set_active(core.settings()['ui'].get('download_photos',False))
        content.pack_start(enabled,False,False,0)
        content.pack_start(label(_('Desligado por padrão. Ao ligar, o app baixa as fotos oficiais do catálogo dos servidores da Sony, para uso só no seu computador. Depois usa as cópias salvas, inclusive sem internet. As fotos não fazem parte do projeto.'),'muted',wrap=True),False,False,0)
        progress=Gtk.ProgressBar();content.pack_start(progress,False,False,0)
        status=label('',wrap=True);content.pack_start(status,False,False,0)
        retry=button(_('Verificar fotos faltantes'),lambda b:self.start_photo_downloads(),'primary')
        content.pack_start(retry,False,False,0)
        self.photo_controls=(progress,status,retry)
        def toggle(check):
            data=core.settings();data['ui']['download_photos']=check.get_active();core.write_json(core.SETTINGS,data)
            if check.get_active():self.start_photo_downloads()
            else:self.photos.stop()
            self.photos_changed(None,self.photos.state)
        enabled.connect('toggled',toggle)
        content.pack_start(label(_('O catálogo tem {0} fotos disponíveis. Modelos sem foto usam uma ilustração. Fotos que você adicionar manualmente são preservadas.').format(self.photos.state['total']),'muted','small',wrap=True),False,False,0)
        credit=label('','muted','small',wrap=True)
        credit.set_markup(_('Fotos: Sony Interactive Entertainment e respectivos titulares; não fazem parte da licença GPL do código. <a href="https://www.playstation.com/en-us/legal/website-terms-of-use/">Termos de uso</a>.\nO download usa apenas os endereços das imagens, sem enviar nomes ou identificadores dos seus controles.'))
        content.pack_start(credit,False,False,0)
        self.photos_changed(None,self.photos.state)
        dialog.show_all();dialog.run();self.photo_controls=None;dialog.destroy()

    def import_picture(self,parent,model,status):
        # The destination is captured before the file chooser opens: a photo
        # never follows a later draft selection or a device on another USB port.
        chooser=Gtk.FileChooserDialog(title=_('Foto para {0}').format(_(artwork.model(model)['name'])),transient_for=parent,action=Gtk.FileChooserAction.OPEN)
        chooser.add_buttons(_('Cancelar'),Gtk.ResponseType.CANCEL,_('Adicionar à biblioteca'),Gtk.ResponseType.OK)
        formats=Gtk.FileFilter();formats.set_name(_('Fotos PNG, JPEG e WebP'))
        for mime in ('image/png','image/jpeg','image/webp'):formats.add_mime_type(mime)
        chooser.add_filter(formats)
        try:
            if chooser.run()==Gtk.ResponseType.OK:
                try:
                    artwork.import_photo(model,chooser.get_filename())
                    if self.photo_gallery:self.photo_gallery.refresh_picture(model)
                    status.set_text(_('Foto adicionada à biblioteca local deste modelo.'))
                except (OSError,ValueError,GLib.Error) as exc:status.set_text(str(exc))
        finally:chooser.destroy()

    def refresh(self):
        if self.busy: return True
        ready=self.helper_ready()
        settings=core.settings()
        devices=sorted(p for p in core.USB.iterdir() if core.supported(p))
        now=time.monotonic()
        self.reconcile_streams(devices)
        if ready:
            candidates=[];identities={}
            for device in devices:
                try:
                    identity=core.key(device)
                    if settings['modes'].get(identity,'play')!='charge':
                        candidates.append(device);identities[device.name]=identity
                except OSError:continue
            accesses=self.access_guard.check(candidates,identities,settings['protection'],now)
            if accesses:
                settings=core.settings()
                for identity,apps in accesses.items():
                    settings['modes'][identity]='charge'
                    for device in candidates:
                        if identities[device.name]==identity:
                            self.stream_errors.pop(device.name,None)
                            self.stream_requests.pop(device.name,None)
                            self.transitions[device.name]=now+12
                    settings['protection'].setdefault('last_actions',{})[identity]=_('Proteção automática: acesso de ')+apps[:180]+'.'
                    self.notice.set_text(settings['names'].get(identity,_('Controle'))+_(' entrou em Só carregar: ')+apps[:180]+'.')
                core.write_json(core.SETTINGS,settings)
        if now>=self.next_game_scan:
            self.native_game=self.game_detector.update(running_game(settings.get('native_games',[])))
            self.next_game_scan=now+3
        self.tray.status.set_label(_('Uplugo · {0} controle(s) conectado(s)').format(len(devices)))
        cache=core.read_cache()
        models={}
        for device in devices:
            try:
                identity=core.key(device)
                preferred=settings['modes'].get(identity,'play')
                if preferred not in MODES:preferred='play'
                wanted=effective_mode(preferred,self.native_game)
                interfaces=core.interfaces(device)
                enabled=bool(interfaces) and all((i/'authorized').read_text().strip()=='1' for i in interfaces)
                if enabled and ready:self.ensure_stream(device,wanted)
                elif not enabled:self.stop_stream(device.name)
                current=self.live.get(device.name)
                if current and (current.get('_connection')!=core.fingerprint(device) or now-current.get('_received',0)>5):current=None
                current=current or core.battery(device)
                fresh=current is not None
                reading=current or cache.get(identity)
                status=self.stream_status.get(device.name,{})
                confirmed=confirmed_mode(wanted,status,fresh,self.stream_kinds.get(device.name),bool(core.raw_device(device)))
                if confirmed:self.transitions.pop(device.name,None)
                elif self.transitions.get(device.name,now+1)<now:
                    self.transitions.pop(device.name,None)
                    self.stream_errors[device.name]=_('Não foi possível confirmar a troca. Verifique o cabo e tente novamente.')
                name=settings['names'].get(identity,'DualSense '+str(len(models)+1))
                rgb=settings['effects'].get(identity,{}).get('rgb')
                if not isinstance(rgb,list) or len(rgb)!=3 or any(type(v)!=int or not 0<=v<=255 for v in rgb):rgb=None
                models[identity]=ControllerState(identity=identity,name=name,port=device.name,
                    requested=preferred,effective=wanted,confirmed=confirmed,fresh=fresh,reading=reading,
                    error=self.stream_errors.get(device.name,''),helper_ready=ready,
                    transition=device.name in self.transitions,
                    native_game=self.games.get(self.native_game,self.native_game),
                    observation=self.charge_watch.describe(identity),rgb=rgb,
                    appearance=settings['appearance'].get(identity,'neutral'),
                    guard_reason=settings['protection'].get('last_actions',{}).get(identity,''))
            except (OSError,ValueError):continue
        for identity,name in settings['names'].items():
            if identity not in models and not identity.startswith('connection:'):
                models[identity]=ControllerState(identity=identity,name=name,connected=False,
                    requested=settings['modes'].get(identity,'play'),reading=cache.get(identity),
                    appearance=settings['appearance'].get(identity,'neutral'))
        self.models=models
        self.dashboard.update(list(models.values()),ready)
        return True

    def request_mode(self, identity, mode):
        self.refresh()
        state=self.models.get(identity)
        if not state or not state.can_change or mode not in MODES:
            self.notice.set_text(_('Aguarde o controle conectar e a operação atual terminar.'))
            return
        device=core.USB/state.port
        if core.key(device)!=identity:
            self.notice.set_text(_('A conexão mudou. Localize o controle novamente antes de trocar o modo.'))
            return
        self.stream_errors.pop(state.port,None)
        self.stream_requests.pop(state.port,None)
        data=core.settings();data['modes'][identity]=mode
        exceptions=set(data['protection'].get('play_exceptions',[]))
        if mode!='charge' and data['protection'].get('allow_manual_play',True):exceptions.add(identity)
        else:exceptions.discard(identity)
        data['protection']['play_exceptions']=sorted(exceptions)
        data['protection'].get('last_actions',{}).pop(identity,None)
        core.write_json(core.SETTINGS,data)
        self.transitions[state.port]=time.monotonic()+12
        interfaces=core.interfaces(device)
        if interfaces and all((i/'authorized').read_text().strip()=='1' for i in interfaces):
            self.refresh()
        else:
            self.run(['pkexec',str(HELPER),'--switch',state.port,'play'],lambda r:None)
        # The row already displays the transition and confirmed mode in place.
        self.notice.set_text('')

    def card_action(self, identity, action):
        state=self.models.get(identity)
        if not state:return
        if action=='rename':self.rename_dialog(identity);return
        if action=='details':self.details_dialog(identity);return
        if action=='touchpad':
            from touchpad_ui import TouchpadDialog,touchpad_error
            try:dialog=TouchpadDialog(identity,state.name,self)
            except ValueError as exc:self.notice.set_text(touchpad_error(str(exc)));return
            dialog.run();dialog.destroy();return
        if action=='input':self.input_dialog(identity);return
        if not state.connected or not state.confirmed or state.transition:
            self.notice.set_text(_('Aguarde o controle confirmar o modo atual.'));return
        if action=='effects' and not state.can_customize:
            self.notice.set_text(_('Personalização disponível em Minhas configurações.'));return
        if core.key(core.USB/state.port)!=identity:
            self.notice.set_text(_('A conexão mudou. Abra a ação novamente no controle correto.'));return
        self.action(state.port,action)

    def rename_dialog(self, identity):
        state=self.models[identity]
        if identity.startswith('connection:'):
            self.notice.set_text(_('Aguardando a identificação permanente do controle.'));return
        dialog=themed_dialog(_('Nome e aparência'),self,830)
        fit_window(dialog,830,740)
        dialog.add_buttons(_('Cancelar'),Gtk.ResponseType.CANCEL,_('Salvar'),Gtk.ResponseType.OK)
        content=dialog.get_content_area()
        save=dialog.get_widget_for_response(Gtk.ResponseType.OK);style(save,'primary')
        editor=AppearanceEditor(state,lambda:save.set_sensitive(editor.valid and editor.dirty),
                                lambda model:self.photos_dialog(dialog,model))
        self.photo_gallery=editor.gallery
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False);scroll.add(editor);content.pack_start(scroll,True,True,0)
        note=label('','muted','small',wrap=True);note.set_no_show_all(True)
        content.pack_start(note,False,False,0)
        save.set_tooltip_text(_('Salvar altera apenas o nome e o modelo escolhido para este controle.'))
        save.set_sensitive(False)
        dialog.show_all()
        editor.name.grab_focus()
        try:
            while dialog.run()==Gtk.ResponseType.OK:
                if not editor.valid or not editor.dirty:continue
                try:
                    # Merge with current preferences, even if this controller
                    # disconnected or moved to another port while editing.
                    data=core.settings();data['names'][identity]=editor.name.get_text().strip()
                    data['appearance'][identity]=editor.gallery.selected;core.write_json(core.SETTINGS,data)
                    break
                except OSError:
                    note.set_text(_('Não foi possível salvar. Suas alterações continuam aqui; tente novamente.'))
                    note.show()
        finally:
            self.photo_gallery=None;dialog.destroy();self.refresh()

    def details_dialog(self, identity):
        state=self.models[identity]
        dialog=themed_dialog(_('Bateria e conexão'),self)
        dialog.add_buttons(_('Fechar'),Gtk.ResponseType.CLOSE)
        panel=BatteryPanel(state.name)
        attach_battery_panel(dialog,panel)
        def update_details():
            panel.update(self.charge_watch,identity,self.models.get(identity))
            return True
        update_details();timer=GLib.timeout_add_seconds(1,update_details)
        try:dialog.show_all();dialog.run()
        finally:GLib.source_remove(timer);dialog.destroy()

    def development_dialog(self):
        from diagnostics import snapshot
        from doctor import checks
        dialog=themed_dialog(_('Desenvolvimento e diagnóstico'),self,720)
        fit_window(dialog,640,520)
        dialog.add_button(_('Fechar'),Gtk.ResponseType.CLOSE)
        outer=Gtk.ScrolledWindow();outer.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        outer.set_overlay_scrolling(False)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        content.set_valign(Gtk.Align.START);outer.add(content)
        dialog.get_content_area().pack_start(outer,True,True,0)
        content.pack_start(label(_('Investigue sem alterar os controles'),'controller-name',wrap=True),False,False,0)
        content.pack_start(label(_('O laboratório usa controles e falhas simuladas em outra janela. '
                                'As preferências reais e as sessões USB continuam separadas.'),
                                'muted',wrap=True),False,False,0)
        content.pack_start(button(_('Abrir laboratório sem USB'),lambda b:subprocess.Popen(
            ['/usr/bin/python3',str(BASE/'development.py')],close_fds=True),'primary'),False,False,0)
        content.pack_start(Gtk.Separator(),False,False,0)
        content.pack_start(label(_('Diagnóstico para compartilhar'),'setting-title',wrap=True),False,False,0)
        summary=label('',wrap=True);content.pack_start(summary,False,False,0)
        content.pack_start(label(_('Não inclui nomes, números de série, portas, caminhos pessoais '
                                'nem histórico dos botões. Revise o texto antes de compartilhar.'),
                                'muted','small',wrap=True),False,False,0)
        text=Gtk.TextView();text.set_editable(False);text.set_cursor_visible(False)
        text.set_monospace(True);text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text.get_accessible().set_name(_('Relatório de diagnóstico'))
        scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(180);scroll.add(text)
        detail=Gtk.Expander();detail.set_label_widget(label(_('Ver relatório completo'),wrap=True))
        detail.add(scroll);content.pack_start(detail,False,False,0)
        report=button(_('Relatar um problema…'),lambda b:self.report_problem(dialog),'quiet')
        report.set_halign(Gtk.Align.START);content.pack_start(report,False,False,0)
        copied=label('','small',wrap=True)
        copied.set_no_show_all(True)
        dialog.get_content_area().pack_start(copied,False,False,0)
        def update():
            data=self.diagnostics_report()
            text.get_buffer().set_text(json.dumps(data,ensure_ascii=False,indent=2))
            required=[item for item in data['dependencies'] if item['required']]
            summary.set_text(_('Dependências necessárias: {0} de {1} disponíveis').format(
                sum(item['ok'] for item in required),len(required))+'\n'+
                _('Controles conectados nesta leitura: {0}').format(sum(item['connected'] for item in data['controllers'])))
            copied.hide()
        def copy():
            buffer=text.get_buffer()
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(buffer.get_text(*buffer.get_bounds(),True),-1)
            copied.set_text(_('✓ Diagnóstico copiado'));copied.show()
        actions=AdaptiveBox(spacing=10)
        actions.pack_start(button(_('Atualizar diagnóstico'),lambda b:update(),'quiet'),False,False,0)
        actions.pack_start(button(_('Copiar diagnóstico'),lambda b:copy(),'quiet'),False,False,0)
        dialog.get_content_area().pack_start(actions,False,False,0)
        update();dialog.show_all();dialog.run();dialog.destroy()

    def diagnostics_report(self):
        from diagnostics import snapshot
        from doctor import checks
        return snapshot(list(self.models.values()),self.stream_status,self.charge_watch.entries,
                        checks(session=False),os.environ.get('XDG_SESSION_TYPE',''))

    def report_problem(self,parent=None):
        from bug_report import issue_url
        report=self.diagnostics_report()
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(json.dumps(report,ensure_ascii=False,indent=2),-1)
        url,included=issue_url(report)
        try:
            Gtk.show_uri_on_window(parent or self,url,Gdk.CURRENT_TIME)
            self.notice.set_text(_('O formulário de problema abriu no navegador. Revise tudo antes de enviar.') if included
                                 else _('O formulário abriu no navegador. O diagnóstico foi copiado: cole no campo Diagnóstico.'))
        except GLib.Error:
            self.notice.set_text(_('Não foi possível abrir o navegador. Acesse {0}/issues; o diagnóstico foi copiado.').format(REPOSITORY))
        return url

    def about_dialog(self):
        dialog=themed_dialog(_('Sobre o Uplugo'),self,600)
        fit_window(dialog,600,580)
        dialog.add_buttons(_('Fechar'),Gtk.ResponseType.CLOSE)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=15)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.add(content);dialog.get_content_area().pack_start(scroll,True,True,0)
        for text,cls in [('Uplugo · '+VERSION,'controller-name'),(_('Controle seus efeitos ou deixe tudo com o jogo.'),'muted'),(_('Minhas configurações: suas cores, vibração e peso dos gatilhos têm prioridade.\nConfigurações do jogo: recursos nativos ficam com o jogo.\nSó carregar: o controle fica fora dos jogos.'),'small'),(_('Idiomas disponíveis: Português (Brasil), English e Español.'),'small'),(_('Projeto independente para Linux. Compatibilidade com jogos e recursos avançados varia. Áudio USB não é virtualizado; para háptica nativa completa, use Configurações do jogo.'),'muted'),(_('Fechar a janela mantém o app na bandeja. Para encerrar e liberar os controles, use Sair no menu da bandeja.'),'muted')]:
            content.pack_start(label(text,cls,wrap=True),False,False,0)
        credit=label('','small',wrap=True)
        credit.set_markup(_('Código e ilustrações próprias: GPL-3.0-only. Geometria do blueprint: the_al, licença MIT (créditos em THIRD_PARTY.md).\nAs fotos adicionadas à biblioteca local mantêm os direitos de seus autores. Imagens oficiais de produto: Sony Interactive Entertainment e respectivos titulares; não estão incluídas no pacote do projeto. <a href="https://www.playstation.com/en-us/legal/website-terms-of-use/">Termos das imagens oficiais</a>.\nProjeto independente, sem afiliação à Sony.'))
        content.pack_start(credit,False,False,0)
        dialog.show_all();dialog.run();dialog.destroy()

    def run_operation(self, operation, done, failed=None):
        if self.busy: return
        self.busy=True
        self.cards.set_sensitive(False)
        self.unlock.set_sensitive(False)
        self.notice.set_text(_('Aguarde…'))
        self.dashboard.update(list(self.models.values()),self.helper_ready())
        def worker():
            try:
                result=operation()
            except Exception as e:
                result=subprocess.CompletedProcess([],1,'',str(e))
            GLib.idle_add(finish,result)
        def finish(result):
            if self.closed:return False
            self.busy=False
            self.cards.set_sensitive(True)
            if result.returncode:
                if failed:failed(result)
                else:self.notice.set_text(result.stderr.strip() or _('Operação cancelada.'))
            else:
                try: done(result)
                except Exception as e:self.notice.set_text(str(e))
            self.refresh()
            return False
        threading.Thread(target=worker,daemon=True).start()

    def run(self, command, done, failed=None, wait_for=None, connection=None):
        def operation():
            if wait_for is not None:
                try:wait_for.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    return subprocess.CompletedProcess(command,1,'',_('O serviço USB ainda está encerrando. Aguarde antes de tentar novamente.'))
            def same_connection():
                return connection is None or bool(connection[1] and core.fingerprint(connection[0])==connection[1])
            if not same_connection():
                return subprocess.CompletedProcess(command,1,'',_('A conexão mudou. Abra a ação novamente no controle correto.'))
            result=subprocess.run(command,capture_output=True,text=True)
            # Retry only a battery read that still contains the kernel's
            # initial Unknown value; never repeat identification or effects.
            if command[-1]=='read' and result.returncode==0:
                for attempt in range(3):
                    if not same_connection():break
                    reading=json.loads(result.stdout).get('reading')
                    if reading and reading.get('status')!='Unknown':break
                    time.sleep(.7)
                    if not same_connection():break
                    result=subprocess.run(command,capture_output=True,text=True)
                    if result.returncode:break
            if not same_connection():
                return subprocess.CompletedProcess(command,1,'',_('A conexão mudou. Abra a ação novamente no controle correto.'))
            return result
        self.run_operation(operation,done,failed)

    def install(self):
        if self.busy:return
        from access_request import run_access
        prepared={}
        def failure(result):
            self.access_setup=AccessSetup('cancelled' if result.returncode==126 else 'failed',
                '' if result.returncode==126 else (result.stderr.strip() or _('O sistema não concluiu a configuração.')))
            self.notice.set_text('')
            self.dashboard.update(list(self.models.values()),self.helper_ready())
        self.access_setup=AccessSetup('busy')
        def operation():
            result,prepared['helper']=run_access('install')
            if DEPLOYMENT.system and result.returncode==0 and not self.native_authorization.confirm():
                return subprocess.CompletedProcess([],1,'',_('A concessão foi salva, mas o sistema ainda não confirmou o acesso desta sessão. Verifique se sua sessão local está ativa e tente novamente.'))
            return result
        def installed(result):
            try:verified=HELPER.read_text()==prepared['helper']
            except OSError:verified=False
            if not verified:
                failure(subprocess.CompletedProcess([],1,'',_('O suporte instalado não corresponde a esta versão do app. Tente configurar novamente.')))
                return
            # Native access changes only this account's grant. Its immutable
            # helper has not been replaced, so existing streams can continue.
            if not DEPLOYMENT.system:self.stop_all()
            self.stream_errors.clear()
            self.access_setup=AccessSetup()
            self.notice.set_text(_('Acesso USB autorizado para esta conta. Seus modos foram preservados.') if DEPLOYMENT.system else
                _('Suporte USB atualizado. Retomando os modos escolhidos.'))
        self.run_operation(operation,installed,failed=failure)

    def action(self, name, mode):
        if mode=='effects':
            self.effects_dialog(name)
            return
        if mode in {'play','charge','proxy'}:
            self.request_mode(core.key(core.USB/name),mode)
            return
        exclusive=self.stream_kinds.get(name) == 'managed'
        if exclusive and mode=='read':
            self.notice.set_text(self.charge_watch.describe(core.key(core.USB/name))+_(' As leituras são automáticas; não é preciso tirar o cabo.'))
            return
        if exclusive and mode=='identify':
            process=self.streams[name]
            try:process.stdin.write(json.dumps({'identify':True})+'\n');process.stdin.flush()
            except OSError:self.notice.set_text(_('Controle desconectado.'))
            return
        connection=(core.USB/name,core.fingerprint(core.USB/name))
        previous=None
        if not (exclusive and mode=='rename'):
            previous=self.streams.get(name)
            self.stop_stream(name)
        self.measured[name]=time.monotonic()
        action='read' if mode=='rename' else 'play' if mode=='charge' else mode
        command=['pkexec',str(HELPER),'--switch',name,action] if DEPLOYMENT.system or HELPER.exists() else ['pkexec','/usr/bin/python3','-I',str(BASE/'dualsense.py'),'--switch',name,action]
        def complete(result):
            if not connection[1] or core.fingerprint(connection[0])!=connection[1]:
                self.notice.set_text(_('A conexão mudou. Abra a ação novamente no controle correto.'))
                return
            if action in {'read','identify'}:
                payload=json.loads(result.stdout)
                if payload.get('reading') and payload['reading'].get('status') == 'Unknown':
                    payload['reading'] = None
                core.remember(core.USB/name,payload['identity'])
                core.save_reading(core.USB/name,payload['reading'])
                self.notice.set_text(_('Modo anterior restaurado. ') + (_('Bateria atualizada.') if payload['reading'] else _('O controle não informou a bateria.')))
                if mode=='rename':
                    if not payload['identity']:
                        self.notice.set_text(_('Identidade permanente indisponível; nome não pode acompanhar troca de porta.'))
                        return
                    dialog=Gtk.Dialog(title=_('Renomear controle'),transient_for=self,modal=True)
                    dialog.add_buttons(_('Cancelar'),Gtk.ResponseType.CANCEL,_('Salvar'),Gtk.ResponseType.OK)
                    entry=Gtk.Entry();entry.set_text(core.nickname(core.USB/name));entry.set_activates_default(True)
                    dialog.set_default_response(Gtk.ResponseType.OK)
                    dialog.get_content_area().pack_start(entry,True,True,16);dialog.show_all()
                    if dialog.run()==Gtk.ResponseType.OK and entry.get_text().strip():
                        data=core.settings();data['names'][payload['identity']]=entry.get_text().strip()[:60]
                        core.write_json(core.SETTINGS,data)
                    dialog.destroy()
            else:
                identity = core.key(core.USB/name)
                if not identity.startswith('connection:'):
                    data=core.settings();data.setdefault('modes', {})[identity]=mode
                    core.write_json(core.SETTINGS,data)
                self.notice.set_text(_('Controle ativo; acompanhe o estado de carga atual.') if mode=='play' else _('USB exclusivo: a Steam não recebe comandos. A bateria é lida sem reativar o driver.'))
        if exclusive and mode=='rename':
            payload={'identity':core.key(core.USB/name),'reading':self.live.get(name)}
            complete(subprocess.CompletedProcess([],0,json.dumps(payload),''));self.refresh()
        else:self.run(command,complete,wait_for=previous,connection=connection)

    def reconcile_streams(self,devices):
        # A USB address can change without an empty enumeration between ticks.
        # Old failures and queued reports must never belong to the next occupant.
        current={device.name:core.fingerprint(device) for device in devices}
        for name in set(self.stream_connections)|set(self.streams):
            if name not in current or self.stream_connections.get(name)!=current[name]:
                self.live.pop(name,None);self.stream_status.pop(name,None)
                self.transitions.pop(name,None)
                if self.input_watch and self.input_watch[0]==name:self.input_sample=None
                if not self.stop_stream(name):continue
                self.stream_errors.pop(name,None)
                self.stream_connections.pop(name,None)
        for name,connection in current.items():
            if name not in self.stream_connections and name not in self.streams:
                self.stream_connections[name]=connection
        for name in list(self.stream_stopping):self.stop_stream(name)

    def stop_stream(self,name,wait=False):
        self.stream_kinds.pop(name,None)
        self.stream_requests.pop(name,None)
        self.stream_status.pop(name,None)
        self.live.pop(name,None)
        process=self.streams.get(name)
        if process is None:
            self.stream_stopping.pop(name,None)
            return True
        if name not in self.stream_stopping:
            self.stream_stopping[name]=time.monotonic()
            try:
                process.stdin.write(json.dumps({'stop':True})+'\n');process.stdin.flush()
            except (OSError,ValueError):pass
            finally:
                try:process.stdin.close()
                except (OSError,ValueError):pass
        if wait:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:pass
        if process.poll() is None:
            if time.monotonic()-self.stream_stopping[name]>=3:
                self.stream_errors[name]=_('O serviço USB ainda está encerrando. Aguarde antes de tentar novamente.')
            return False
        self.streams.pop(name,None);self.stream_stopping.pop(name,None)
        self.stream_errors.pop(name,None)
        return True

    def stop_all(self):
        for name in list(self.streams):self.stop_stream(name,wait=True)

    def ensure_stream(self,device,mode='play'):
        connection=core.fingerprint(device)
        if not connection or self.stream_connections.get(device.name)!=connection:return
        if device.name in self.stream_stopping:
            if not self.stop_stream(device.name):return
        if device.name in self.stream_errors:return
        kind='managed' if mode in {'charge','proxy'} else 'direct'
        process=self.streams.get(device.name)
        if process and self.stream_kinds.get(device.name)!=kind:
            if not self.stop_stream(device.name):return
            process=None
        config=core.settings().get('effects',{}).get(core.key(device)) if self.protect.get_active() else None
        request={'mode':mode,'config':config} if kind=='managed' else {'release':True}
        if process and process.poll() is None:
            try:
                if self.stream_requests.get(device.name)!=request:
                    process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
                    self.stream_requests[device.name]=request
            except OSError:self.stop_stream(device.name)
            return
        command=['pkexec',str(HELPER),'--exclusive',device.name,mode] if kind=='managed' else ['pkexec',str(HELPER),'--stream',device.name]
        self.stream_status.pop(device.name,None);self.live.pop(device.name,None)
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        self.streams[device.name]=process
        self.stream_kinds[device.name]=kind
        try:
            process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
            self.stream_requests[device.name]=request
        except OSError:pass
        def reader():
            for line in process.stdout:
                try:
                    payload=json.loads(line)
                    GLib.idle_add(receive,payload)
                except ValueError:pass
            error=process.stderr.read().strip()
            process.wait()
            def failed():
                if self.streams.get(device.name) is process:
                    if device.name in self.stream_stopping:self.stop_stream(device.name)
                    else:
                        self.stream_errors[device.name]=error or _('O serviço USB encerrou.')
                        self.notice.set_text(self.stream_errors[device.name])
                return False
            GLib.idle_add(failed)
        def receive(payload):
            if core.fingerprint(device)!=connection:return False
            if self.streams.get(device.name) is not process:return False
            if device.name in self.stream_stopping:return False
            if 'input' in payload:
                if self.input_watch == (device.name, connection):
                    state=payload['input']
                    observed=set(state.get('observed',[]))
                    if self.input_sample:observed.update(self.input_sample[0].get('observed',[]))
                    self.input_sample=(dict(state,observed=sorted(observed)),time.monotonic())
                return False
            self.stream_status[device.name]=payload
            if not payload.get('reading'):return False
            core.remember(device,payload['identity'])
            core.save_reading(device,payload['reading'])
            self.charge_watch.observe(core.key(device),connection,payload['reading'],port=device.name)
            self.live[device.name]=dict(payload['reading'],_received=time.monotonic(),_connection=connection)
            return False
        threading.Thread(target=reader,daemon=True).start()

    def input_dialog(self, identity):
        state=self.models.get(identity)
        if self.busy or not state or not state.connected or not state.confirmed or state.transition:
            self.notice.set_text(_('Aguarde a conexão confirmar antes de testar.'));return
        try:ready=f'INPUT_MONITOR_VERSION = {INPUT_MONITOR_VERSION}' in HELPER.read_text()
        except OSError:ready=False
        if not ready:
            dialog=themed_dialog(_('Atualizar teste de botões'),self)
            dialog.get_content_area().pack_start(label(_('O teste precisa atualizar o serviço USB uma vez. '
                'Os modos e nomes salvos serão mantidos. O sistema pode pedir sua senha.'),wrap=True),False,False,0)
            dialog.add_buttons(_('Agora não'),Gtk.ResponseType.CANCEL,_('Atualizar suporte USB'),Gtk.ResponseType.OK)
            dialog.show_all();response=dialog.run();dialog.destroy()
            if response==Gtk.ResponseType.OK:self.install()
            return
        device=core.USB/state.port
        connection=core.fingerprint(device)
        if not connection or core.key(device)!=identity:
            self.notice.set_text(_('A conexão mudou. Abra o teste novamente.'));return
        try:edge=(device/'idProduct').read_text().strip().lower()=='0df2'
        except OSError:edge=False
        dialog=themed_dialog(_('Testar botões'),self,700)
        dialog.add_button(_('Concluir'),Gtk.ResponseType.CLOSE)
        content=dialog.get_content_area()
        content.pack_start(label(state.name,'controller-name'),False,False,0)
        route=label('','muted','small',wrap=True);route.set_max_width_chars(75)
        content.pack_start(route,False,False,0)
        panel=InputPanel(edge);attach_input_panel(dialog,panel)
        content.pack_start(label(_('Leitura bruta, sem alterar calibração. Pequenas oscilações dos analógicos '
                                'não comprovam defeito. Touchpad: deslize até dois dedos; aperte para testar o clique.'),
                                'dialog-note',wrap=True),False,False,0)
        self.input_watch=(state.port,connection);self.input_sample=None
        next_ping=last_frame=0
        def send(enabled):
            process=self.streams.get(state.port)
            if not process or process.poll() is not None:return False
            try:
                process.stdin.write(json.dumps({'monitor':enabled})+'\n');process.stdin.flush()
                return True
            except (OSError,ValueError):return False
        def tick():
            nonlocal next_ping,last_frame
            now=time.monotonic()
            current=self.models.get(identity)
            try:
                valid=bool(current and current.connected and current.port==state.port and
                           core.fingerprint(device)==connection and core.key(device)==identity)
            except (OSError,ValueError):valid=False
            if not valid:
                panel.waiting(_('Controle desconectado ou conexão alterada. Feche e abra o teste novamente.'))
                route.set_text(_('Leitura encerrada; nenhum modo foi alterado.'))
                self.input_watch=None;self.input_sample=None
                return True
            if current.transition or not current.confirmed or current.error:
                panel.waiting(_('Aguardando o modo atual confirmar…'));return True
            route.set_text(_('Só carregar · teste exclusivo aqui. A Steam não recebe estes comandos.')
                           if current.effective=='charge' else
                           _('Modo jogar · a Steam e os jogos também recebem os botões. '
                           'Para testar só aqui, volte e escolha Só carregar.'))
            if now>=next_ping:
                send(True);next_ping=now+.75
            sample=self.input_sample
            if sample and now-sample[1]<.5:
                if sample[1]!=last_frame:
                    panel.update(sample[0], sample[1]);last_frame=sample[1]
                    sample[0]['observed']=[]
            else:panel.waiting(_('Aguardando entradas atuais do controle…'))
            return True
        timer=GLib.timeout_add(33,tick)
        try:
            tick();dialog.show_all();dialog.run()
        finally:
            GLib.source_remove(timer)
            # Never send commands to a replacement controller on the same port.
            if core.fingerprint(device)==connection:send(False)
            self.input_watch=None;self.input_sample=None;dialog.destroy()

    def effects_dialog(self,name):
        if self.busy:return
        device=core.USB/name
        state=self.models.get(core.key(device))
        if not state or not state.can_customize:
            self.notice.set_text(_('Escolha Minhas configurações para personalizar este controle.'));return
        config=core.settings().get('effects',{}).get(core.key(device),{'rgb':[0,100,255],'vibration':'game'})
        if not isinstance(config.get('rgb'),list) or len(config['rgb'])!=3:
            config=dict(config,rgb=[0,100,255])
        dialog=themed_dialog(_('Luzes e efeitos'),self,590)
        monitor=self.get_display().get_monitor_at_window(self.get_window())
        area=monitor.get_workarea()
        dialog.set_default_size(min(590,area.width),min(680,max(300,area.height-64)))
        dialog.add_buttons(_('Cancelar'),Gtk.ResponseType.CANCEL,_('Salvar e aplicar'),Gtk.ResponseType.OK)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.add(content);dialog.get_content_area().pack_start(scroll,True,True,0)
        content.pack_start(label(state.name,'controller-name'),False,False,0)
        content.pack_start(label(_('Para este controle · Minhas configurações'),'muted','small'),False,False,0)
        try:trigger_ready='TRIGGER_CONTROL_VERSION = 2' in HELPER.read_text()
        except OSError:trigger_ready=False
        configured=bool(core.settings().get('effects',{}).get(state.identity)) and self.protect.get_active()
        editor=EffectsEditor(config,trigger_ready,configured);content.pack_start(editor,False,False,0)
        if not trigger_ready:
            content.pack_start(button(_('Atualizar suporte aos gatilhos'),lambda b:(dialog.response(Gtk.ResponseType.CANCEL),GLib.idle_add(self.install)),'quiet'),False,False,0)
        feedback=label('','dialog-note',wrap=True);feedback.set_margin_top(12)
        content.pack_start(feedback,False,False,0)
        trial=button(_('Experimentar peso · 5 s'),lambda b:preview_weight(),'quiet')
        trial.set_no_show_all(True);trial.set_image(icon('media-playback-start-symbolic'));trial.set_always_show_image(True)
        trial.set_halign(Gtk.Align.START);content.pack_start(trial,False,False,0)
        trial.set_tooltip_text(_('Experimenta apenas o peso de L2/R2 e volta ao ajuste salvo após 5 segundos.'))
        test=button(_('Vibrar com ajustes salvos · 1 s'),lambda b:rumble(),'quiet');test.set_halign(Gtk.Align.START)
        test.set_no_show_all(True);test.set_image(icon('media-playback-start-symbolic'));test.set_always_show_image(True)
        content.pack_start(test,False,False,0)
        save=dialog.get_widget_for_response(Gtk.ResponseType.OK);style(save,'primary')
        trial_until=0;trial_process=None;trial_connection=None;trial_failed=False
        def stop_trial():
            nonlocal trial_until,trial_process,trial_failed
            process=trial_process;trial_process=None;trial_until=0
            if process is None:return
            # Restore only this connection. A new controller on the same port
            # must never receive the old controller's preferences.
            if self.streams.get(name) is not process or core.fingerprint(device)!=trial_connection:return
            restore=core.settings().get('effects',{}).get(state.identity) if self.protect.get_active() else None
            try:
                process.stdin.write(json.dumps({'config':restore})+'\n');process.stdin.flush()
            except (OSError,ValueError):
                trial_failed=True
                self.stream_requests.pop(name,None)  # retry through normal refresh
        def preview_weight():
            nonlocal trial_until,trial_process,trial_connection,trial_failed
            if not available() or editor.values()['triggers']=='game':return
            stop_trial()
            process=self.streams.get(name)
            if process is None or process.poll() is not None:
                feedback.set_text(_('Sem conexão com o serviço USB. O teste não foi iniciado.'));return
            baseline=core.settings().get('effects',{}).get(state.identity) if self.protect.get_active() else None
            config=dict(baseline or {},triggers=editor.values()['triggers'])
            trial_process=process;trial_connection=core.fingerprint(device)
            try:
                process.stdin.write(json.dumps({'config':config})+'\n');process.stdin.flush()
            except (OSError,ValueError):
                stop_trial();feedback.set_text(_('Não foi possível enviar o teste ao controle.'));return
            trial_failed=False;trial_until=time.monotonic()+5
            update_editor()
        def available():
            current=self.models.get(state.identity)
            try:return bool(current and current.can_customize and current.port==name and core.key(device)==state.identity)
            except (OSError,ValueError):return False
        def update_editor():
            ready=available()
            if trial_until and (time.monotonic()>=trial_until or not ready):stop_trial()
            save.set_sensitive(ready and editor.dirty)
            trial.set_sensitive(ready and editor.values()['triggers']!='game' and not trial_until)
            test.set_sensitive(ready and not trial_until and not editor.dirty and editor.values()['vibration']!='off')
            trial.set_visible(editor.sections.get_visible_child_name()=='triggers')
            test.set_visible(editor.sections.get_visible_child_name()=='vibration')
            feedback.set_text(_('O controle mudou de modo ou desconectou. Seus ajustes não foram aplicados.') if not ready else
                              _('Não foi possível enviar o retorno do teste. Verifique a conexão USB.') if trial_failed else
                              _('Teste de peso enviado · solte e aperte L2/R2. Volta ao salvo em {0} s.').format(max(1,int(trial_until-time.monotonic())+1)) if trial_until else
                              _('Salve para testar a vibração.') if editor.dirty and editor.sections.get_visible_child_name()=='vibration' else '')
            feedback.set_visible(bool(feedback.get_text()))
            return True
        def rumble():
            if not available() or editor.dirty or editor.values()['vibration']=='off':return
            process=self.streams.get(name)
            if process and process.poll() is None:
                try:process.stdin.write('{"test":true}\n');process.stdin.flush()
                except OSError:pass
        def changed():
            stop_trial();update_editor()
        editor.on_change=changed;editor.on_section_change=changed
        timer=GLib.timeout_add(250,update_editor)
        dialog.show_all();update_editor()
        try:response=dialog.run()
        finally:GLib.source_remove(timer);stop_trial()
        if response==Gtk.ResponseType.OK:
            if not available():self.notice.set_text(_('A conexão mudou. Os efeitos não foram aplicados.'))
            else:
                data=core.settings();data.setdefault('effects',{})[state.identity]=editor.values()
                core.write_json(core.SETTINGS,data);self.protect.set_active(True)
                self.notice.set_text(_('Efeitos salvos e envio solicitado para ')+state.name+_('. Gatilhos: ')+editor.triggers.get_active_text()+'.')
        dialog.destroy();self.refresh()

    def profiles_dialog(self):
        from profiles_ui import GameProfileEditor
        dialog=themed_dialog(_('Jogos e troca de modo'),self,720)
        dialog.add_buttons(_('Cancelar'),Gtk.ResponseType.CANCEL,_('Salvar escolhas'),Gtk.ResponseType.OK)
        editor=GameProfileEditor(installed_games(),core.settings().get('native_games',[]))
        baseline=editor.profile_text();save=style(dialog.get_widget_for_response(Gtk.ResponseType.OK),'primary')
        save.set_sensitive(False);editor.on_change=lambda:save.set_sensitive(editor.profile_text()!=baseline)
        fit_window(dialog,720,700 if len(editor.checks)>3 else 580)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.add(editor);dialog.get_content_area().pack_start(scroll,True,True,0)
        error=label('','mode-status','error',wrap=True);dialog.get_content_area().pack_start(error,False,False,0)
        error.set_no_show_all(True)
        dialog.show_all();editor.filter_games()
        while dialog.run()==Gtk.ResponseType.OK:
            try:profiles=parse_profiles(editor.profile_text())
            except ValueError as exc:
                error.set_text(str(exc));error.show();editor.advanced.set_expanded(True);editor.manual.grab_focus()
                continue
            data=core.settings();data['native_games']=profiles
            try:core.write_json(core.SETTINGS,data)
            except OSError:
                error.set_text(_('Não foi possível salvar. Suas alterações continuam aqui; tente novamente.'));error.show()
                continue
            self.notice.set_text(_('Escolhas salvas. Jogos selecionados podem usar Configurações do jogo; Só carregar permanece igual.') if profiles else _('Troca automática por jogo desativada. Seus modos escolhidos permanecem iguais.'))
            break
        dialog.destroy()

if __name__=='__main__':
    if os.geteuid()==0:raise SystemExit(_('Abra o app como seu usuário, sem sudo.'))
    from session import run_application
    from maintenance import PendingInstallation
    try:raise SystemExit(run_application(Window))
    except PendingInstallation:
        os.execv('/usr/bin/python3',['/usr/bin/python3',str(BASE/'recovery_ui.py')])
