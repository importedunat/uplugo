# SPDX-License-Identifier: GPL-3.0-only
"""Native failure dialogs and real fresh-interpreter retry; no hardware."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from unittest.mock import patch
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))


def child(screenshots):
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk,GLib
    import startup_notice as notice
    settings=Gtk.Settings.get_default()
    for font in ('Sans 10','Sans 18'):
        settings.set_property('gtk-font-name',font)
        for language in ('pt-BR','en','es'):
            preference=Path(os.environ['XDG_CONFIG_HOME'])/'dualsense-usb/controllers.json'
            preference.parent.mkdir(parents=True,exist_ok=True)
            preference.write_text(json.dumps({'ui':{'language':language}}))
            failures=[];original=notice.notice_dialog
            def make(*args):
                dialog=original(*args)
                def check():
                    try:
                        assert dialog.get_visible()
                        assert dialog.get_default_widget()==dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
                        assert dialog.get_widget_for_response(Gtk.ResponseType.OK).get_label()==notice.STARTUP_TEXT[language]['retry']
                        area=Gdk.Display.get_default().get_monitor_at_window(dialog.get_window()).get_workarea()
                        width,height=dialog.get_size()
                        assert width<=area.width and height<=area.height,(font,language,width,height,area.width,area.height)
                        def descendants(widget):
                            yield widget
                            if isinstance(widget,Gtk.Container):
                                for item in widget.get_children():yield from descendants(item)
                        labels=[widget for widget in descendants(dialog) if isinstance(widget,Gtk.Label)]
                        assert any(widget.get_text()==notice.STARTUP_TEXT[language]['package_body'] for widget in labels)
                        details=next(widget for widget in labels if widget.get_text().startswith('<missing'))
                        assert not details.get_use_markup() and details.get_selectable()
                        if screenshots and language=='pt-BR' and font=='Sans 10':
                            screenshots.mkdir(parents=True,exist_ok=True)
                            Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height).savev(str(screenshots/'native-startup.png'),'png',[],[])
                    except BaseException as exc:failures.append(exc)
                    dialog.response(Gtk.ResponseType.CLOSE);return False
                GLib.timeout_add(100,check)
                return dialog
            with patch.object(notice,'notice_dialog',side_effect=make),contextlib.redirect_stderr(io.StringIO()):
                assert notice.report_startup_failure(RuntimeError('<missing file> & details'),retry=[sys.executable,'unchanged'])==78
            if failures:raise failures[0]
    # Real GTK unavailable-display fallback is tested in the parent process too.
    print('NATIVE STARTUP UI OK: pt-BR/en/es, large text, bounded window, explicit retry and plain details.')


def retry_driver(root):
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,GLib
    sys.path.insert(0,str(root))
    def respond():
        dialogs=[item for item in Gtk.Window.list_toplevels() if isinstance(item,Gtk.Dialog) and item.get_visible()]
        if not dialogs:return True
        (root/'native_lifecycle.py').write_text('def hold_native_package(version): pass\n')
        # Replace the entrypoint after the failure. Retry must read this new
        # file in a new interpreter, not resume already-imported old modules.
        (root/'entry.py').write_bytes((root/'next-entry').read_bytes())
        dialogs[0].get_widget_for_response(Gtk.ResponseType.OK).activate()
        return False
    GLib.timeout_add(100,respond)
    runpy.run_path(str(root/'entry.py'),run_name='__main__')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--child',action='store_true');parser.add_argument('--retry-driver',type=Path);parser.add_argument('--screenshots',type=Path)
    args=parser.parse_args()
    if args.child:return child(args.screenshots)
    if args.retry_driver:return retry_driver(args.retry_driver)
    with tempfile.TemporaryDirectory(prefix='dualsense-native-startup-') as temporary:
        root=Path(temporary)
        env=dict(os.environ,HOME=str(root),XDG_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
        for key in ('INVOCATION_ID','NOTIFY_SOCKET','PYTHONPATH'):env.pop(key,None)
        command=[sys.executable,__file__,'--child']
        if args.screenshots:command+=['--screenshots',str(args.screenshots.resolve())]
        subprocess.run(command,env=dict(env,GDK_SCALE='1'),check=True,timeout=30)
        subprocess.run([sys.executable,__file__,'--child'],env=dict(env,GDK_SCALE='2'),check=True,timeout=30)
        import native_package
        old=b"raise AssertionError('Old program resumed')\n"
        marker=root/'result'
        new=('from pathlib import Path\nPath('+repr(str(marker))+').write_text("fresh process")\n').encode()
        (root/'entry.py').write_bytes(native_package.bootstrap(old))
        (root/'next-entry').write_bytes(native_package.bootstrap(new))
        (root/'native_lifecycle.py').write_text('def hold_native_package(version): raise RuntimeError("maintenance test")\n')
        # The driver can import the gate next to the entrypoint, but the actual
        # retry gets that path through Python's normal script invocation.
        subprocess.run([sys.executable,__file__,'--retry-driver',str(root)],env=dict(env,PYTHONPATH=str(root)),check=True,timeout=15)
        assert marker.read_text()=='fresh process'
        headless=dict(env,DISPLAY=':65530',WAYLAND_DISPLAY='missing-display')
        result=subprocess.run([sys.executable,'-c','from startup_notice import report_startup_failure;raise SystemExit(report_startup_failure(RuntimeError("headless")))'],env=headless,cwd=SOURCE,capture_output=True,text=True,timeout=5)
        assert result.returncode==78 and 'headless' in result.stderr,result.stderr
        print('NATIVE STARTUP RETRY OK: real replacement process loads the repaired entrypoint; unavailable display exits cleanly; no USB.')


if __name__=='__main__':main()
