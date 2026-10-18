# SPDX-License-Identifier: GPL-3.0-only
"""Actual effects dialog: drafts, cancel, unplug/identity guards and save.

No host settings, network, USB or vibration.
"""
import os
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='dualsense-effects-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    from i18n import set_language,_
    set_language("pt-BR")
    from presentation import ControllerState
    from ui import EffectsEditor
    from gi.repository import GLib,Gtk,Gdk
    usb=root/'usb';usb.mkdir();helper=root/'helper';helper.write_text("BROKER_VERSION = 'uhid-1'\nTRIGGER_PRESETS = {}\nTRIGGER_CONTROL_VERSION = 2")
    original={'rgb':[0,120,255],'vibration':'game','triggers':'game'}
    window.core.write_json(window.core.SETTINGS,{'ui':{'download_photos':False},'effects':{'hid:example':original,'hid:other':{'rgb':[255,0,0]}}})
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',helper),patch.object(window.GLib,'timeout_add_seconds',return_value=0):
        app=window.Window()
    state=ControllerState('hid:example','Controle de teste',port='1-1',requested='proxy',effective='proxy',confirmed=True,fresh=True)
    app.models={state.identity:state}
    failures=[]
    def descendants(widget):
        yield widget
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():yield from descendants(child)
    def exercise(scenario):
        stream=Mock();stream.poll.return_value=None;stream.stdin=io.StringIO()
        app.streams={'1-1':stream};clock=[100.0]
        def inspect():
            dialog=next(w for w in Gtk.Window.list_toplevels() if w.get_title()==_('Luzes e efeitos'))
            try:
                editor=next(w for w in descendants(dialog) if isinstance(w,EffectsEditor))
                save=dialog.get_widget_for_response(Gtk.ResponseType.OK)
                cancel=dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
                geometry=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
                width,height=dialog.get_size()
                assert width<=geometry.width and height<=geometry.height,(width,height,geometry.width,geometry.height)
                for control in (save,cancel):
                    x,y=control.translate_coordinates(dialog,0,0)
                    assert control.get_mapped() and y+control.get_allocated_height()<=height
                assert not save.get_sensitive()
                editor.pick((151,81,255));editor.triggers.set_active_id('firm')
                assert save.get_sensitive()
                assert window.core.settings()['effects']['hid:example']==original,'Draft changed settings'
                if scenario.startswith('preview'):
                    editor.sections.set_visible_child_name('triggers')
                    trial=next(w for w in descendants(dialog) if isinstance(w,Gtk.Button) and w.get_label()==_('Experimentar peso · 5 s'))
                    trial.clicked()
                    commands=[json.loads(line) for line in stream.stdin.getvalue().splitlines()]
                    assert commands==[{'config':dict(original,triggers='firm')}],commands
                    assert window.core.settings()['effects']['hid:example']==original
                    if scenario=='preview_timeout':
                        clock[0]+=6
                        def expired():
                            try:
                                assert trial.get_sensitive()
                                assert json.loads(stream.stdin.getvalue().splitlines()[-1])=={'config':original}
                            except BaseException as exc:failures.append(exc)
                            dialog.response(Gtk.ResponseType.CANCEL);return False
                        GLib.timeout_add(300,expired)
                    elif scenario=='preview_tab':
                        editor.sections.set_visible_child_name('color')
                        assert json.loads(stream.stdin.getvalue().splitlines()[-1])=={'config':original}
                        assert not trial.get_visible()
                        dialog.response(Gtk.ResponseType.CANCEL)
                    elif scenario=='preview_replaced':
                        app.streams={'1-1':Mock()};dialog.response(Gtk.ResponseType.CANCEL)
                    else:dialog.response(Gtk.ResponseType.CANCEL)
                elif scenario=='cancel':dialog.response(Gtk.ResponseType.CANCEL)
                elif scenario=='unplug':
                    state.connected=False
                    # Even a queued OK response must revalidate hardware identity.
                    dialog.response(Gtk.ResponseType.OK)
                elif scenario=='identity':
                    key.return_value='hid:replacement';dialog.response(Gtk.ResponseType.OK)
                else:dialog.response(Gtk.ResponseType.OK)
            except BaseException as exc:failures.append(exc);dialog.response(Gtk.ResponseType.CANCEL)
            return False
        state.connected=True;key.return_value='hid:example'
        GLib.idle_add(inspect)
        with patch.object(window.time,'monotonic',side_effect=lambda:clock[0]):app.effects_dialog('1-1')
        if failures:raise failures[0]
        actual=window.core.settings()['effects']
        assert actual['hid:other']=={'rgb':[255,0,0]}
        if scenario!='save':assert actual['hid:example']==original
        else:assert actual['hid:example']=={'rgb':[151,81,255],'vibration':'game','triggers':'firm'}
        commands=[json.loads(line) for line in stream.stdin.getvalue().splitlines()]
        if scenario in ('preview_cancel','preview_timeout','preview_tab'):assert commands[-1]=={'config':original}
        if scenario=='preview_replaced':assert len(commands)==1
        app.streams={}
    with patch.object(window,'HELPER',helper),patch.object(app,'refresh',return_value=True),patch.object(window.core,'fingerprint',return_value='connection'),patch.object(window.core,'key',return_value='hid:example') as key:
        for code in ('pt-BR','en','es'):
            set_language(code)
            for scenario in ('cancel','unplug','identity','preview_cancel','preview_timeout','preview_replaced','preview_tab','save'):exercise(scenario)
            settings=window.core.settings();settings['effects']['hid:example']=original;window.core.write_json(window.core.SETTINGS,settings)
    app.destroy()
    if failures:raise failures[0]
    print('EFFECTS OK: three languages, bounded dialog with reachable actions, draft/cancel, disconnect/identity guards, temporary trigger preview restores on cancel/timeout, save only target controller.')
