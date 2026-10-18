# SPDX-License-Identifier: GPL-3.0-only
"""Open at login: hidden start in the tray, reveal, and the Preferences toggle; no USB."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='dualsense-autostart-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    import autostart
    import tray
    from i18n import set_language
    window.core.write_json(window.core.SETTINGS,{'ui':{'download_photos':False}})
    from gi.repository import GLib,Gtk
    usb=root/'usb';usb.mkdir()
    launcher=root/'installed app'/'launch.py';launcher.parent.mkdir();launcher.write_text('# launcher\n')
    failures=[]
    for code in ('pt-BR','en','es'):
        set_language(code)
        autostart.request_hidden_start(window.core.STATE_DIR)
        with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',root/'missing-helper'),patch.object(tray.Tray,'available',return_value=True):
            app=window.Window()
            def verify():
                try:
                    assert not app.get_visible(), 'Login start must stay in the tray'
                    assert not (window.core.STATE_DIR/autostart.HIDDEN).exists(), 'The request is single-use'
                    choice=app.dashboard.autostart
                    assert not choice.get_active() and not choice.get_sensitive(), 'A source checkout must not register itself'
                    choice.set_sensitive(True);app.autostart_launcher=launcher
                    choice.set_active(True)
                    entry=autostart.entry_path()
                    assert entry.is_file() and str(launcher.parent.name) in entry.read_text() and autostart.enabled()
                    assert app.notice.get_text()
                    choice.set_active(False)
                    assert not entry.exists() and not autostart.enabled()
                    entry.write_text('[Desktop Entry]\nExec=other\n')
                    choice.set_active(True)
                    assert not choice.get_active(), 'A foreign entry is reported, not overwritten'
                    assert entry.read_text()=='[Desktop Entry]\nExec=other\n'
                    entry.unlink()
                    app.reveal()
                    assert app.get_visible(), 'Opening from the tray or menu shows the window'
                    print('AUTOSTART:',code,'hidden start, reveal, toggle on/off, foreign entry preserved')
                except BaseException as exc:failures.append(exc)
                finally:app.quit_app()
                return False
            GLib.idle_add(verify);Gtk.main()
        if failures:raise failures[0]
    print('AUTOSTART OK: hidden login start, single-use request, reveal, Preferences toggle in three languages; no USB.')
