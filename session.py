# SPDX-License-Identifier: GPL-3.0-only
"""Desktop lifecycle, independent of the user's init system.

GApplication owns uniqueness on the session bus. Only its primary instance
constructs a Window (and therefore opens USB); another launch just activates it.
"""
import subprocess
import os
from pathlib import Path
from i18n import _

APP_ID = 'org.local.DualSenseUSB'
APP_PATH = '/org/local/DualSenseUSB'
UNIT = 'dualsense-usb.service'


def systemd_available():
    try:
        return subprocess.run(['systemctl', '--user', 'show-environment'],
                              capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def session_bus():
    from gi.repository import Gio
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def process_directory(pid,proc=Path('/proc')):
    """Identify an existing Python entrypoint, including relative arguments."""
    entry=proc/str(pid)
    args=(entry/'cmdline').read_bytes().split(b'\0')
    if not args or not Path(os.fsdecode(args[0])).name.startswith('python'):return None
    index=1
    while index<len(args) and args[index] in (b'-I',b'-B',b'-u',b'-E',b'-s',b'-S',b'-O',b'-OO'):index+=1
    if index>=len(args) or not args[index] or args[index].startswith(b'-'):return None
    script=Path(os.fsdecode(args[index]))
    if not script.is_absolute():script=(entry/'cwd').resolve()/script
    return script.resolve().parent if script.name=='window.py' else None


def instance_running():
    """True when the app already owns its D-Bus name; never activates it."""
    from gi.repository import Gio, GLib
    return session_bus().call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                   'org.freedesktop.DBus', 'NameHasOwner',
                                   GLib.Variant('(s)', (APP_ID,)), GLib.VariantType('(b)'),
                                   Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]


def activate_existing(expected_directory=None):
    """Activate only an existing owner. Never register a competing instance."""
    from gi.repository import Gio, GLib
    bus = session_bus()
    owned = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                          'org.freedesktop.DBus', 'NameHasOwner',
                          GLib.Variant('(s)', (APP_ID,)), GLib.VariantType('(b)'),
                          Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
    if not owned:
        return False
    destination=APP_ID
    if expected_directory is not None:
        destination=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus',
            'org.freedesktop.DBus','GetNameOwner',GLib.Variant('(s)',(APP_ID,)),
            GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
        pid=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus',
            'org.freedesktop.DBus','GetConnectionUnixProcessID',GLib.Variant('(s)',(destination,)),
            GLib.VariantType('(u)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
        try:directory=process_directory(pid)
        except OSError:directory=None
        if directory!=Path(expected_directory).resolve():
            raise RuntimeError(_('Outra instalação do Uplugo está aberta. Encerre-a pela bandeja antes de abrir a versão do sistema.'))
    bus.call_sync(destination, APP_PATH, 'org.freedesktop.Application', 'Activate',
                  GLib.Variant('(a{sv})', ({},)), None,
                  Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
    return True


def run_application(window_factory, argv=None):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gio, GLib
    from maintenance import installation_lock
    from deployment import inspect_deployment, require_no_legacy
    from maintenance import Locations
    profile=inspect_deployment()
    if profile.system:
        require_no_legacy(Locations.current())
        if activate_existing(expected_directory=profile.directory):return 0
    # GApplication can otherwise fall back to a non-unique local process when
    # D-Bus is absent. Never let that create competing owners of the controllers.
    try:
        session_bus()
    except GLib.Error as exc:
        raise RuntimeError(_('Não foi possível conectar à sessão do desktop. Abra o app dentro de uma sessão gráfica com D-Bus.')) from exc
    GLib.set_prgname('dualsense-usb')
    GLib.set_application_name('Uplugo')
    app = Gtk.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
    window = None
    lock = None
    startup_errors = []

    def activate(application):
        nonlocal window, lock
        if window is None:
            try:
                if application.get_dbus_connection() is None:
                    raise RuntimeError(_('Não foi possível conectar à sessão do desktop. Abra o app dentro de uma sessão gráfica com D-Bus.'))
                candidate = installation_lock(shared=True)
                candidate.__enter__()
                lock = candidate
                window = window_factory(application=application)
            except Exception as exc:
                # Exceptions raised from GObject handlers otherwise only print
                # a traceback and can incorrectly exit with success.
                startup_errors.append(exc)
                application.quit()
        else:
            window.reveal()

    def shutdown(application):
        nonlocal lock
        try:
            if window is not None:
                window.stop_resources()
        finally:
            if lock is not None:
                lock.__exit__(None, None, None)
                lock = None

    app.connect('activate', activate)
    app.connect('shutdown', shutdown)
    try:
        result = app.run(argv or ['dualsense-usb'])
    finally:
        # Covers a startup failure before GApplication emits shutdown, too.
        if lock is not None:
            lock.__exit__(None, None, None)
    if startup_errors:raise startup_errors[0]
    return result
