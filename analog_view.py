# SPDX-License-Identifier: GPL-3.0-only
"""Guided, read-only stick measurements. No device access or file persistence."""
import time
from gi.repository import Gtk, GdkPixbuf
from analog_test import AnalogSession, REST_SECONDS, DIRECTION_THRESHOLD, percent
from i18n import _
from ui import label, button, style
from layout import AdaptiveBox


class StickPlot(Gtk.Image):
    def __init__(self):
        super().__init__()
        self.frame = (None, ())
        self.width = 0
        self.render(240)

    def do_get_request_mode(self): return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_get_preferred_width(self): return (180, 240)
    def do_get_preferred_width_for_height(self,height):return self.get_preferred_width()
    def do_get_preferred_height(self): return (180, 240)
    def do_get_preferred_height_for_width(self, width):
        return (min(width, 280), min(width, 280))

    def do_size_allocate(self, allocation):
        Gtk.Image.do_size_allocate(self, allocation)
        width = max(1, min(280, allocation.width))
        if width != self.width: self.render(width)

    def show_state(self, current=None, trail=()):
        frame = (tuple(current) if current is not None else None, tuple(trail))
        if frame != self.frame:
            self.frame = frame
            self.render(self.width or 240)

    def render(self, width):
        current, trail = self.frame
        parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">',
                 '<rect x="1" y="1" width="238" height="238" rx="12" fill="#0b2030" stroke="#33576d"/>',
                 '<rect x="24" y="24" width="192" height="192" fill="none" stroke="#284a60"/>',
                 '<circle cx="120" cy="120" r="96" fill="none" stroke="#42687f"/>',
                 '<circle cx="120" cy="120" r="48" fill="none" stroke="#284a60" stroke-dasharray="3 5"/>',
                 '<path d="M24 120H216 M120 24V216" fill="none" stroke="#42687f"/>',
                 '<g font-family="sans-serif" font-size="11" fill="#9fb0c8" text-anchor="middle">',
                 '<text x="120" y="17">−Y</text><text x="120" y="232">+Y</text>',
                 '<text x="13" y="124">−X</text><text x="227" y="124">+X</text></g>']
        if trail:
            points = ' '.join(f'{120+x*.96:.2f},{120+y*.96:.2f}' for x, y in trail)
            parts.append(f'<polyline points="{points}" fill="none" stroke="#6da1e8" stroke-width="1.5" opacity=".65"/>')
        if current is not None:
            x, y = (120+value*.96 for value in current)
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#8ce6f3"/>')
        parts.append('</svg>')
        loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.set_size(width, width); loader.write(''.join(parts).encode()); loader.close()
        self.set_from_pixbuf(loader.get_pixbuf()); self.width = width


class AnalogGuide(Gtk.Box):
    def __init__(self, clock=time.monotonic):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.clock = clock
        self.session = AnalogSession()
        self.heading = label('', 'setting-title', wrap=True)
        self.prompt = label('', 'muted', wrap=True)
        self.pack_start(self.heading, False, False, 0)
        self.pack_start(self.prompt, False, False, 0)
        self.progress = Gtk.ProgressBar(); self.progress.set_no_show_all(True)
        self.pack_start(self.progress, False, False, 0)
        actions = AdaptiveBox(spacing=8)
        self.primary = button('', lambda widget: self.advance(), 'primary')
        self.clear = button(_('Limpar teste'), lambda widget: self.reset(), 'quiet')
        actions.pack_start(self.primary, False, False, 0)
        actions.pack_end(self.clear, False, False, 0)
        self.pack_start(actions, False, False, 0)
        columns = AdaptiveBox(spacing=16)
        self.plots = []; self.live_values = []; self.centers = []; self.spreads = []; self.directions = []; self.stats = []
        self.direction_names = {'up': _('Cima'), 'right': _('Direita'), 'down': _('Baixo'), 'left': _('Esquerda')}
        for title in (_('Analógico esquerdo'), _('Analógico direito')):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            column.pack_start(label(title, 'setting-title', wrap=True), False, False, 0)
            plot = StickPlot(); plot.get_accessible().set_name(title)
            column.pack_start(plot, False, False, 0); self.plots.append(plot)
            live = label('', 'small', wrap=True); column.pack_start(live, False, False, 0); self.live_values.append(live)
            center = label('', 'small', wrap=True); column.pack_start(center, False, False, 0); self.centers.append(center)
            spread = label('', 'dialog-note', wrap=True); column.pack_start(spread, False, False, 0); self.spreads.append(spread)
            row = Gtk.Box(spacing=4, homogeneous=True); keys = {}
            for key, symbol in (('up', '↑'), ('right', '→'), ('down', '↓'), ('left', '←')):
                value = style(Gtk.Label(label=symbol), 'direction-mark')
                row.pack_start(value, True, True, 0); keys[key] = (value, symbol)
            column.pack_start(row, False, False, 0); self.directions.append(keys)
            columns.pack_start(column, True, True, 0)
        self.pack_start(columns, False, False, 0)
        self.pack_start(label(_('✓ = direção que atingiu {0}% do eixo durante o alcance.').format(int(DIRECTION_THRESHOLD)),
                              'dialog-note', wrap=True), False, False, 0)
        self.detail = Gtk.Expander()
        self.detail.set_label_widget(label(_('Medições e como interpretar'),wrap=True))
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); detail_box.set_margin_top(10)
        for title in (_('Analógico esquerdo'), _('Analógico direito')):
            value = label('', 'small', wrap=True)
            detail_box.pack_start(label(title, 'setting-title'), False, False, 0)
            detail_box.pack_start(value, False, False, 0); self.stats.append(value)
        detail_box.pack_start(label(_('Centro médio é a média das leituras em repouso. As faixas mostram os menores e maiores valores recebidos. '
            'O desenho mostra os movimentos recentes; o círculo é uma referência, não uma meta de perfeição.'), 'dialog-note', wrap=True), False, False, 0)
        self.detail.add(detail_box); self.pack_start(self.detail, False, False, 0)
        self.pack_start(label(_('O jogo pode aplicar zona morta. Estas medidas, sozinhas, não confirmam drift. '
            'O teste não altera calibração nem configurações do jogo.'), 'dialog-note', wrap=True), False, False, 0)
        self.render()

    def reset(self):
        self.session.reset(); self.render()

    def interrupt(self):
        self.session.interrupt()
        if self.get_mapped(): self.render()

    def observe(self, values, now):
        self.session.observe(values, now)
        if self.get_mapped(): self.render(now)

    def advance(self):
        now = self.clock()
        if self.session.phase == 'ready': self.session.start_travel(now)
        elif self.session.phase == 'travel': self.session.finish(now)
        else: self.session.start_rest(now)
        self.render(now)

    def render(self, now=None):
        now = self.clock() if now is None else now
        session = self.session; phase = session.phase; live = session.live(now)
        heading, prompt, action = {
            'idle': (_('Analógicos · teste em duas etapas'), _('Primeiro, deixe os dois analógicos soltos por 5 segundos. Depois, gire cada um até as bordas.'), _('Começar repouso · 5 s')),
            'rest': (_('1 de 2 · deixe os analógicos soltos'), _('Medindo repouso · {0:.1f} s de 5 s').format(min(REST_SECONDS, session.rest.seconds)), _('Medindo…')),
            'ready': (_('Repouso registrado'), _('Na próxima etapa, faça uma volta completa com cada analógico. Você escolhe quando concluir.'), _('Medir alcance')),
            'travel': (_('2 de 2 · gire os analógicos'), _('Faça uma volta até as bordas com cada um, depois selecione Ver resultado.'), _('Ver resultado')),
            'done': (_('Resultado desta sessão') if live else _('Resultado anterior · sem leitura atual'), _('As marcas mostram as direções observadas. Uma direção sem marca não indica defeito.'), _('Repetir repouso · 5 s')),
            'interrupted': (_('Teste interrompido'), _('A leitura parou ou você mudou de tela. Recomece com o controle conectado.'), _('Recomeçar · 5 s')),
        }[phase]
        if not live and phase in ('idle', 'interrupted'):
            prompt = _('Aguardando uma leitura atual do controle para começar.')
        self.heading.set_text(heading); self.prompt.set_text(prompt); self.primary.set_label(action)
        self.primary.set_sensitive(live and phase != 'rest' and (phase != 'travel' or bool(session.travel.count)))
        self.clear.set_label(_('Cancelar') if phase in ('rest', 'travel') else _('Limpar teste'))
        self.clear.set_sensitive(phase != 'idle')
        self.progress.set_visible(phase == 'rest')
        self.progress.set_fraction(min(1, session.rest.seconds/REST_SECONDS))
        for stick in range(2):
            point = [percent(v) for v in session.values[stick*2:stick*2+2]] if live and phase != 'done' else None
            self.plots[stick].show_state(point, session.trails[stick])
            current = _('Ao vivo · X {0:+.1f}% · Y {1:+.1f}%').format(*point) if point is not None else _('Desenho do teste concluído') if phase == 'done' else _('Sem posição atual')
            self.live_values[stick].set_text(current); self.plots[stick].get_accessible().set_description(current)
            means = session.rest.means
            self.centers[stick].set_text(_('Centro médio · X {0:+.1f}% · Y {1:+.1f}%').format(*means[stick*2:stick*2+2])
                                        if means is not None and phase != 'rest' else _('Medindo o centro…') if phase == 'rest' else _('Repouso ainda não medido'))
            a, b = stick*2, stick*2+1
            self.spreads[stick].set_text(_('Faixa em repouso\nX {0:+.1f}% a {1:+.1f}%\nY {2:+.1f}% a {3:+.1f}%').format(
                percent(session.rest.low[a]), percent(session.rest.high[a]), percent(session.rest.low[b]), percent(session.rest.high[b]))
                if means is not None and phase != 'rest' else '')
            seen = session.travel.directions(stick)
            for key, (widget, symbol) in self.directions[stick].items():
                widget.set_text(('✓ ' if key in seen else '· ')+symbol)
                widget.get_accessible().set_name(self.direction_names[key]+(_(' · observado') if key in seen else _(' · ainda não observado')))
                widget.get_style_context().remove_class('observed')
                if key in seen: style(widget, 'observed')
            parts = []
            for title, window in ((_('Repouso'), session.rest), (_('Alcance'), session.travel)):
                if window.count:
                    a, b = stick*2, stick*2+1
                    parts.append(title+' · '+_('{0} leituras em {1:.1f} s').format(window.count, window.seconds)+'\n'+
                                 _('X {0:+.1f}% a {1:+.1f}% · Y {2:+.1f}% a {3:+.1f}%').format(percent(window.low[a]), percent(window.high[a]), percent(window.low[b]), percent(window.high[b])))
            self.stats[stick].set_text('\n'.join(parts) or _('Nenhuma medição nesta sessão.'))
