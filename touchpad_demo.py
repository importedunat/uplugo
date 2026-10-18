# SPDX-License-Identifier: GPL-3.0-only
"""Interactive explanation only: SVG rendering, no input-device access or writes."""
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GdkPixbuf
from i18n import _


class TouchpadDemo(Gtk.EventBox):
    def __init__(self):
        super().__init__()
        self.choice='system';self.position=(.5,.5);self.dragging=False;self.width=0;self.render_signature=None
        self.image=Gtk.Image();self.add(self.image);self.set_visible_window(False)
        self.set_can_focus(True);self.set_valign(Gtk.Align.START)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect('button-press-event',self.press);self.connect('button-release-event',self.release)
        self.connect('motion-notify-event',self.motion);self.connect('key-press-event',self.key)
        self.connect('focus-out-event',self.unfocus);self.connect('focus-in-event',lambda *a:self.render())
        self.connect('style-updated',lambda *a:self.render())
        self.get_accessible().set_name(_('Demonstração do touchpad. Arraste o ponto ou use as setas.'))
        self.render()

    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_get_preferred_width(self):return 280,560
    def do_get_preferred_width_for_height(self,height):return self.do_get_preferred_width()
    def do_get_preferred_height(self):return 85,170
    def do_get_preferred_height_for_width(self,width):
        height=max(1,round(width*170/560));return height,height

    def do_size_allocate(self,allocation):
        Gtk.EventBox.do_size_allocate(self,allocation)
        if self.width!=allocation.width:self.width=allocation.width;self.render()

    def set_choice(self,choice):
        self.choice=choice;self.render()

    @property
    def cursor(self):return self.position if self.choice=='system' else (.5,.5)

    def move(self,x,y):
        self.position=(min(1,max(0,x)),min(1,max(0,y)));self.render()

    def point(self,event):
        scale=560/max(1,self.get_allocated_width())
        return (event.x*scale-32)/180,(event.y*scale-32)/100

    def press(self,widget,event):
        if event.button!=1:return False
        x,y=self.point(event)
        if 0<=x<=1 and 0<=y<=1:
            self.grab_focus();self.dragging=True;self.move(x,y);return True
        return False

    def motion(self,widget,event):
        if self.dragging and event.state&Gdk.ModifierType.BUTTON1_MASK:self.move(*self.point(event));return True
        self.dragging=False
        return False

    def release(self,*args):self.dragging=False;return False

    def unfocus(self,*args):self.dragging=False;self.render();return False

    def key(self,widget,event):
        delta={Gdk.KEY_Left:(-.1,0),Gdk.KEY_Right:(.1,0),Gdk.KEY_Up:(0,-.1),Gdk.KEY_Down:(0,.1)}.get(event.keyval)
        if delta:self.move(self.position[0]+delta[0],self.position[1]+delta[1]);return True
        return False

    def render(self):
        if not hasattr(self,'image'):return
        context=self.get_style_context();fg=context.get_color(Gtk.StateFlags.NORMAL)
        ink=f'rgb({round(fg.red*255)},{round(fg.green*255)},{round(fg.blue*255)})'
        found,color=context.lookup_color('theme_selected_bg_color');color=color if found else fg
        accent=f'rgb({round(color.red*255)},{round(color.green*255)},{round(color.blue*255)})'
        signature=(self.width,self.choice,self.position,self.has_focus(),ink,accent)
        if self.render_signature==signature:return
        self.render_signature=signature
        x,y=self.position;cx,cy=self.cursor
        transfer=('<path d="M254 82h48m-9-8 9 8-9 8"/>' if self.choice=='system' else
                  '<rect x="269" y="77" width="22" height="20" rx="3"/><path d="M274 77v-8a6 6 0 0 1 12 0v8"/>')
        focus=f'<rect x="14" y="14" width="222" height="136" rx="24" fill="none" stroke="{accent}" stroke-width="3"/>' if self.has_focus() else ''
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="560" height="170" viewBox="0 0 560 170">
        <g stroke="{ink}" stroke-width="2" fill="none"><path d="M40 24Q125 12 210 24Q220 26 220 40L214 124Q213 140 198 140H52Q37 140 36 124L30 40Q30 28 40 24Z"/>
        <rect x="340" y="22" width="202" height="120" rx="10"/><path d="M415 152h52"/>{transfer}</g>
        <circle cx="{32+x*180:.2f}" cy="{32+y*100:.2f}" r="13" fill="{accent}"/>
        <path transform="translate({352+cx*150:.2f},{32+cy*75:.2f})" d="M0 0v29l8-8 8 14 5-3-8-13 12-2Z" fill="{ink}"/>{focus}</svg>'''
        width=max(1,self.width or 560)
        loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.set_size(width,max(1,round(width*170/560)))
        loader.write(svg.encode());loader.close();self.image.set_from_pixbuf(loader.get_pixbuf())
        self.get_accessible().set_description(_('Prévia: o cursor acompanha o gesto.') if self.choice=='system' else _('Prévia: o cursor fica parado. O clique para jogos não é bloqueado.'))
