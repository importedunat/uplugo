#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only environment checks; does not enumerate controller identities."""
import ctypes.util
import json
import shutil
import sys
from pathlib import Path


def checks(session=True,native=False):
    result=[]
    def add(name,ok,required=True):result.append(dict(name=name,ok=bool(ok),required=required))
    add('Python 3.10+',sys.version_info>=(3,10))
    for command in ('pkexec','udevadm'):add(command,shutil.which(command))
    if native:add('pkcheck',Path('/usr/bin/pkcheck').is_file())
    add('systemctl (supervisão opcional)',shutil.which('systemctl'),False)
    add('libusb',ctypes.util.find_library('usb-1.0'))
    add('Bandeja AppIndicator',ctypes.util.find_library('ayatana-appindicator3') or ctypes.util.find_library('appindicator3'),False)
    try:
        import gi
        gi.require_version('Gtk','3.0')
        gi.require_version('GdkPixbuf','2.0')
        from gi.repository import Gtk,GdkPixbuf
        add('GTK 3 / PyGObject',True)
        add('Imagens SVG',any(fmt.get_name()=='svg' for fmt in GdkPixbuf.Pixbuf.get_formats()))
    except (ImportError,ValueError):add('GTK 3 / PyGObject',False)
    if session:
        from session import systemd_available, session_bus
        add('Sessão systemd de usuário (opcional)',systemd_available(),False)
        try:
            from gi.repository import GLib
        except ImportError:add('D-Bus da sessão gráfica',False)
        else:
            try:
                session_bus()
                add('D-Bus da sessão gráfica',True)
            except (ImportError,ValueError,GLib.Error):add('D-Bus da sessão gráfica',False)
        add('UHID disponível (necessário para Minhas configurações)',Path('/dev/uhid').exists(),False)
    return result


if __name__=='__main__':
    from deployment import inspect_deployment
    items=checks(session='--no-session' not in sys.argv,native=inspect_deployment().system)
    if '--json' in sys.argv:print(json.dumps(items,ensure_ascii=False,indent=2))
    else:
        for item in items:print(('OK' if item['ok'] else 'FALTA' if item['required'] else 'OPCIONAL')+' · '+item['name'])
    sys.exit(int(any(item['required'] and not item['ok'] for item in items)))
