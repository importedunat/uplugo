# SPDX-License-Identifier: GPL-3.0-only
"""Observed battery samples only. No forecasts, charging-rate inference or writes."""
from gi.repository import Gtk,GdkPixbuf
from i18n import _
import time


class BatteryPlot(Gtk.Image):
    def __init__(self):
        super().__init__()
        self.samples=();self.fresh=False;self.width=0;self.signature=None
        self.get_accessible().set_name(_('Histórico visual da porcentagem recebida'))
        self.connect('style-updated',lambda *args:self.render())
        self.render()

    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_get_preferred_width(self):return 280,560
    def do_get_preferred_width_for_height(self,height):return self.do_get_preferred_width()
    def do_get_preferred_height(self):return 130,170
    def do_get_preferred_height_for_width(self,width):return 170,170

    def do_size_allocate(self,allocation):
        Gtk.Image.do_size_allocate(self,allocation)
        if self.width!=allocation.width:self.width=allocation.width;self.render()

    def update(self,samples,fresh):
        self.samples=tuple((s['at'],s['capacity']) for s in samples)
        self.fresh=fresh;self.render()

    def render(self):
        if not hasattr(self,'samples'):return
        width=max(280,self.width or 560);height=170
        context=self.get_style_context();c=context.get_color(Gtk.StateFlags.NORMAL)
        ink=f'rgb({round(c.red*255)},{round(c.green*255)},{round(c.blue*255)})'
        found,accent=context.lookup_color('theme_selected_bg_color');accent=accent if found and self.fresh else c
        color=f'rgb({round(accent.red*255)},{round(accent.green*255)},{round(accent.blue*255)})'
        size=max(11,self.get_pango_context().get_font_description().get_size()/1024*1.1)
        left=round(size*3.7);bottom=height-2.8*size;top=size*1.5
        key=(width,self.samples,self.fresh,ink,color,size)
        if key==self.signature:return
        self.signature=key
        marks=[]
        for value in (0,50,100):
            y=bottom-value/100*(bottom-top)
            marks.append(f'<path d="M{left} {y}H{width-14}" stroke="{ink}" opacity=".18"/>')
            marks.append(f'<text x="2" y="{y+4}" fill="{ink}" font-size="{size:.1f}">{value}%</text>')
        if self.samples:
            start,end=self.samples[0][0],self.samples[-1][0]
            def point(at,capacity):return left+(at-start)/max(1,end-start)*(width-left-14),bottom-capacity/100*(bottom-top)
            dots=[point(*sample) for sample in self.samples]
            # A stepped line represents the last reported percentage, never an
            # inferred smooth charging curve. A one-sample session is a dot.
            if len(dots)>1:
                path=f'M{dots[0][0]:.2f} {dots[0][1]:.2f}'
                for x,y in dots[1:]:path+=f'H{x:.2f}V{y:.2f}'
                marks.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>')
            for x,y in (dots[0],dots[-1]):marks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="{color}"/>')
            for x,at,anchor in ((left,start,'start'),(width-14,end,'end')):
                marks.append(f'<text x="{x}" y="{height-size*.4:.1f}" text-anchor="{anchor}" fill="{ink}" font-size="{size:.1f}">{time.strftime("%H:%M",time.localtime(at))}</text>')
            description=_('{0} leituras · de {1}% para {2}%.').format(len(self.samples),self.samples[0][1],self.samples[-1][1])
            if not self.fresh:description+=' '+_('Leitura anterior')
        else:
            description=_('As leituras aparecerão aqui.');marks.append(f'<text x="{width/2}" y="82" fill="{ink}" text-anchor="middle" font-size="{size*2:.1f}">—</text>')
        self.get_accessible().set_description(description)
        self.svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif">'+''.join(marks)+'</svg>'
        loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.write(self.svg.encode());loader.close();self.set_from_pixbuf(loader.get_pixbuf())
