# SPDX-License-Identifier: GPL-3.0-only
"""Repeatable synthetic stress, not a USB or battery endurance test."""
import json
import random
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from input_state import InputMonitor, decode_input
from development import DevelopmentWindow, SCENARIOS
from gi.repository import Gtk

start=time.monotonic();rng=random.Random(54)
monitor=InputMonitor();frames=0
for index in range(100000):
    now=100+index/1000
    if index%1000==0:monitor.request(True,now)
    packet=bytes([1])+bytes(rng.randrange(256) for _ in range(63))
    frame=monitor.feed(packet,now)
    if frame:
        frames+=1
        assert all(0<=axis<=255 for axis in frame['input']['sticks']+frame['input']['triggers'])
        assert all(0<=p['x']<1920 and 0<=p['y']<1080 for p in frame['input']['touches'])
        assert len(frame['input']['touches'])+frame['input']['touch_invalid']<=2
    if index%100==0:
        assert decode_input(packet[:-1]) is None
        assert decode_input(bytes([0x31])+packet[1:]) is None
assert 2800<=frames<=3100,frames
monitor.request(False,201)
assert monitor.feed(packet,202) is None

window=DevelopmentWindow();window.show_all()
def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)
pump();transitions=0
try:
    for index in range(120):
        scenario=SCENARIOS[index%len(SCENARIOS)][0]
        window.reset(scenario);pump()
        if scenario=='normal':
            window.request_mode('simulated:0','charge');transitions+=1
            assert window.models['simulated:0'].transition
        window.reset('empty');pump()
        assert not window.pending,'Canceled scenario leaked a timeout'
        assert not window.dashboard.items
    window.reset('normal');pump()
    first=window.dashboard.items['simulated:0']
    first.test_input.grab_focus()
    for index in range(5000):
        model=window.models['simulated:0']
        model.reading={'capacity':index%101,'status':'Charging','time':'synthetic'}
        model.fresh=True
        window.render()
        if index%50==0:pump()
        assert window.dashboard.items['simulated:0'] is first,'Update replaced the focused widget'
        assert len(window.dashboard.cards.get_children())==2
    assert window.get_focus() is first.test_input
    assert len(window.pending)==0
finally:window.destroy();pump()
print(json.dumps({'synthetic_reports':100000,'ui_frames':frames,'scenario_changes':240,
                  'canceled_transitions':transitions,'dashboard_updates':5000,
                  'seconds':round(time.monotonic()-start,2),'usb_access':False}))
