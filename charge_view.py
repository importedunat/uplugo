# SPDX-License-Identifier: GPL-3.0-only
"""Battery readings and bounded USB observation history; no hardware actions."""
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from i18n import _
from ui import label, button
from charge_watch import MAX_NOTE
from battery_plot import BatteryPlot
from layout import fit_window


class ObservationNoteDialog(Gtk.Dialog):
    def __init__(self, watch, identity, session, parent=None, saved=None):
        super().__init__(title=_('Anotar cabo e condições'), transient_for=parent, modal=True)
        self.set_destroy_with_parent(True)
        self.watch, self.identity, self.session_id = watch, identity, session['session_id']
        self.saved_callback = saved
        from ui import style
        style(self, 'dualsense');fit_window(self, 560, 440)
        self.add_button(_('Cancelar'), Gtk.ResponseType.CANCEL)
        self.save_button = self.add_button(_('Salvar'), Gtk.ResponseType.APPLY)
        self.set_default_response(Gtk.ResponseType.CANCEL)
        content = self.get_content_area();content.set_border_width(20)
        scroll = Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content.pack_start(scroll, True, True, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12);scroll.add(body)
        body.pack_start(label(observed_interval(session), 'small', wrap=True), False, False, 0)
        body.pack_start(label(_('Anote como você conectou o controle para comparar depois. O app não detecta qual cabo foi usado.'), wrap=True), False, False, 0)
        self.entry = Gtk.Entry();self.entry.set_max_length(MAX_NOTE);self.entry.set_text(session['note'])
        self.entry.set_placeholder_text(_('Ex.: cabo curto, porta traseira, sem hub'))
        self.entry.get_accessible().set_name(_('Cabo e condições desta observação'))
        body.pack_start(self.entry, False, False, 0)
        body.pack_start(label(_('Até 160 caracteres. Deixe vazio para remover a anotação. Ela fica somente neste período, mesmo que o controle seja reconectado.'), 'muted', wrap=True), False, False, 0)
        self.error = label('', wrap=True);body.pack_start(self.error, False, False, 0)
        self.connect('response', self.respond)

    def respond(self, dialog, response):
        if response != Gtk.ResponseType.APPLY:
            self.destroy();return
        try:
            self.watch.annotate(self.identity, self.session_id, self.entry.get_text())
        except LookupError:
            self.error.set_text(_('Esta observação já saiu do histórico. A anotação não foi transferida para outra.'))
            self.save_button.set_sensitive(False)
        except ValueError:
            self.error.set_text(_('Use uma linha de texto com até 160 caracteres.'))
        except OSError:
            self.error.set_text(_('Não foi possível salvar. Sua anotação continua aqui; tente novamente.'))
        else:
            if self.saved_callback:self.saved_callback()
            self.destroy()


def observed_interval(session):
    start = time.strftime('%d/%m/%Y %H:%M', time.localtime(session['started']))
    end = time.strftime('%d/%m/%Y %H:%M', time.localtime(session['seen']))
    minutes = int((session['seen'] - session['started']) / 60)
    duration = _('{0} min observados').format(minutes) if minutes else _('Menos de 1 min observado')
    return start + ' → ' + end + ' · ' + duration


def session_change(session):
    delta = session['capacity'] - session['baseline']
    return _('{0}% → {1}% · {2:+d} pontos percentuais').format(session['baseline'], session['capacity'], delta)


class BatteryPanel(Gtk.Box):
    def __init__(self, name):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.pack_start(label(name, 'controller-name', wrap=True), False, False, 0)
        self.value = label('', 'battery-value', wrap=True)
        self.observation = label('', wrap=True)
        self.pack_start(self.value, False, False, 0)
        self.pack_start(self.observation, False, False, 0)
        self.plot=BatteryPlot();self.pack_start(self.plot,False,False,0)
        self.pack_start(label(_('Leituras do controle · sem previsão de carga'),'muted','small',wrap=True),False,False,0)
        self.pack_start(Gtk.Separator(), False, False, 0)
        self.pack_start(label(_('Neste período'), 'controller-name', wrap=True), False, False, 0)
        self.change = label('', wrap=True)
        self.interval = label('', 'muted', 'small', wrap=True)
        self.changes = label('', 'small', wrap=True)
        for widget in (self.change, self.interval):
            widget.set_selectable(True)
            self.pack_start(widget, False, False, 0)
        recent=Gtk.Expander(label=_('Ver valores recebidos'));recent.add(self.changes)
        self.pack_start(recent,False,False,0)
        self.note = label('', 'small', wrap=True);self.note.set_no_show_all(True)
        self.pack_start(self.note, False, False, 0)
        self.note_button = button(_('Anotar cabo e condições'), lambda b:self.edit_note(), 'quiet')
        self.pack_start(self.note_button, False, False, 0)
        self.note_button.set_sensitive(False)
        self.history = Gtk.Expander(label=_('Períodos anteriores'))
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.history.add(self.history_box)
        self.pack_start(self.history, False, False, 0)
        interpretation=Gtk.Expander(label=_('Como interpretar a carga'))
        explanation=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        explanation.pack_start(label(_('A porcentagem vem do controle em passos aproximados de 10%. O indicador de carga não mede a corrente do cabo.'),'muted','small',wrap=True),False,False,0)
        explanation.pack_start(label(_('O histórico fica neste computador e guarda até 24 observações anteriores por controle. Reconexões e pausas nas leituras iniciam outra observação; o tempo sem dados não entra na comparação.'), 'muted', 'small', wrap=True), False, False, 0)
        explanation.pack_start(label(_('A porta USB é registrada, mas o app não identifica o cabo. A variação pode incluir uso e carga; não é uma medida da velocidade do carregador.'), 'muted', 'small', wrap=True), False, False, 0)
        interpretation.add(explanation);self.pack_start(interpretation,False,False,0)
        self.details = Gtk.Expander(label=_('Conexão e alimentação'))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.connection = label('', 'muted', 'small', wrap=True)
        self.connection.set_selectable(True)
        box.pack_start(self.connection, False, False, 0)
        box.pack_start(label(_('Com o PC desligado, a carga depende da alimentação USB da placa-mãe. O app não consegue manter a porta energizada nessa situação.'), 'muted', 'small', wrap=True), False, False, 0)
        self.details.add(box)
        self.pack_start(self.details, False, False, 0)
        self.history_signature = None
        self.context = None

    def edit_note(self, session=None):
        if self.context is None:return
        watch, identity, state, now = self.context
        sessions = watch.sessions(identity, now)
        session = session or (sessions[0] if sessions else None)
        if session is None:return
        parent = self.get_toplevel()
        dialog = ObservationNoteDialog(watch, identity, session, parent if isinstance(parent, Gtk.Window) else None,
                                       saved=lambda:self.update(*self.context))
        dialog.show_all();return dialog

    def update(self, watch, identity, state, now=None):
        self.context = (watch, identity, state, now)
        now = time.time() if now is None else now
        sessions = watch.sessions(identity, now)
        reading = (state.reading if state else None) or {}
        fresh = bool(state and state.connected and state.fresh and sessions and sessions[0]['fresh'])
        self.plot.update(watch.entries.get(identity,{}).get('samples',[]),fresh)
        capacity = reading.get('capacity')
        if type(capacity) is int:
            self.value.set_text(str(capacity)+'% · '+(state.battery_label if fresh else _('Leitura anterior')))
        else:
            self.value.set_text(_('Bateria ainda não informada'))
        self.observation.set_text(watch.describe(identity, now) if fresh else _('Sem leitura USB recente; aguardando o controle.'))
        if sessions:
            current = sessions[0]
            self.note.set_text(_('Sua anotação: {0}').format(current['note']) if current['note'] else '')
            self.note.set_visible(bool(current['note']))
            self.change.set_text(session_change(current))
            port = _('USB {0}').format(current['port']) if current['port'] else _('Porta não registrada')
            self.interval.set_text(port+'\n'+observed_interval(current))
        else:
            self.note.set_text('');self.note.hide()
            self.change.set_text(_('Ainda não há observações para este controle.'))
            self.interval.set_text('')
        self.note_button.set_sensitive(bool(sessions))
        changes = []
        for sample in watch.entries.get(identity, {}).get('samples', []):
            if not changes or sample['capacity'] != changes[-1]['capacity']:
                changes.append(sample)
        self.changes.set_text((_('Leituras recentes')+'\n'+'\n'.join(
            time.strftime('%H:%M', time.localtime(s['at']))+f"  ·  {s['capacity']}%" for s in changes[-5:])) if changes else '')
        # Archived periods never change; keep widgets/focus stable on live refresh.
        signature = tuple(tuple(sorted(s.items())) for s in sessions[1:])
        if signature != self.history_signature:
            self.history_signature = signature
            for child in self.history_box.get_children():
                child.destroy()
            if not sessions[1:]:
                self.history_box.pack_start(label(_('As observações anteriores aparecerão aqui depois de uma reconexão ou pausa nas leituras.'), 'muted', wrap=True), False, False, 0)
            for session in sessions[1:]:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                port = _('USB {0}').format(session['port']) if session['port'] else _('Porta não registrada')
                box.pack_start(label(port+' · '+session_change(session), wrap=True), False, False, 0)
                box.pack_start(label(observed_interval(session), 'muted', 'small', wrap=True), False, False, 0)
                reason = {'connection': _('Terminou com outra conexão USB.'),
                          'gap': _('Terminou com uma pausa nas leituras.'),
                          'clock': _('Terminou porque o relógio do sistema mudou.')}[session['reason']]
                box.pack_start(label(reason, 'muted', 'small', wrap=True), False, False, 0)
                if session['note']:
                    box.pack_start(label(_('Sua anotação: {0}').format(session['note']), 'small', wrap=True), False, False, 0)
                box.pack_start(button(_('Anotar cabo e condições'), lambda b,s=session:self.edit_note(s), 'quiet'), False, False, 0)
                box.pack_start(Gtk.Separator(), False, False, 0)
                self.history_box.pack_start(box, False, False, 0)
            self.history_box.show_all()
        voltage = reading.get('voltage')
        voltage_text = f'{voltage:.2f} V' if type(voltage) in (int, float) else _('não fornecida pelo controle')
        port = _('USB {0}').format(state.port) if state and state.connected else _('desconectado')
        self.connection.set_text(_('Última leitura: ')+reading.get('time', '—')+_('\nTensão: ')+voltage_text+_('\nConexão: ')+port)


def attach_battery_panel(dialog, panel):
    display = Gdk.Display.get_default()
    parent = dialog.get_transient_for()
    monitor = display.get_monitor_at_window(parent.get_window()) if parent and parent.get_window() else display.get_monitor(0)
    area = monitor.get_workarea() if monitor else None
    dialog.set_default_size(min(620, area.width-64) if area else 620,
                            min(760, area.height-80) if area else 760)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    panel.set_valign(Gtk.Align.START)
    scroll.add(panel)
    dialog.get_content_area().pack_start(scroll, True, True, 0)
    return scroll
