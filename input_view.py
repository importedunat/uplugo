# SPDX-License-Identifier: GPL-3.0-only
"""A live, read-only test bench. No USB access or preference writes."""
from i18n import _
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango
from input_state import BUTTON_NAMES, EDGE_BUTTON_NAMES
from ui import label, button, style
from layout import AdaptiveBox, AdaptiveStackSwitcher
from controller_blueprint import blueprint_svg, WIDTH, HEIGHT
from analog_view import AnalogGuide
from motion_view import MotionPanel
import time


def attach_input_panel(dialog, panel):
    """Keep the close button reachable even with details open on a small screen."""
    display = Gdk.Display.get_default()
    parent = dialog.get_transient_for()
    monitor = display.get_monitor_at_window(parent.get_window()) if parent and parent.get_window() else display.get_monitor(0)
    area = monitor.get_workarea() if monitor else None
    available = area.height if area else 800
    width = max(360, min(760, area.width-64)) if area else 760
    dialog.set_default_size(width, max(240, min(900, available-80)))
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(180)
    panel.set_valign(Gtk.Align.START)
    scroll.add(panel)
    dialog.get_content_area().pack_start(scroll, True, True, 0)
    return scroll


class BlueprintImage(Gtk.Image):
    """Scale the vector to the available width; reuse identical input frames."""
    def __init__(self):
        super().__init__()
        self.snapshot = None
        self.render_width = 0
        self.background = None
        self.background_width = 0
        self.svg = ''
        self.get_accessible().set_name(_('Vista frontal do DualSense: botões, analógicos e gatilhos'))
        self.show_state()

    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_get_preferred_width(self):return (360, 650)
    def do_get_preferred_width_for_height(self,height):return self.get_preferred_width()
    def do_get_preferred_height(self):return (round(360*HEIGHT/WIDTH), round(650*HEIGHT/WIDTH))
    def do_get_preferred_height_for_width(self, width):
        height=round(min(WIDTH, width)*HEIGHT/WIDTH)
        return height,height

    def do_size_allocate(self, allocation):
        Gtk.Image.do_size_allocate(self, allocation)
        width=max(1,min(WIDTH,allocation.width))
        if width!=self.render_width:self.render(width)

    def show_state(self, held=(), seen=(), sticks=None, triggers=None, touches=None):
        snapshot=(tuple(sorted(held)),tuple(sorted(seen)),tuple(sticks) if sticks is not None else None,
                  tuple(triggers) if triggers is not None else None,
                  tuple((p['slot'],p['id'],p['x'],p['y']) for p in touches) if touches is not None else None)
        if snapshot==self.snapshot:return
        self.snapshot=snapshot
        self.svg=blueprint_svg(*snapshot,layer='live')
        self.render(self.render_width or 650)
        names=' + '.join(held) if held else _('nenhum')
        self.get_accessible().set_description(_('Pressionado agora: ')+names+_('. Abra Detalhes do teste para a lista e os valores dos eixos.'))

    def render(self,width):
        if self.background_width!=width:
            self.background=self.raster(blueprint_svg(layer='static'),width)
            self.background_width=width
        foreground=self.raster(self.svg,width)
        frame=self.background.copy()
        foreground.composite(frame,0,0,frame.get_width(),frame.get_height(),0,0,1,1,GdkPixbuf.InterpType.NEAREST,255)
        self.render_width=width
        self.set_from_pixbuf(frame)

    @staticmethod
    def raster(svg,width):
        loader=GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.set_size(width,round(width*HEIGHT/WIDTH))
        loader.write(svg.encode());loader.close()
        return loader.get_pixbuf()


class InputPanel(Gtk.Box):
    def __init__(self, edge=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.names = BUTTON_NAMES + (EDGE_BUTTON_NAMES if edge else ())
        self.seen = set()
        self.keys = {}
        self.latest = None
        self.latest_time = None
        self.waiting_message = ''
        self.pages = Gtk.Stack(); self.pages.set_hhomogeneous(False); self.pages.set_vhomogeneous(False)
        self.tabs = style(AdaptiveStackSwitcher(), 'input-tabs'); self.tabs.set_stack(self.pages)
        self.pack_start(self.tabs, False, False, 0)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.pages.add_titled(self.controls, 'controller', _('Controle'))
        self.analog = AnalogGuide()
        self.pages.add_titled(self.analog, 'analogs', _('Analógicos'))
        self.motion = MotionPanel()
        self.pages.add_titled(self.motion, 'motion', _('Movimento'))
        for tab in self.tabs.get_children():
            caption=tab.get_child()
            caption.set_line_wrap(True);caption.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            caption.set_max_width_chars(10)
        self.pack_start(self.pages, False, False, 0)
        self.status = label(_('Aguardando leitura…'), 'dialog-note', wrap=True)
        self.controls.pack_start(self.status, False, False, 0)
        self.blueprint = BlueprintImage()
        self.controls.pack_start(self.blueprint, False, False, 0)
        self.current = label(_('Nenhum botão pressionado'), 'input-current', wrap=True)
        self.current.get_accessible().set_name(_('Botões pressionados agora'))
        self.controls.pack_start(self.current, False, False, 0)
        legend=AdaptiveBox(spacing=8)
        for text,classes in [(_('● Pressionado'),('input-key','pressed')),
                             (_('✓ Já respondeu'),('input-key',)),
                             (_('Ainda não testado'),('input-key',))]:
            item=label(text,*classes,wrap=True)
            legend.pack_start(item,False,False,0)
        legend.set_tooltip_text(_('Ainda não testado não indica defeito.'))
        self.controls.pack_start(legend,False,False,0)
        footer=AdaptiveBox(spacing=12)
        self.count=label('','small',wrap=True)
        footer.pack_start(self.count,True,True,0)
        footer.pack_end(button(_('Recomeçar teste'),lambda b:self.reset(),'quiet'),False,False,0)
        self.controls.pack_start(footer,False,False,0)
        self.progress=Gtk.ProgressBar()
        self.progress.get_accessible().set_name(_('Progresso do teste de botões'))
        self.controls.pack_start(self.progress,False,False,0)
        self.touch_status = label(_('Touchpad · aguardando leitura…'), 'dialog-note', wrap=True)
        self.controls.pack_start(self.touch_status, False, False, 0)
        self.details = Gtk.Expander()
        self.details.set_label_widget(label(_('Detalhes do teste · eixos e checklist'),wrap=True))
        self.details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.details_box.set_margin_top(12)
        self.details.add(self.details_box)
        grid=Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_min_children_per_line(2);grid.set_max_children_per_line(5)
        grid.set_homogeneous(True);grid.set_column_spacing(6);grid.set_row_spacing(6)
        for index, name in enumerate(self.names):
            grid.add(self.key(name))
        self.details_box.pack_start(grid, False, False, 0)
        if edge:
            self.details_box.pack_start(label(_('Fn e botões traseiros do Edge aparecem neste checklist; '
                                             'não ficam visíveis na vista frontal.'), 'muted', 'small', wrap=True), False, False, 0)
        self.axes = {}
        analogs = AdaptiveBox(spacing=26)
        for title, axes in [(_('Analógico esquerdo'), ('LX', 'LY')),
                            (_('Analógico direito'), ('RX', 'RY')),
                            (_('Curso dos gatilhos'), ('L2', 'R2'))]:
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            column.pack_start(label(title, 'setting-title'), False, False, 0)
            for axis in axes:
                value = label(axis+'  —', 'small')
                bar = Gtk.ProgressBar()
                column.pack_start(value, False, False, 0)
                column.pack_start(bar, False, False, 0)
                self.axes[axis] = (value, bar)
            analogs.pack_start(column, True, True, 0)
        self.details_box.pack_start(analogs, False, False, 0)
        self.touch_values = label('', 'small', wrap=True)
        self.touch_values.get_accessible().set_name(_('Coordenadas dos toques no touchpad'))
        self.details_box.pack_start(self.touch_values, False, False, 0)
        self.controls.pack_start(self.details, False, False, 0)
        self.reset()
        self.pages.connect('notify::visible-child-name', self.page_changed)

    def page_changed(self, *args):
        page=self.pages.get_visible_child_name()
        if page!='analogs' and self.analog.session.phase in ('rest', 'ready', 'travel'):self.analog.interrupt()
        if page!='motion':self.motion.clear()
        if page=='analogs':self.analog.render()
        elif page=='motion':
            if self.latest is not None:self.motion.observe(self.latest.get('motion'),self.latest_time)
        else:
            if self.latest is not None: self.render_controller(self.latest)
            else: self.render_waiting()

    def key(self, name):
        widget = style(Gtk.Label(label=name), 'input-key')
        widget.set_size_request(72, 32)
        widget.get_accessible().set_name(name+_(' · ainda não observado'))
        self.keys[name] = widget
        return widget

    def reset(self):
        self.seen.clear()
        self.analog.session.reset()
        self.waiting(_('Aguardando a próxima leitura…'))
        self.current.set_text(_('Aguardando a próxima leitura…'))

    def render_touches(self, touches=None, invalid=0):
        if touches is None:
            message = _('Touchpad · aguardando leitura…')
        elif invalid:
            message = _('Touchpad · coordenada fora do intervalo; toque novamente.')
        elif not touches:
            message = _('Touchpad · deslize um ou dois dedos sobre a superfície.')
        else:
            message = _('Touchpad · {0} de 2 pontos ativos').format(len(touches))
        self.touch_status.set_text(message)
        self.touch_values.set_text('\n'.join(_('Ponto {0} · X {1} / 1919 · Y {2} / 1079').format(
            p['slot']+1,p['x'],p['y']) for p in touches or ()) or _('Touchpad · sem coordenadas atuais'))

    def render_buttons(self, held):
        for name, widget in self.keys.items():
            widget.get_style_context().remove_class('pressed')
            if name in held:
                style(widget, 'pressed')
            widget.set_text(('● ' if name in held else '✓ ' if name in self.seen else '')+name)
            widget.get_accessible().set_name(name+(_(' · pressionado') if name in held else
                                                   _(' · já respondeu') if name in self.seen else _(' · ainda não observado')))
        self.count.set_text(_('{0} de {1} botões observados').format(len(self.seen.intersection(self.names)), len(self.names)))
        self.progress.set_fraction(len(self.seen.intersection(self.names))/len(self.names))
        self.progress.get_accessible().set_description(self.count.get_text())

    def update(self, state, timestamp=None):
        timestamp=time.monotonic() if timestamp is None else timestamp
        self.analog.observe(state['sticks'], timestamp)
        self.seen.update(state.get('observed', state['buttons']))
        self.seen.update(state['buttons'])
        self.latest = state
        self.latest_time = timestamp
        # Keep receiving/checking inputs across tabs, but rasterize only the
        # visible view. Returning to the blueprint displays the newest frame.
        # Gtk.Stack has no visible child until show_all() on a new panel.
        if self.pages.get_visible_child_name() in (None, 'controller'): self.render_controller(state)
        elif self.pages.get_visible_child_name()=='motion':self.motion.observe(state.get('motion'),timestamp)

    def render_controller(self, state):
        self.render_buttons(state['buttons'])
        self.blueprint.show_state(state['buttons'],self.seen,state['sticks'],state['triggers'],state.get('touches'))
        self.render_touches(state.get('touches'),state.get('touch_invalid',0))
        self.current.set_text(_('Pressionado agora: ')+ ' + '.join(name for name in self.names if name in state['buttons'])
                              if state['buttons'] else _('Nenhum botão pressionado'))
        for axis, raw in zip(('LX', 'LY', 'RX', 'RY', 'L2', 'R2'), state['sticks']+state['triggers']):
            value, bar = self.axes[axis]
            percentage = raw / 255 * 100 if axis in ('L2', 'R2') else (raw - 127.5) / 127.5 * 100
            value.set_text(f'{axis}  {percentage:+.0f}%' if axis not in ('L2', 'R2') else f'{axis}  {percentage:.0f}%')
            bar.set_fraction(raw / 255)
        self.status.set_text(_('Recebendo entradas ao vivo · mova os analógicos e pressione os gatilhos até o fim.'))

    def waiting(self, message):
        self.latest = None
        self.latest_time = None
        self.waiting_message = message
        self.analog.interrupt()
        self.motion.clear()
        if self.pages.get_visible_child_name() in (None, 'controller'): self.render_waiting()

    def render_waiting(self):
        self.status.set_text(self.waiting_message)
        self.render_buttons([])
        self.blueprint.show_state(seen=self.seen)
        self.render_touches()
        self.current.set_text(_('Sem leitura atual · desenho em repouso'))
        for axis, (value, bar) in self.axes.items():
            value.set_text(axis+'  —')
            bar.set_fraction(0)
