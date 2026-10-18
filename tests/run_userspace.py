#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the shared userspace suite as a regular user inside a prepared OS image.

This does not set up a sandbox. Use isolated_userspace.py or the documented
container command. Every GUI check gets a private D-Bus session and X server.
"""
import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from app_info import VERSION


def environment():
    try: release = platform.freedesktop_os_release()
    except OSError: release = {}
    result = {'distribution': release.get('ID', 'unknown'),
              'distribution_version': release.get('VERSION_ID', 'unknown'),
              'architecture': platform.machine(), 'python': platform.python_version()}
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib
        result.update(pygobject=gi.__version__,
                      gtk='.'.join(map(str, (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()))),
                      glib='.'.join(map(str, (GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION))))
    except (ImportError, ValueError):
        result['gtk'] = 'unavailable'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Write machine-readable results, including failures.')
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as a regular user; the installation tests must not run as root.')
    report = {'format': 1, 'app_version': VERSION, 'scope': 'userspace; no physical USB or graphical login',
              'environment': environment(), 'test_display': {'backend': 'x11', 'pixels': [1280, 1024], 'depth': 24, 'scale': 1},
              'results': [], 'ok': False}
    python = [sys.executable]
    # xvfb-run defaults differ: Fedora uses 640x480, Debian/Ubuntu 1280x1024.
    gui = ['dbus-run-session', '--', 'xvfb-run', '-a', '-s', '-screen 0 1280x1024x24', *python]
    commands = [('dependencies', python+['doctor.py', '--no-session']),
                ('unit', python+['-m', 'unittest', 'discover', '-q']),
                ('clean_install', gui+['tests/clean_install.py']),
                ('release', gui+['tests/release_smoke.py', '--gui'])]
    commands += [(name, gui+['tests/'+name+'_smoke.py']) for name in
                 ('session', 'startup', 'autostart', 'stream_recovery', 'native_startup', 'recovery', 'setup', 'deployment', 'migration', 'touchpad','steam_access', 'native_access', 'readonly', 'first_use', 'tour', 'gui', 'accessibility', 'display', 'appearance', 'language', 'effects', 'profiles', 'input', 'input_layout', 'diagnostic', 'analog', 'motion', 'battery', 'photos')]
    commands.append(('stress', gui+['tests/stress.py']))
    try:
        with tempfile.TemporaryDirectory(prefix='dualsense-userspace-') as temporary:
            root = Path(temporary)
            env = dict(os.environ, LANG='C.UTF-8', GDK_BACKEND='x11', GDK_SCALE='1', GIO_USE_VFS='local',
                       NO_AT_BRIDGE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(SOURCE))
            for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'LANGUAGE', 'LC_ALL', 'GTK_THEME', 'GDK_DPI_SCALE'):
                env.pop(key, None)
            for key, name in [('HOME', 'home'), ('XDG_RUNTIME_DIR', 'runtime'),
                              ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                              ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
                path = root/name; path.mkdir(mode=0o700); env[key] = str(path)
            for name, command in commands:
                print('CHECK:', name, flush=True)
                start = time.monotonic()
                try:
                    result = subprocess.run(command, cwd=SOURCE, env=env, check=False)
                    code = result.returncode
                except OSError as exc:
                    print(str(exc), file=sys.stderr); code = 127
                report['results'].append({'name': name, 'exit_code': code,
                                          'seconds': round(time.monotonic()-start, 2)})
                if code:
                    return 1
            report['ok'] = True
            return 0
    finally:
        text = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
        if args.report:
            # A pre-created report in a sticky directory (e.g. a container's
            # /run) cannot be reopened with O_CREAT under fs.protected_regular.
            flags=os.O_WRONLY|os.O_TRUNC|(0 if args.report.exists() else os.O_CREAT)
            with os.fdopen(os.open(args.report,flags,0o644),'w',encoding='utf-8') as stream:stream.write(text)
        print('USERSPACE RESULT:', json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
