# SPDX-License-Identifier: GPL-3.0-only
"""Actual input dialog, fake USB stream; never opens the host's devices."""
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix='dualsense-input-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'), XDG_STATE_HOME=str(root/'state'), XDG_DATA_HOME=str(root/'data'))
    import window
    from i18n import set_language
    set_language("pt-BR")
    from gi.repository import GLib, Gtk
    from input_view import InputPanel
    from input_state import INPUT_MONITOR_VERSION
    from presentation import ControllerState
    usb=root/'usb';usb.mkdir()
    helper=root/'helper';helper.write_text(f"BROKER_VERSION = 'uhid-1'\nINPUT_MONITOR_VERSION = {INPUT_MONITOR_VERSION}")
    original={'ui':{'download_photos':False},'modes':{'hid:example':'charge'}}
    window.core.write_json(window.core.SETTINGS,original)
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',helper),patch.object(window.GLib,'timeout_add_seconds',return_value=0):
        app=window.Window()
    state=ControllerState('hid:example','Teste',port='1-1',requested='charge',effective='charge',confirmed=True,fresh=True)
    app.models={state.identity:state}
    failures=[]
    def exercise(scenario):
        stream=Mock();stream.poll.return_value=None;stream.stdin=io.StringIO()
        app.streams={'1-1':stream};state.connected=True
        def frame():
            dialog=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='Testar botões')
            def descendants(widget):
                yield widget
                if isinstance(widget,Gtk.Container):
                    for child in widget.get_children():yield from descendants(child)
            panel=next(w for w in descendants(dialog) if isinstance(w,InputPanel))
            try:
                sample={'buttons':['×','L2'],'observed':['×','L2','Options'], 'sticks':[0,255,128,128],'triggers':[255,0],
                        'touches':[{'slot':0,'id':127,'x':400,'y':500},{'slot':1,'id':0,'x':1400,'y':300}]}
                panel.update(sample)
                assert '3 de 19' in panel.count.get_text()
                assert abs(panel.progress.get_fraction()-3/19)<.001
                assert panel.keys['×'].get_text()=='● ×'
                assert panel.keys['Options'].get_text()=='✓ Options'
                assert panel.keys['×'].get_style_context().has_class('pressed')
                assert panel.axes['L2'][0].get_text()=='L2  100%'
                assert 'data-name="×" data-pressed="true"' in panel.blueprint.svg
                assert 'data-name="○" data-pressed="false"' in panel.blueprint.svg
                assert 'id="touch-0"' in panel.blueprint.svg and 'id="touch-1"' in panel.blueprint.svg
                assert '2 de 2' in panel.touch_status.get_text()
                assert 'X 1400' in panel.touch_values.get_text()
                panel.update(dict(sample,touches=[],touch_invalid=1))
                assert 'fora do intervalo' in panel.touch_status.get_text()
                assert 'id="touch-' not in panel.blueprint.svg
                for value,bar in panel.axes.values():assert bar.get_preferred_height().natural_height<25,'Empty meter inherited empty-state padding'
                panel.reset();assert not panel.seen
                assert panel.progress.get_fraction()==0
                assert 'data-pressed="true"' not in panel.blueprint.svg
                assert 'id="touch-' not in panel.blueprint.svg
                assert 'X 1400' not in panel.touch_values.get_text()
                panel.details.set_expanded(True)
                panel.update(sample)
                panel.pages.set_visible_child_name('analogs')
                panel.analog.primary.clicked()
                assert panel.analog.session.phase=='rest'
                hidden=dict(sample,buttons=['○'],observed=['R1'],triggers=[0,255],touches=[])
                with patch.object(panel.blueprint,'show_state',wraps=panel.blueprint.show_state) as draw:
                    panel.update(hidden)
                    draw.assert_not_called()
                    assert {'○','R1'}.issubset(panel.seen)
                panel.pages.set_visible_child_name('controller')
                assert panel.analog.session.phase=='interrupted'
                assert panel.keys['○'].get_style_context().has_class('pressed')
                assert not panel.keys['×'].get_style_context().has_class('pressed')
                assert panel.axes['R2'][0].get_text()=='R2  100%'
                assert 'id="touch-' not in panel.blueprint.svg
                assert 'data-name="○" data-pressed="true"' in panel.blueprint.svg
                panel.pages.set_visible_child_name('analogs')
                panel.update(sample)
                with patch.object(panel.blueprint,'show_state',wraps=panel.blueprint.show_state) as draw:
                    panel.waiting('Lost input while hidden')
                    draw.assert_not_called()
                panel.pages.set_visible_child_name('controller')
                assert 'data-pressed="true"' not in panel.blueprint.svg
                assert 'id="touch-' not in panel.blueprint.svg
                assert panel.axes['L2'][0].get_text()=='L2  —'
                app.input_sample=(sample,time.monotonic())
                if scenario=='unplug':state.connected=False
                if scenario=='replaced':fingerprint.return_value='new-connection'
                if scenario=='stale':app.input_sample=(sample,time.monotonic()-2)
                def verify():
                    try:
                        close=dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
                        assert close.translate_coordinates(dialog,0,0)[1]+close.get_allocated_height()<=dialog.get_allocated_height()
                        monitor=dialog.get_display().get_monitor_at_window(dialog.get_window())
                        assert dialog.get_allocated_height()<=monitor.get_workarea().height
                        assert dialog.get_allocated_width()<=monitor.get_workarea().width
                        if scenario=='live':
                            assert panel.keys['×'].get_style_context().has_class('pressed')
                            assert 'data-name="×" data-pressed="true"' in panel.blueprint.svg
                            assert 'id="touch-1"' in panel.blueprint.svg
                        else:
                            assert not panel.keys['×'].get_style_context().has_class('pressed')
                            assert panel.keys['×'].get_text()=='✓ ×'
                            assert panel.axes['L2'][0].get_text()=='L2  —'
                            assert 'data-pressed="true"' not in panel.blueprint.svg
                            assert 'id="touch-' not in panel.blueprint.svg
                            assert 'X 1400' not in panel.touch_values.get_text()
                    except BaseException as exc:failures.append(exc)
                    dialog.response(Gtk.ResponseType.CLOSE)
                    return False
                GLib.timeout_add(100,verify)
            except BaseException as exc:failures.append(exc);dialog.response(Gtk.ResponseType.CLOSE)
            return False
        fingerprint.return_value='connection'
        GLib.idle_add(frame);app.input_dialog(state.identity)
        requests=[json.loads(line) for line in stream.stdin.getvalue().splitlines()]
        assert requests and all(set(request)=={'monitor'} for request in requests), requests
        assert requests[0]=={'monitor':True}
        if scenario!='replaced':assert requests[-1]=={'monitor':False}
        assert app.input_watch is None and app.input_sample is None
        assert window.core.settings()['modes']==original['modes']
        app.streams={}
    with patch.object(window,'HELPER',helper),patch.object(window.core,'key',return_value='hid:example'),patch.object(window.core,'fingerprint',return_value='connection') as fingerprint:
        for scenario in ('live','stale','unplug','replaced'):exercise(scenario)
        helper.write_text("BROKER_VERSION = 'uhid-1'\nINPUT_MONITOR_VERSION = 1")
        state.connected=True
        with patch.object(Gtk.Dialog,'run',return_value=Gtk.ResponseType.CANCEL) as prompt,patch.object(app,'install') as install:
            app.input_dialog(state.identity)
            prompt.assert_called_once();install.assert_not_called()
        assert app.input_watch is None and not app.streams
    app.destroy()
    if failures:raise failures[0]
    print('INPUT OK: buttons, axes, touches, reset, stale/unplug/replacement, hidden-tab collection without rendering, latest frame on return, legacy upgrade cancellation; only subscriptions, modes preserved.')
