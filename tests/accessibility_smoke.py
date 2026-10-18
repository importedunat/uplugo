# SPDX-License-Identifier: GPL-3.0-only
"""GTK keyboard and local ATK semantics, using synthetic controllers only.

Run under a private Xvfb. This is not an Orca / AT-SPI end-to-end test.
"""
import argparse
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,Atk
from ui import ControllerCard,EffectsEditor,AppearanceGallery,Dashboard,ASSETS,style,label
from presentation import ControllerState
from i18n import _,set_language


def pump(delay=0):
    until=time.monotonic()+delay
    while True:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        if time.monotonic()>=until:return
        time.sleep(.005)


def key(root,value,shift=False):
    _found,entries=Gdk.Keymap.get_for_display(Gdk.Display.get_default()).get_entries_for_keyval(value)
    for kind in (Gdk.EventType.KEY_PRESS,Gdk.EventType.KEY_RELEASE):
        event=Gdk.Event.new(kind);event.window=root.get_window();event.keyval=value
        event.set_device(Gdk.Display.get_default().get_default_seat().get_keyboard())
        event.state=Gdk.ModifierType.SHIFT_MASK if shift else Gdk.ModifierType(0)
        event.send_event=True;event.time=Gdk.CURRENT_TIME
        event.hardware_keycode=entries[0].keycode;event.group=entries[0].group
        root.event(event)
    pump(.3)


def related(widget,relation):
    rel=widget.get_accessible().ref_relation_set().get_relation_by_type(relation)
    return list(rel.get_target()) if rel else []


def run(code,output):
    set_language(code);commands=[]
    root=style(Gtk.Window(),'dualsense')
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    root.add(box)
    models=[ControllerState('hid:demo:'+suffix,'Meu controle',requested='proxy',effective='proxy',confirmed=True,fresh=True,
                            reading={'capacity':55,'status':'Charging','time':'12:00'}) for suffix in ('1234','5678')]
    cards=[ControllerCard(model,lambda *a:commands.append(a),lambda *a:commands.append(a)) for model in models]
    for card in cards:box.pack_start(card,False,False,0)
    root.show_all();root.get_window().focus(Gdk.CURRENT_TIME);pump()
    first,second=cards;state=models[0]
    for attr in ('locate','test_input','customize','more','appearance_button','bar'):
        a=getattr(first,attr).get_accessible();b=getattr(second,attr).get_accessible()
        assert a.get_name()!=b.get_name() and '1234' in a.get_name() and '5678' in b.get_name(),attr
    assert first.get_accessible().get_role()==Atk.Role.PANEL
    assert first.bar.get_accessible().get_description()==_('Carregando')
    for item,title in first.menu_actions:assert item.get_accessible().get_name().startswith(title+' — ')
    # Polling the same state must not repeat accessible-name notifications.
    notices=[]
    for widget in (first.locate,first.mode_buttons['proxy'],first.bar):
        widget.get_accessible().connect('notify::accessible-name',lambda *a:notices.append(a))
    first.test_input.grab_focus()
    for _iteration in range(20):first.update(state)
    assert not notices,'Repeated polling changed accessible names'
    assert root.get_focus() is first.test_input
    state.name='Novo nome';first.update(state)
    assert 'Novo nome' in first.locate.get_accessible().get_name()
    state.fresh=False;first.update(state)
    assert _(' · modo ativo') not in first.mode_buttons['proxy'].get_accessible().get_name()
    assert first.bar.get_accessible().get_description().startswith(_('Última leitura · '))
    state.reading=None;first.update(state);root.show_all();pump()
    assert not first.bar.get_visible(),'Unknown capacity must not be exposed as 0%'
    state.fresh=True;first.update(state)
    anchor=first.mode_buttons['charge'];anchor.grab_focus();key(root,Gdk.KEY_space)
    assert first.popover.get_visible() and root.get_focus() is first.cancel
    assert not commands,'Opening a mode choice sent a command'
    key(root,Gdk.KEY_Tab);assert root.get_focus() is first.apply
    key(root,Gdk.KEY_ISO_Left_Tab,shift=True);assert root.get_focus() is first.cancel
    key(root,Gdk.KEY_Escape)
    assert not first.popover.get_visible() and root.get_focus() is anchor and not commands
    key(root,Gdk.KEY_space);key(root,Gdk.KEY_Tab);key(root,Gdk.KEY_space)
    assert commands==[(state.identity,'charge')]
    anchor.grab_focus();key(root,Gdk.KEY_space)
    assert first.popover.get_visible(),('Reopening mode choice',root.get_focus(),commands)
    state.connected=False;first.update(state);pump()
    first.apply_choice(None)
    assert not first.apply.get_sensitive() and len(commands)==1
    key(root,Gdk.KEY_Escape);root.destroy();pump()

    # Real toggle state and visible check mark, including arbitrary custom colors.
    editor=EffectsEditor({'rgb':[0,120,255],'triggers':'game','vibration':'game'})
    dialog=style(Gtk.Dialog(title=_('Luzes e efeitos')),'dualsense')
    geometry=Gdk.Display.get_default().get_primary_monitor().get_workarea();width,height=geometry.width,geometry.height
    dialog.set_default_size(min(590,width),min(590,height));dialog.set_decorated(False)
    dialog.get_content_area().pack_start(label(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'),'warning',wrap=True),False,False,0)
    scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
    scroll.add(editor);dialog.get_content_area().pack_start(scroll,True,True,0)
    close=dialog.add_button(_('Cancelar'),Gtk.ResponseType.CANCEL)
    dialog.show_all();pump()
    for widget,title in [(editor.vibration,_('Vibração')),(editor.triggers,_('Peso dos gatilhos'))]:
        assert widget.get_accessible().get_name()==title
        targets=related(widget,Atk.RelationType.LABELLED_BY)
        assert any(target.get_name()==title for target in targets)
        assert related(widget,Atk.RelationType.DESCRIBED_BY)
    blue=editor.swatches[(0,120,255)];green=editor.swatches[(0,200,90)]
    assert blue.get_accessible().ref_state_set().contains_state(Atk.StateType.CHECKED)
    green.grab_focus();key(dialog,Gdk.KEY_space)
    assert editor.values()['rgb']==[0,200,90] and green.get_label()=='✓'
    assert green.get_accessible().ref_state_set().contains_state(Atk.StateType.CHECKED)
    assert not blue.get_accessible().ref_state_set().contains_state(Atk.StateType.CHECKED)
    key(dialog,Gdk.KEY_space)
    assert green.get_active(),'Activating selected preset must keep a selected color'
    editor.pick((1,2,3))
    assert all(not widget.get_active() for widget in editor.swatches.values())
    assert editor.color.get_accessible().get_description()=='#010203'
    editor.sections.set_visible_child_name('triggers');pump(.2)
    editor.triggers.grab_focus();key(dialog,Gdk.KEY_Down)
    assert editor.triggers.get_active_id()=='off'
    assert editor.triggers.get_accessible().get_description()==_('L2 e R2 ficam livres, sem resistência adicional.')
    editor.sections.set_visible_child_name('color');pump(.2)
    editor.pick((0,200,90));green.grab_focus();pump()
    assert dialog.get_size()[0]<=width and dialog.get_size()[1]<=height
    assert close.get_mapped()
    if output:
        output.mkdir(exist_ok=True,parents=True)
        w,h=dialog.get_size()
        image=Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,w,h)
        image.savev(str(output/f'{code}-effects-{dialog.get_scale_factor()}x.png'),'png',[],[])
    dialog.destroy();pump()
    gallery=AppearanceGallery('white',local_images=False)
    assert gallery.tiles['white'][0].get_accessible().get_name()==_('Branco')
    gallery.destroy()
    class Owner:
        def profiles_dialog(self):pass
    dashboard=Dashboard(Owner())
    assert dashboard.dismiss_notice.get_accessible().get_name()==_('Fechar aviso')
    dashboard.destroy()
    assert commands==[(state.identity,'charge')],'Draft effect choices sent commands'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
    from theme import install_theme
    install_theme()
    for code in ('pt-BR','en','es'):run(code,args.output)
    print('ACCESSIBILITY OK: three languages; controller context, stable ATK names, mode keyboard draft/cancel/confirm/unplug, labeled effects, selected colors, unknown capacity hidden. No hardware or screen-reader certification.')
