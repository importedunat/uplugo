#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Render the native UI with synthetic data; never touches USB or user state."""
import argparse
import math
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk, GLib
from presentation import ControllerState
from ui import Dashboard, ContentClamp, style, ASSETS
from presentation import AccessSetup
from i18n import _, set_language


def input_preview(output, native=False, analogs=False):
    from input_view import InputPanel
    from ui import label
    from theme import install_theme
    install_theme()
    widget=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=15);widget.set_border_width(25)
    widget.pack_start(label(_('Testar botões'),'controller-name'),False,False,0)
    widget.pack_start(label(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'),'warning',wrap=True),False,False,0)
    panel=InputPanel();widget.pack_start(panel,True,True,0)
    panel.update({'buttons':['×','R1'],'observed':['×','R1','L2','Options'],
                  'sticks':[128,128,250,40],'triggers':[120,0],
                  'touches':[{'slot':0,'id':12,'x':400,'y':400},{'slot':1,'id':13,'x':1450,'y':700}]})
    if analogs:
        session=panel.analog.session
        # A deterministic demonstration, never readings from a real device.
        session.interrupt();session.observe([128]*4,10);session.start_rest(10)
        for index in range(127):session.observe([128+index%2,127,128,128],10+.04*(index+1))
        now=15.08;session.start_travel(now)
        for index in range(91):
            now+=.04;angle=index*math.pi/45
            session.observe([round(127.5+127.5*math.cos(angle)),round(127.5+127.5*math.sin(angle)),
                             round(127.5+120*math.sin(angle)),round(127.5+120*math.cos(angle))],now)
        session.finish(now);panel.analog.clock=lambda:now
        panel.pages.set_visible_child_name('analogs');panel.analog.render(now)
    off=style(Gtk.Window() if native else Gtk.OffscreenWindow(),'dualsense');off.set_default_size(700,900 if analogs else 820)
    if native:off.set_decorated(False)
    off.add(widget);off.show_all()
    if analogs:panel.pages.set_visible_child_name('analogs');panel.analog.render(now)
    for iteration in range(10):
        while Gtk.events_pending():Gtk.main_iteration_do(False)
    if native:
        loop=GLib.MainLoop()
        GLib.timeout_add(180,lambda:(loop.quit(),False)[1]);loop.run()
        w,h=off.get_size()
        pixbuf=Gdk.pixbuf_get_from_window(off.get_window(),0,0,w,h)
    else:pixbuf=off.get_pixbuf()
    pixbuf.savev(str(output),'png',[],[])
    actual=(pixbuf.get_width(),pixbuf.get_height());off.destroy()
    return actual


def battery_preview(output, native=False):
    import tempfile
    from charge_watch import ChargeWatch
    from charge_view import BatteryPanel, attach_battery_panel
    from ui import themed_dialog, label
    from theme import install_theme
    install_theme()

    with tempfile.TemporaryDirectory() as temp:
        watch=ChargeWatch(Path(temp)/'synthetic.json')
        watch.flush=lambda:None  # Preview data stays in memory.
        start=1781690400
        for index,(baseline,final,minutes,port) in enumerate(((25,25,30,'1-2'),(25,55,45,'3-1'),(55,65,20,'3-1'))):
            for elapsed in range(0,minutes*60+1,10):
                capacity=final if elapsed==minutes*60 else baseline
                now=start+elapsed
                watch.observe('demo',str(index),dict(capacity=capacity,status='Charging'),now,port=port)
            start=now+120
        state=ControllerState('demo','Player 02',port='3-1',fresh=True,
                              reading={'capacity':65,'status':'Charging','time':'12:00'})
        dialog=themed_dialog(_('Bateria e conexão'),None)
        dialog.add_button(_('Fechar'),Gtk.ResponseType.CLOSE)
        panel=BatteryPanel(state.name)
        banner=label(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'),'warning',wrap=True)
        panel.pack_start(banner,False,False,0);panel.reorder_child(banner,1)
        attach_battery_panel(dialog,panel)
        panel.update(watch,'demo',state,now)
        dialog.show_all();panel.history.set_expanded(True)
        loop=GLib.MainLoop();GLib.timeout_add(180,lambda:(loop.quit(),False)[1]);loop.run()
        width,height=dialog.get_size()
        pixbuf=Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height)
        pixbuf.savev(str(output),'png',[],[])
        dialog.destroy()
        return width,height


def recovery_preview(output, scenario):
    import tempfile
    import subprocess
    from maintenance import Locations
    from recovery_ui import RecoveryDialog
    from ui import label
    from theme import install_theme
    install_theme()

    with tempfile.TemporaryDirectory() as temporary:
        locations=Locations(Path(temporary)/'data',Path(temporary)/'config')
        locations.app.mkdir(parents=True);(locations.app/'launch.py').touch()
        dialog=RecoveryDialog(locations,lambda:subprocess.CompletedProcess([],0))
        banner=label(_('DADOS SIMULADOS · nenhum controle real está sendo lido.'),'warning',wrap=True)
        # This preview never starts a recovery operation.
        dialog.get_content_area().pack_start(banner,False,False,0)
        dialog.get_content_area().reorder_child(banner,0)
        dialog.show_all()
        if scenario=='recovery-failed':dialog.completed(subprocess.CompletedProcess([],1,'','Demonstration: the app is still running.'))
        if scenario=='recovery-complete':dialog.completed(subprocess.CompletedProcess([],0))
        loop=GLib.MainLoop();GLib.timeout_add(180,lambda:(loop.quit(),False)[1]);loop.run()
        width,height=dialog.get_size()
        pixbuf=Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height)
        pixbuf.savev(str(output),'png',[],[])
        dialog.destroy()
        return width,height


def render(output, width=1040, height=880, scenario='dashboard', local_images=False, native=False):

    Gtk.Settings.get_default().set_property('gtk-overlay-scrolling',False)
    from theme import install_theme
    install_theme()
    class Owner:
        preview=True
        def profiles_dialog(self):pass
        def install(self):pass
        def about_dialog(self):pass
        def photos_dialog(self):pass
        def card_action(self,*args):pass
        def request_mode(self,*args):pass
    owner=Owner();owner.local_images=local_images
    dashboard=Dashboard(owner)
    models=[ControllerState(identity='hid:00:00:00:00:a1:b2',name='Player 01',port='1-1',
            requested='proxy',effective='proxy',confirmed=True,fresh=True,
            reading={'capacity':75,'status':'Discharging','time':'20:30:00'},rgb=[104,229,238],appearance='black'),
            ControllerState(identity='hid:00:00:00:00:c3:d4',name='Player 02',port='1-2',
            requested='charge',effective='charge',confirmed=True,fresh=True,
            appearance='white',reading={'capacity':35,'status':'Charging','time':'20:30:00'})]
    if scenario=='setup':
        for model in models:model.helper_ready=False;model.confirmed=False
    if scenario=='empty' or scenario.startswith('welcome'):models=[]
    if scenario=='welcome-cancelled':owner.access_setup=AccessSetup('cancelled')
    if scenario=='welcome-failed':owner.access_setup=AccessSetup('failed','Demonstration: setup could not be completed.')
    if scenario=='welcome-busy':owner.access_setup=AccessSetup('busy')
    if scenario=='stale':
        models[0].fresh=False;models[0].confirmed=False
        models[1].connected=False;models[1].fresh=False;models[1].confirmed=False
    if scenario=='error':models[0].error='Não foi possível acessar o controle. Verifique a conexão e tente novamente.'
    ready=scenario!='setup' and not scenario.startswith('welcome')
    dashboard.update(models,ready)
    dashboard.count.set_text('DEMONSTRAÇÃO · dados fictícios, sem acesso ao USB')
    off=style(Gtk.Window() if native else Gtk.OffscreenWindow(),'dualsense')
    if native:off.set_decorated(False)
    off.set_size_request(width,height);off.add(ContentClamp(dashboard));off.show_all()
    dashboard.update(models,ready)
    dashboard.count.set_text('DEMONSTRAÇÃO · dados fictícios, sem acesso ao USB')
    for _ in range(10):
        while Gtk.events_pending():Gtk.main_iteration_do(False)
    if native:
        # A native surface avoids theme-specific OffscreenWindow text clipping.
        # Use this option under Xvfb when producing public screenshots.
        loop=GLib.MainLoop()
        GLib.timeout_add(180,lambda:(loop.quit(),False)[1]);loop.run()
        w,h=off.get_size()
        image=Gdk.pixbuf_get_from_window(off.get_window(),0,0,w,h)
    else:image=off.get_pixbuf()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    image.savev(str(output),'png',[],[])
    actual=(image.get_width(),image.get_height())
    off.destroy()
    return actual


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='docs/preview.png')
    parser.add_argument('--width',type=int,default=1040)
    parser.add_argument('--height',type=int,default=880)
    parser.add_argument('--local-images',action='store_true',help='Use personal photos; do not publish the result without image rights.')
    parser.add_argument('--language',choices=['pt-BR','en','es'],default='pt-BR')
    parser.add_argument('--native',action='store_true',help='Capture a visible native window; use under Xvfb for screenshots.')
    parser.add_argument('--scenario',choices=['dashboard','empty','stale','error','setup','input','analog','battery','recovery','recovery-failed','recovery-complete','welcome','welcome-cancelled','welcome-failed','welcome-busy'],default='dashboard')
    args=parser.parse_args()
    set_language(args.language)
    if args.scenario.startswith('recovery'):
        print(recovery_preview(args.output,args.scenario));raise SystemExit(0)
    if args.scenario=='battery':
        print(battery_preview(args.output,args.native));raise SystemExit(0)
    print(input_preview(args.output,args.native,args.scenario=='analog') if args.scenario in ('input','analog') else render(args.output,args.width,args.height,args.scenario,args.local_images,args.native))
