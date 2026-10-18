# SPDX-License-Identifier: GPL-3.0-only
"""Run in a graphical session. Synthetic controllers only; no USB access."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from ui import Dashboard,ASSETS,style,AppearanceGallery,ContentClamp,EffectsEditor
from presentation import ControllerState
from i18n import set_language
set_language('pt-BR')

class Owner:
    busy=False
    def __init__(self):self.actions=[]
    def request_mode(self,*args):self.actions.append(args)
    def card_action(self,*args):self.actions.append(args)
    def profiles_dialog(self):pass
    def install(self):pass
    def about_dialog(self):pass

def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)

from theme import install_theme
install_theme()
owner=Owner();root=style(Gtk.Window(title='Uplugo — teste de interface'),'dualsense')
root.set_default_size(1040,820)
dashboard=Dashboard(owner);root.add(ContentClamp(dashboard))
model=ControllerState('hid:example','Controle de demonstração',requested='proxy',effective='proxy',confirmed=True,fresh=True)
dashboard.update([model],True);root.show_all();pump()
try:
    assert dashboard.heading.get_mapped() and dashboard.guide.get_mapped(), 'Connected controllers must keep the heading and mode guide visible'
    card=dashboard.items[model.identity]
    card.customize.grab_focus();pump()
    model.reading={'capacity':65,'status':'Charging','time':'12:00'}
    dashboard.update([model],True)
    assert dashboard.items[model.identity] is card
    assert card.spinner.get_property('active')
    assert root.get_focus() is card.customize
    card.choose_mode(None,'charge');pump()
    assert not owner.actions, 'Selecting a draft must not send hardware commands'
    assert card.apply.get_sensitive()
    card.apply_choice(None);pump()
    assert owner.actions==[('hid:example','charge')]
    card.choose_mode(None,'charge');pump()
    model.connected=False;model.fresh=False
    dashboard.update([model],True)
    assert not card.apply.get_sensitive()
    assert not card.customize.get_sensitive()
    assert not card.locate.get_sensitive()
    assert not card.test_input.get_sensitive()
    assert not card.spinner.get_property('active')
    card.apply_choice(None)
    assert len(owner.actions)==1
    card.popover.popdown()
    dashboard.update([model],False)
    assert dashboard.setup.get_visible() and dashboard.unlock.get_sensitive()
    owner.busy=True;dashboard.update([model],False)
    assert not dashboard.unlock.get_sensitive()
    owner.busy=False;dashboard.update([model],False)
    assert dashboard.unlock.get_sensitive()
    dashboard.update([],True)
    assert dashboard.stack.get_visible_child_name()=='empty'
    assert not dashboard.heading.get_visible() and dashboard.empty_guide.get_visible()
    gallery=AppearanceGallery('black',local_images=False)
    gallery.tiles['chroma-teal'][0].set_active(True)
    gallery.search.set_text('ANIVERSARIO');gallery.filter_changed()
    assert gallery.selected=='chroma-teal', 'Filtering must preserve the draft selection'
    assert gallery.includes(gallery.tiles['anniversary-30'][3])
    assert not gallery.includes(gallery.tiles['black'][3])
    gallery.group.set_active_id('DualSense Edge')
    assert gallery.includes(gallery.tiles['edge-anniversary-30'][3])
    assert not gallery.includes(gallery.tiles['anniversary-30'][3])
    assert len(owner.actions)==1, 'Appearance selection must never send hardware commands'
    gallery.destroy()
    editor=EffectsEditor({'rgb':[0,120,255],'vibration':'game','triggers':'game'})
    assert not editor.dirty
    editor.pick((240,66,66))
    assert editor.dirty and editor.values()['rgb']==[240,66,66]
    assert editor.hex_label.get_text()=='#F04242'
    editor.triggers.set_active_id('firm')
    assert 'firme' in editor.trigger_note.get_text()
    assert len(owner.actions)==1, 'Effect drafts must not send hardware commands'
    editor.destroy()
    # Device navigation is local-only, including keyboard and repeated readings.
    from tests.accessibility_smoke import key
    model.connected=True;model.fresh=True
    other=ControllerState('hid:second','Segundo controle',appearance='white',requested='charge',effective='charge',confirmed=True,fresh=True,reading={'capacity':100,'status':'Full'})
    dashboard.update([model,other],True);pump()
    before=list(owner.actions)
    dashboard.selectors[other.identity].clicked();pump()
    assert dashboard.selected==other.identity and dashboard.cards.get_visible_child() is dashboard.items[other.identity]
    assert dashboard.selectors[other.identity].get_active() and not dashboard.selectors[model.identity].get_active()
    dashboard.selectors[other.identity].clicked();pump()
    assert dashboard.selectors[other.identity].get_active(), 'Selected device cannot deselect itself'
    dashboard.selectors[other.identity].grab_focus();key(root,Gdk.KEY_Left)
    assert dashboard.selected==model.identity
    assert root.get_focus() is dashboard.selectors[model.identity]
    card=dashboard.items[model.identity]
    card.choose_mode(None,'charge');pump()
    assert card.popover.get_visible()
    dashboard.select_controller(other.identity);pump()
    assert not card.popover.get_visible(), 'Changing devices must dismiss the old draft'
    model.error='USB test error';dashboard.update([other,model],True);pump()
    assert dashboard.selected==other.identity, 'Polling order must not change the selected controller'
    assert 'Precisa de atenção' in dashboard.selectors[model.identity].status.get_text()
    assert dashboard.items[other.identity].customize.get_visible() and not dashboard.items[other.identity].customize.get_sensitive()
    dashboard.update([model],True);pump()
    assert dashboard.selected==model.identity and len(dashboard.selectors)==1
    assert owner.actions==before, 'Navigation and polling must never send controller commands'
    print('GUI OK: focus, draft/apply, unplug guard, stale animation, setup, empty state; gallery search, accents, groups, draft selection without USB commands.')
finally:
    root.destroy();pump()
