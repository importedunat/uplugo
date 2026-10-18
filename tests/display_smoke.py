# SPDX-License-Identifier: GPL-3.0-only
"""Real GTK sizing, desktop font, high contrast and focus with fake devices.

Use a private Xvfb. No USB, persistent settings or screen-reader certification.
"""
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from theme import install_theme
from ui import Dashboard,ContentClamp,style
from presentation import ControllerState,AccessSetup
from i18n import set_language,_
from tests import accessibility_smoke as keyboard
from tests.accessibility_smoke import key


def pump(delay=.12):
    until=time.monotonic()+delay
    while time.monotonic()<until:
        deadline=time.monotonic()+2
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
            assert time.monotonic()<deadline,'GTK layout did not settle'
        time.sleep(.005)
keyboard.pump=pump


class Owner:
    preview=False
    busy=False
    def __init__(self):self.actions=[]
    def card_action(self,*args):self.actions.append(args)
    def request_mode(self,*args):self.actions.append(args)
    def profiles_dialog(self):pass


def inside(widget,root):
    x,_y=widget.translate_coordinates(root,0,0)
    assert x>=0 and x+widget.get_allocated_width()<=root.get_allocated_width(),(type(widget).__name__,x,widget.get_allocated_width(),root.get_size())


def run(code,theme_name,font,output):
    print('DISPLAY CASE:',code,theme_name,font,flush=True)
    settings=Gtk.Settings.get_default();settings.set_property('gtk-theme-name',theme_name)
    settings.set_property('gtk-font-name',font);set_language(code)
    owner=Owner();root=style(Gtk.Window(),'dualsense');root.set_decorated(False)
    dashboard=Dashboard(owner);root.add(ContentClamp(dashboard))
    models=[ControllerState('demo:'+str(i),_('Controle de teste {0}').format(i+1),appearance=('black','white')[i],
                            requested=mode,effective=mode,confirmed=True,fresh=True,
                            reading={'capacity':55,'status':'Charging'}) for i,mode in enumerate(('proxy','charge'))]
    dashboard.update(models,True);root.set_default_size(1040,880);root.show_all();root.get_window().focus(Gdk.CURRENT_TIME);pump()
    card=dashboard.items['demo:0'];control=card.mode_buttons['play']
    control.grab_focus();pump()
    # Same objects survive wide -> narrow -> wide reflow and identical readings.
    screen=Gdk.Display.get_default().get_primary_monitor().get_geometry()
    for width,height in ((1040,880),(640,464),(480,640),(1040,880)):
        width=min(width,screen.width);height=min(height,screen.height-32)
        print('RESIZE:',width,height,flush=True)
        root.resize(width,height);pump();dashboard.update(models,True);pump()
        assert root.get_size()==(width,height),(code,theme_name,font,width,height,root.get_size())
        assert dashboard.items['demo:0'] is card and root.get_focus() is control
        for other in (card,):
            for widget in [other,other.portrait,other.name,other.locate,*other.mode_buttons.values(),other.test_input]:inside(widget,root)
        inside(dashboard.preferences,root);inside(dashboard.footer_note,root)
        actions=(dashboard.compatibility,dashboard.help,dashboard.preferences)
        for action in actions:inside(action,root)
        for left,right in zip(actions,actions[1:]):
            lx,ly=left.translate_coordinates(root,0,0);rx,ry=right.translate_coordinates(root,0,0)
            assert lx+left.get_allocated_width()<=rx or ly+left.get_allocated_height()<=ry,(code,font,'Header actions overlap')
    # Focusing the final action scrolls the whole page, including both devices.
    dashboard.select_controller('demo:1');pump()
    last=dashboard.items['demo:1'].test_input;last.grab_focus();pump()
    x,y=last.translate_coordinates(dashboard.scroll,0,0)
    assert y>=0 and y+last.get_allocated_height()<=dashboard.scroll.get_allocated_height(),(y,last.get_allocated_height(),dashboard.scroll.get_allocated_height())
    dashboard.select_controller('demo:0');pump()
    control.grab_focus();pump();key(root,Gdk.KEY_space)
    assert card.popover.get_visible() and not owner.actions
    key(root,Gdk.KEY_Escape);assert not card.popover.get_visible() and not owner.actions
    # Preferences remain scrollable and keyboard-dismissable on a short screen.
    dashboard.preferences.grab_focus();key(root,Gdk.KEY_space)
    popup=dashboard.preferences.get_popover()
    assert popup.get_visible()
    assert popup.get_allocated_height()<=screen.height and popup.get_allocated_width()<=screen.width,(popup.get_allocation(),screen)
    # The nested preference is inactive without protection, but its value
    # survives turning protection off and on. No synthetic child changes.
    changed=[]
    dashboard.allow_play.set_active(True)
    dashboard.allow_play.connect('toggled',lambda w:changed.append(w.get_active()))
    assert not dashboard.allow_play.get_sensitive()
    dashboard.guard.set_active(True);assert dashboard.allow_play.get_sensitive()
    dashboard.guard.set_active(False)
    assert dashboard.allow_play.get_active() and not changed
    assert not dashboard.maintenance.get_expanded()
    for expander in (dashboard.protection_help,dashboard.maintenance):
        expander.set_expanded(True);pump()
        assert popup.get_allocated_height()<=screen.height
        assert popup.get_allocated_width()<=screen.width
    if output and code=='pt-BR' and theme_name=='Adwaita' and font=='Sans 10':
        output.mkdir(parents=True,exist_ok=True)
        width,height=popup.get_window().get_width(),popup.get_window().get_height()
        Gdk.pixbuf_get_from_window(popup.get_window(),0,0,width,height).savev(str(output/'preferences-expanded.png'),'png',[],[])
    dashboard.protection_help.set_expanded(False);dashboard.maintenance.set_expanded(False)
    # Destination actions close the popover before opening the next surface.
    opened=[]
    owner.photos_dialog=lambda:opened.append(popup.get_visible())
    dashboard.preference_actions['photos_dialog'].clicked();pump()
    assert opened==[False] and not owner.actions
    dashboard.preferences.grab_focus();key(root,Gdk.KEY_space)
    assert popup.get_visible()
    key(root,Gdk.KEY_Escape);assert not popup.get_visible() and not owner.actions
    theme=install_theme();assert theme.high_contrast==(theme_name=='HighContrast')
    current_color=card.description.get_style_context().get_color(Gtk.StateFlags.NORMAL)
    if theme.high_contrast:
        # A light high-contrast theme must not keep the app's pale gray text.
        assert max(current_color.red,current_color.green,current_color.blue)<.4,current_color
    font_size=card.description.get_pango_context().get_font_description().get_size()
    text_height=card.capacity.get_preferred_height()[1]
    # The update notice must wrap on a narrow screen and remain keyboard
    # reachable without changing the cards or initiating an update.
    from types import SimpleNamespace
    owner.support_revision=SimpleNamespace(state=lambda:'different',native=False)
    owner.access_setup=AccessSetup()
    root.resize(min(480,screen.width),min(640,screen.height-32));pump()
    dashboard.update(models,True);pump()
    assert dashboard.support_update.get_visible()
    inside(dashboard.support_update_text,root);inside(dashboard.support_update_button,root)
    dashboard.support_update_button.grab_focus();pump()
    x,y=dashboard.support_update_button.translate_coordinates(dashboard.scroll,0,0)
    assert y>=0 and y+dashboard.support_update_button.get_allocated_height()<=dashboard.scroll.get_allocated_height()
    if output and code=='pt-BR' and theme_name=='Adwaita' and font=='Sans 10':
        output.mkdir(parents=True,exist_ok=True)
        width,height=root.get_size()
        Gdk.pixbuf_get_from_window(root.get_window(),0,0,width,height).savev(str(output/'usb-support-update.png'),'png',[],[])
    owner.support_revision=None
    root.resize(min(1040,screen.width),min(880,screen.height-32));pump()
    # Setup/empty/error pages share the same bounded scroll region.
    for phase in ('busy','failed','cancelled'):
        owner.access_setup=AccessSetup(phase,'Example error '*20)
        dashboard.update([],False);pump()
        assert root.get_size()[0]<=screen.width and root.get_size()[1]<=screen.height
        inside(dashboard.unlock,root)
    dashboard.update(models,True);dashboard.count.set_text(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'));dashboard.count.show()
    dashboard.scroll.get_vadjustment().set_value(0);pump()
    if output and code=='pt-BR':
        output.mkdir(parents=True,exist_ok=True)
        width,height=root.get_size()
        Gdk.pixbuf_get_from_window(root.get_window(),0,0,width,height).savev(str(output/f'{theme_name}-{font.replace(" ","-")}-{root.get_scale_factor()}x.png'),'png',[],[])
    root.destroy();pump();assert not owner.actions
    return font_size,text_height


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    failures=[];original_hook=sys.excepthook
    def record(*args):failures.append(args);original_hook(*args)
    sys.excepthook=record
    settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False)
    theme=install_theme()
    try:
        for code in ('pt-BR','en','es'):
            for name in ('Adwaita','HighContrast'):
                small=run(code,name,'Sans 10',args.output)
                large=run(code,name,'Sans 16',args.output)
                assert large[0]>small[0]*1.4 and large[1]>small[1]*1.4,(small,large)
        # GNOME large-text settings may change DPI rather than the font name.
        original_dpi=settings.get_property('gtk-xft-dpi')
        settings.set_property('gtk-xft-dpi',96*1024)
        normal=run('pt-BR','Adwaita','Sans 10',None)
        settings.set_property('gtk-xft-dpi',144*1024)
        enlarged=run('pt-BR','Adwaita','Sans 10',None)
        assert enlarged[1]>normal[1]*1.3,(normal,enlarged)
        settings.set_property('gtk-xft-dpi',original_dpi)
        assert not failures,'GTK callbacks raised exceptions'
    finally:sys.excepthook=original_hook
    print('DISPLAY OK: three languages; desktop font growth, live high-contrast switch, 480/640/1040 widths, keyboard focus and page scroll, bounded preferences and setup; no commands.')


if __name__=='__main__':main()
