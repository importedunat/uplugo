# SPDX-License-Identifier: GPL-3.0-only
"""Guided help uses real widgets without sending controller commands. Run in Xvfb."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.display_smoke import pump
from tests.accessibility_smoke import key
from ui import Dashboard,ContentClamp,style
from presentation import ControllerState
from i18n import set_language
from theme import install_theme
from gi.repository import Gtk,Gdk
install_theme();Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
class Owner:
 def __init__(self):self.actions=[]
 def card_action(self,*a):self.actions.append(a)
 def request_mode(self,*a):self.actions.append(a)
 def profiles_dialog(self):self.actions.append('profiles')
for lang in ('pt-BR','en','es'):
 for width,font in ((1000,'Sans 11'),(480,'Sans 16')):
  set_language(lang);Gtk.Settings.get_default().set_property('gtk-font-name',font)
  owner=Owner();w=style(Gtk.Window(),'dualsense');w.set_decorated(False);w.set_default_size(width,700)
  d=Dashboard(owner);w.add(ContentClamp(d))
  m=ControllerState('demo:1','Demo',requested='charge',effective='charge',confirmed=True,fresh=True)
  d.update([m],True);w.show_all();w.get_window().focus(Gdk.CURRENT_TIME);pump()
  d.help.clicked();pump();tour=d.tour
  for index in range(len(tour.steps)):
   assert tour.index==index and tour.popup.get_visible()
   assert tour.target.get_style_context().has_class('tour-focus')
   width_,height_=w.get_size();pw,ph=tour.popup.get_allocated_width(),tour.popup.get_allocated_height()
   assert pw<=width_ and ph<=height_,(lang,font,index,tour.steps[index][1],pw,ph,width_,height_)
   if index==2:
    tour.back.clicked();pump();assert tour.index==1
    tour.next.clicked();pump();assert tour.index==2 and not owner.actions
   tour.next.clicked();pump()
  assert tour.closed and not owner.actions
  d.start_tour();pump();key(w,Gdk.KEY_Escape);assert d.tour.closed
  d.start_tour();pump();d.tour.show(4);pump();d.update([],True);pump()
  assert d.tour.closed and not owner.actions
  d.start_tour();pump();assert len(d.tour.steps)==5
  d.tour.close();w.destroy();pump()
print('TOUR OK: three languages, 480/1000 widths, large font, all steps, Escape, unplug, empty state; no actions')
