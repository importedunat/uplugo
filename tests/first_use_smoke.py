# SPDX-License-Identifier: GPL-3.0-only
"""First use and authorization outcomes with private files and a fake installer."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix='dualsense-first-use-') as directory:
    root=Path(directory)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),
                      XDG_STATE_HOME=str(root/'state'),LANGUAGE='es',LC_ALL='C.UTF-8')
    import i18n
    import window
    import access_request
    from first_use import mode_guide_dialog
    from gi.repository import Gtk
    from presentation import AccessSetup
    usb=root/'usb';usb.mkdir();helper=root/'helper'
    def pump():
        while Gtk.events_pending():Gtk.main_iteration_do(False)
    def until(predicate):
        deadline=time.monotonic()+4
        while not predicate():
            pump()
            if time.monotonic()>deadline:raise AssertionError('Timed out waiting for first-use outcome')
            time.sleep(.01)
        pump()
    with patch.object(window.core,'USB',usb),patch.object(window,'HELPER',helper), \
         patch.object(window.core,'migrate_legacy'), \
         patch.object(window.Window,'start_photo_downloads',return_value=False), \
         patch.object(window.GLib,'timeout_add_seconds',return_value=0):
        app=window.Window()
        try:
            pump()
            assert i18n.language()=='es'
            assert app.dashboard.first_language.get_active_id()=='es'
            assert app.dashboard.stack.get_visible_child_name()=='empty'
            assert app.dashboard.setup.get_visible() and app.dashboard.unlock.get_sensitive()
            assert not window.core.SETTINGS.exists(), 'First use must not write an inferred language or mode'
            app.dashboard.first_language.set_active_id('pt-BR');pump()
            assert i18n.saved_language()=='pt-BR'
            assert app.dashboard.language_choice.get_active_id()=='pt-BR'
            app.dashboard.connection_help.set_expanded(True);pump()
            assert not app.streams
            # Help and dismissing it must not run commands or change settings.
            before=window.core.SETTINGS.read_bytes()
            with patch.object(window.subprocess,'run') as commands:
                for code in ('pt-BR','en','es'):
                    i18n.set_language(code)
                    guide=mode_guide_dialog(app);guide.show_all();pump()
                    close=guide.get_widget_for_response(Gtk.ResponseType.CLOSE)
                    assert close.get_label()==i18n._('Entendi')
                    assert close.translate_coordinates(guide,0,0)[1]+close.get_allocated_height()<=guide.get_allocated_height()
                    area=guide.get_display().get_monitor_at_window(guide.get_window()).get_workarea()
                    assert guide.get_allocated_width()<=area.width and guide.get_allocated_height()<=area.height
                    guide.response(Gtk.ResponseType.CLOSE);guide.destroy()
                i18n.set_language('pt-BR')
                commands.assert_not_called()
            assert window.core.SETTINGS.read_bytes()==before
            with patch.object(window.subprocess,'Popen') as spawn:
                app.dashboard.try_lab.clicked()
                assert spawn.call_args.args[0]==['/usr/bin/python3',str(window.BASE/'development.py')]
            # Keep a synthetic live session while exercising the asynchronous
            # authorization runner. No USB path or real subprocess is used.
            preferences=window.core.settings();preferences['modes']={'fixture':'charge'}
            window.core.write_json(window.core.SETTINGS,preferences)
            saved=window.core.SETTINGS.read_bytes()
            stream=Mock();app.streams={'fixture':stream}
            expected="BROKER_VERSION = 'uhid-1'\n# first-use fixture\n"
            def redraw():app.dashboard.update(list(app.models.values()),app.helper_ready())
            with patch.object(app,'refresh',side_effect=redraw),patch.object(app,'stop_all') as stop:
                gate=threading.Event()
                def cancelled(command,**kwargs):
                    assert command[:3]==['pkexec','/usr/bin/python3','-I']
                    assert gate.wait(3)
                    return subprocess.CompletedProcess(command,126,'','authorization dismissed')
                with patch.object(access_request,'helper_source',return_value=expected) as build, \
                     patch.object(window.subprocess,'run',side_effect=cancelled):
                    app.install()
                    assert app.busy and not app.unlock.get_sensitive()
                    assert app.access_setup.phase=='busy' and app.dashboard.setup_spinner.get_property('active')
                    app.install();until(lambda:build.call_count==1);build.assert_called_once()
                    gate.set();until(lambda:not app.busy)
                assert app.access_setup.phase=='cancelled'
                assert app.unlock.get_sensitive() and app.unlock.get_label()=='Tentar novamente'
                assert not app.dashboard.setup_details.get_visible()
                stop.assert_not_called();stream.stdin.write.assert_not_called()
                assert window.core.SETTINGS.read_bytes()==saved
                for code,error in ((127,'authorization refused'),(1,'fixture installer failure')):
                    with patch.object(access_request,'helper_source',return_value=expected), \
                         patch.object(window.subprocess,'run',return_value=subprocess.CompletedProcess([],code,'',error)):
                        app.install();until(lambda:not app.busy)
                    assert app.access_setup.phase=='failed' and app.dashboard.setup_details.get_visible()
                    assert app.dashboard.setup_error.get_text()==error
                    stop.assert_not_called()
                    assert window.core.SETTINGS.read_bytes()==saved
                with patch.object(access_request,'helper_source',side_effect=OSError('package fixture missing')),patch.object(window.subprocess,'run') as command:
                    app.install();until(lambda:not app.busy);command.assert_not_called()
                    assert app.access_setup.phase=='failed' and not app.busy
                # Exit status 0 alone is not enough to restart controller sessions.
                with patch.object(access_request,'helper_source',return_value=expected), \
                     patch.object(window.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')):
                    app.install();until(lambda:not app.busy)
                assert app.access_setup.phase=='failed';stop.assert_not_called()
                def installed(command,**kwargs):
                    helper.write_text(expected)
                    return subprocess.CompletedProcess(command,0,'','')
                with patch.object(access_request,'helper_source',return_value=expected),patch.object(window.subprocess,'run',side_effect=installed):
                    app.install();until(lambda:not app.busy)
                stop.assert_called_once();assert not app.dashboard.setup.get_visible()
                assert window.core.SETTINGS.read_bytes()==saved
                app.review_access()
                assert app.dashboard.setup.get_visible() and app.unlock.get_label()=='Atualizar suporte USB'
                app.dismiss_access();assert not app.dashboard.setup.get_visible()
                # A failure is still visible if older USB support already exists.
                app.access_setup=AccessSetup('failed','existing support fixture');redraw()
                assert app.dashboard.setup.get_visible()
            # Revision warnings are advisory: a protocol-compatible helper
            # remains usable, including while a comparison is running.
            app.access_setup=AccessSetup()
            revision=access_request.HelperRevision(helper,builder=lambda:expected+'# correction\n')
            app.support_revision=revision
            until(lambda:revision.state()=='different')
            with patch.object(app,'install') as install,patch.object(app,'open_setup') as setup, \
                 patch.object(app,'stop_all') as stop,patch.object(window.subprocess,'run') as command:
                for language in ('pt-BR','en','es'):
                    i18n.set_language(language)
                    for native in (False,True):
                        revision.native=native;app.access_setup=AccessSetup();redraw();pump()
                        assert app.helper_ready() and app.dashboard.support_update.get_visible()
                        expected_action='Verificar instalação' if native else 'Revisar suporte USB'
                        assert app.dashboard.support_update_button.get_label()==i18n._(expected_action)
                        app.dashboard.support_update_button.clicked();pump()
                        if native:setup.assert_called_once();setup.reset_mock()
                        else:
                            assert app.access_setup.reviewing and app.dashboard.setup.get_visible()
                            assert not app.dashboard.support_update.get_visible()
                            app.dismiss_access();redraw();assert app.dashboard.support_update.get_visible()
                        assert window.core.SETTINGS.read_bytes()==saved
                        assert app.streams['fixture'] is stream
                install.assert_not_called();stop.assert_not_called();command.assert_not_called()
                stream.stdin.write.assert_not_called()
                helper.write_text(expected+'# correction\n')
                revision._next=0;until(lambda:revision.state()=='current');redraw()
                assert not app.dashboard.support_update.get_visible()
                assert app.helper_ready()
            print('FIRST USE OK: system language, visible selector, read-only help, demo launch, busy exclusion, cancellation, failure, retry, verified installation and unchanged modes.')
            print('SUPPORT REVISION OK: async comparison, compatible helper stays usable, manual review and native package guidance in three languages, no authorization/restart, notice clears after replacement.')
        finally:
            app.streams={};app.quit_app();pump()
