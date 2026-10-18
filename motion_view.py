# SPDX-License-Identifier: GPL-3.0-only
"""Live gyro/accelerometer readings with units, local traces and explicit limits."""
import math
from gi.repository import Gtk,GdkPixbuf
from i18n import _
from ui import label,button,style
from motion_trace import MotionTrace


class MotionPlot(Gtk.Image):
    def __init__(self,trace,channel):
        super().__init__();self.trace=trace;self.channel=channel
        self.width=0;self.signature=None
        self.get_accessible().set_name(_('Histórico local de movimento · últimos 10 segundos'))

    def do_get_preferred_width(self):return (260,650)
    def do_get_preferred_height(self):return (110,110)

    def do_size_allocate(self,allocation):
        Gtk.Image.do_size_allocate(self,allocation)
        width=max(1,allocation.width)
        if width!=self.width:self.width=width;self.render()

    def extent(self):
        return max([1 if self.channel==2 else 30]+[abs(v) for row in self.trace.samples for v in (row[self.channel] or ())])

    def render(self):
        width,height=self.width or 650,110
        color=self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        foreground='#{:02x}{:02x}{:02x}'.format(*(round(v*255) for v in (color.red,color.green,color.blue)))
        samples=self.trace.samples
        extent=self.extent()
        end=samples[-1][0] if samples else 0
        colors=('#59a6ff','#d9912e','#ad85f2')
        high_contrast='highcontrast' in str(Gtk.Settings.get_default().get_property('gtk-theme-name')).lower()
        signature=(tuple(samples),width,foreground,high_contrast)
        if signature==self.signature:return
        self.signature=signature
        parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="110">',
               f'<path d="M8 55H{width-8}" stroke="{foreground}" opacity=".3"/>']
        for axis,rgb in enumerate(colors):
            commands=[];started=False
            for row in samples:
                if row[self.channel] is None:
                    started=False;continue
                x=8+(width-16)*max(0,1-(end-row[0])/10)
                y=height/2-row[self.channel][axis]/extent*(height/2-8)
                commands.append(('L' if started else 'M')+f'{x:.2f} {y:.2f}');started=True
            dash=('none','6 3','2 3')[axis]
            parts.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{foreground if high_contrast else rgb}" stroke-width="2" stroke-dasharray="{dash}"/>')
        parts.append('</svg>')
        loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.write(''.join(parts).encode());loader.close()
        self.set_from_pixbuf(loader.get_pixbuf())


class MotionPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.trace=MotionTrace();self.latest=None
        self.pack_start(label(_('Incline e gire o controle devagar. Compare as leituras ao mover e ao deixar parado.'),wrap=True),False,False,0)
        self.status=label('','dialog-note',wrap=True);self.pack_start(self.status,False,False,0)
        self.values=[];self.plots=[];self.scales=[]
        for channel,title in ((1,_('Giroscópio · velocidade de rotação')),(2,_('Acelerômetro · movimento e gravidade'))):
            self.pack_start(label(title,'setting-title',wrap=True),False,False,0)
            value=label('',wrap=True);value.set_selectable(True);self.values.append(value)
            self.pack_start(value,False,False,0)
            plot=MotionPlot(self.trace,channel);self.plots.append(plot);self.pack_start(plot,False,False,0)
            scale=label('','small','muted',wrap=True);self.scales.append(scale);self.pack_start(scale,False,False,0)
        self.gravity=label('','muted',wrap=True);self.pack_start(self.gravity,False,False,0)
        self.pack_start(label(_('X = linha contínua · Y = tracejada · Z = pontilhada. A escala de cada gráfico se ajusta às leituras.'),'small','muted',wrap=True),False,False,0)
        self.pack_start(label(_('°/s mede a rapidez da rotação, não o ângulo. g mede aceleração, incluindo a gravidade: parado, a soma vetorial costuma ficar perto de 1 g. Pequenas oscilações não comprovam defeito.'),'small','muted',wrap=True),False,False,0)
        self.detail=Gtk.Expander(label=_('Como estes dados são usados'))
        self.detail.add(label(_('As unidades usam a calibração de fábrica lida do controle. Nenhuma calibração é gravada. O gráfico guarda até 10 segundos só nesta aba; fechar, trocar de aba ou perder a leitura limpa esse histórico. Isso não mede posição, latência do jogo nem compatibilidade com mira por movimento.'),'small','muted',wrap=True))
        self.pack_start(self.detail,False,False,0)
        self.clear_button=button(_('Limpar gráfico'),lambda b:self.clear(),'quiet');self.pack_start(self.clear_button,False,False,0)
        self.render()

    def clear(self):
        self.trace.clear();self.latest=None;self.render()

    def observe(self,motion,now):
        self.latest=motion;self.trace.observe(motion,now);self.render()

    def render(self):
        if self.trace.stalled:text=_('O relógio do sensor parou de atualizar. Aguardando uma leitura nova…')
        elif self.trace.current is None:text=_('Aguardando dados atuais dos sensores…')
        elif any(v is None for v in self.trace.current):text=_('Calibração de fábrica indisponível para um ou mais sensores. Valores sem unidade não são mostrados como °/s ou g.')
        else:text=_('Leitura ao vivo · unidades calculadas com a calibração de fábrica')
        self.status.set_text(text)
        values=self.trace.current or (None,None)
        for widget,vector,unit in zip(self.values,values,('°/s','g')):
            widget.set_text('  ·  '.join(f'{axis} {value:+.2f} {unit}' for axis,value in zip('XYZ',vector)) if vector is not None else _('Sem leitura calibrada'))
        acceleration=values[1]
        self.gravity.set_text(_('Aceleração total observada: {0:.2f} g').format(math.sqrt(sum(v*v for v in acceleration))) if acceleration is not None else '')
        self.clear_button.set_sensitive(bool(self.trace.samples))
        for plot,scale,unit in zip(self.plots,self.scales,('°/s','g')):
            scale.set_text(_('Escala vertical: ±{0:.2f} {1} · janela de 10 s').format(plot.extent(),unit))
            plot.render()
