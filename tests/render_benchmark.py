# SPDX-License-Identifier: GPL-3.0-only
"""Informational GTK input-render benchmark; synthetic data, no USB.

Run under private D-Bus/Xvfb in the test image. Numbers describe the local
rendering workload, not controller or game latency. There is no timing gate.
"""
import sys,time,math,json,resource,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from input_view import InputPanel
from ui import ASSETS
from theme import install_theme
install_theme()
window=Gtk.Window();window.set_default_size(720,900)
panel=InputPanel();window.add(panel);window.show_all()
def pump():
 while Gtk.events_pending():Gtk.main_iteration_do(False)
pump();results=[]
for page in ('controller','analogs'):
 panel.pages.set_visible_child_name(page);pump()
 # Include a synthetic range trace; functional stage transitions have their
 # own tests in analog_smoke.py. No real controller is opened.
 if page=='analogs':panel.analog.session.phase='travel'
 times=[];child_start=resource.getrusage(resource.RUSAGE_CHILDREN)
 for i in range(120):
  t=time.perf_counter();angle=i*.15
  panel.update({'buttons':['×'] if i%2 else [],'observed':[],'sticks':[round(127.5+100*math.sin(angle)),round(127.5+100*math.cos(angle)),round(127.5+90*math.cos(angle)),round(127.5+90*math.sin(angle))],'triggers':[i%256,0],'touches':[]})
  pump();times.append((time.perf_counter()-t)*1000)
 child_end=resource.getrusage(resource.RUSAGE_CHILDREN)
 results.append({'page':page,'frames':len(times),'mean_ms':round(statistics.mean(times),3),'p95_ms':round(sorted(times)[int(len(times)*.95)-1],3),'max_ms':round(max(times),3),'child_cpu_seconds':round(child_end.ru_utime+child_end.ru_stime-child_start.ru_utime-child_start.ru_stime,3)})
window.destroy();pump();print(json.dumps(results))
