# SPDX-License-Identifier: GPL-3.0-only
"""Exercise actual window startup and missing-tray recovery without USB."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='dualsense-startup-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    from i18n import set_language
    set_language("pt-BR")
    window.core.write_json(window.core.SETTINGS,{'ui':{'download_photos':False}})
    from gi.repository import GLib,Gtk
    usb=root/'usb';usb.mkdir()
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',root/'missing-helper'):
        app=window.Window()
        failures=[]
        def verify():
            try:
                assert app.dashboard.stack.get_visible_child_name()=='empty'
                assert app.dashboard.setup.get_visible()
                assert not app.streams
                with patch.object(app.tray,'available',return_value=False):
                    assert app.hide_to_tray()
                    assert 'não tem bandeja' in app.notice.get_text()
                assert app.get_visible(), 'No invisible application when the desktop has no tray'
                # Apply an observed access to one synthetic controller, then
                # verify explicit Play grants the configured exception.
                device=usb/'1-1';device.mkdir()
                interface=root/'fake-interface';interface.mkdir();(interface/'authorized').write_text('1')
                config=window.core.settings()
                config.update(names={'hid:test':'Teste'},modes={'hid:test':'play'},protection={'enabled':True,'allow_manual_play':True})
                window.core.write_json(window.core.SETTINGS,config)
                with patch.object(window.core,'supported',return_value=True),patch.object(window.core,'key',return_value='hid:test'),patch.object(window.core,'interfaces',return_value=[interface]),patch.object(window.core,'raw_device',return_value=None),patch.object(window.core,'battery',return_value={'capacity':65,'status':'Charging'}),patch.object(app,'helper_ready',return_value=True),patch.object(app,'ensure_stream'),patch.object(app.access_guard,'check',return_value={'hid:test':'steam'}) as access:
                    app.refresh()
                    assert window.core.settings()['modes']['hid:test']=='charge'
                    assert 'steam' in app.models['hid:test'].guard_reason
                    access.return_value={}
                    app.stream_status['1-1']={'mode':'charge','exclusive':True}
                    app.stream_kinds['1-1']='managed'
                    app.request_mode('hid:test','proxy')
                    assert window.core.settings()['modes']['hid:test']=='proxy'
                    assert 'hid:test' in window.core.settings()['protection']['play_exceptions']
                    app.stream_status['1-1']={'mode':'proxy','exclusive':True,'virtual_started':True}
                    app.request_mode('hid:test','charge')
                    assert window.core.settings()['modes']['hid:test']=='charge'
                    assert 'hid:test' not in window.core.settings()['protection']['play_exceptions']
                print('STARTUP OK: empty account, no USB, missing tray; access -> charge -> explicit play -> charge re-arms guard.')
            except BaseException as exc:failures.append(exc)
            finally:app.quit_app()
            return False
        GLib.idle_add(verify);Gtk.main()
        if failures:raise failures[0]
