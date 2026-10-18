# SPDX-License-Identifier: GPL-3.0-only
"""Linux tray integration through the installed Ayatana library."""
import ctypes as C
import ctypes.util
from pathlib import Path
from gi.repository import Gtk, Gio, GLib
from i18n import _

class Tray:
    def __init__(self, show, quit_app):
        self.status=Gtk.MenuItem(label=_('Uplugo em execução'))
        self.actions=[]
        self.indicator=None
        library=ctypes.util.find_library('ayatana-appindicator3') or ctypes.util.find_library('appindicator3')
        if not library:return
        self.library = C.CDLL(library)
        for name, args, result in [
            ('app_indicator_new', [C.c_char_p, C.c_char_p, C.c_int], C.c_void_p),
            ('app_indicator_set_status', [C.c_void_p, C.c_int], None),
            ('app_indicator_set_menu', [C.c_void_p, C.c_void_p], None),
            ('app_indicator_set_title', [C.c_void_p, C.c_char_p], None),
        ]:
            method=getattr(self.library,name);method.argtypes=args;method.restype=result
        icon=Path(__file__).resolve().parent/'assets/dualsense-usb.svg'
        self.indicator=self.library.app_indicator_new(b'dualsense-usb',str(icon).encode(),0)
        if not self.indicator:raise RuntimeError(_('Não foi possível criar o ícone da bandeja.'))
        self.menu=Gtk.Menu()
        self.status.set_sensitive(False)
        self.menu.append(self.status)
        self.menu.append(Gtk.SeparatorMenuItem())
        for label,callback in [('Abrir Uplugo',show),('Sair e liberar controles para a Steam',quit_app)]:
            item=Gtk.MenuItem(label=label)
            self.actions.append((item,label))
            item.connect('activate',lambda item,fn=callback:fn())
            self.menu.append(item)
        self.menu.show_all()
        pointer=C.pythonapi.PyCapsule_GetPointer
        pointer.argtypes=[C.py_object,C.c_char_p];pointer.restype=C.c_void_p
        self.library.app_indicator_set_menu(self.indicator,pointer(self.menu.__gpointer__,None))
        self.library.app_indicator_set_title(self.indicator,b'Uplugo')
        self.library.app_indicator_set_status(self.indicator,1)
        self.retranslate()

    def retranslate(self):
        self.status.set_label(_('Uplugo em execução'))
        for item,text in self.actions:item.set_label(_(text))

    def available(self):
        if not self.indicator:return False
        try:
            bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            result=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
                                 'NameHasOwner',GLib.Variant('(s)',('org.kde.StatusNotifierWatcher',)),
                                 GLib.VariantType.new('(b)'),Gio.DBusCallFlags.NONE,1000,None)
            return result.unpack()[0]
        except GLib.Error:return False

    def close(self):
        if self.indicator:self.library.app_indicator_set_status(self.indicator,0)
