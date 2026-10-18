# SPDX-License-Identifier: GPL-3.0-only
"""App layout with desktop font sizing and GTK high-contrast colors."""
import os
from pathlib import Path
from gi.repository import Gtk,Gdk

ASSETS=Path(__file__).resolve().parent/'assets'
_theme=None


class Theme:
    def __init__(self,screen):
        self.screen=screen;self.settings=Gtk.Settings.get_for_screen(screen)
        self.original_dark=self.settings.get_property('gtk-application-prefer-dark-theme')
        self.layout=Gtk.CssProvider();self.layout.load_from_path(str(ASSETS/'style.css'))
        self.palette=Gtk.CssProvider();self.palette.load_from_path(str(ASSETS/'colors.css'))
        Gtk.StyleContext.add_provider_for_screen(screen,self.layout,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.palette_active=False
        self.settings.connect('notify::gtk-theme-name',self.update)
        self.update()

    def update(self,*args):
        name=os.environ.get('GTK_THEME') or self.settings.get_property('gtk-theme-name') or ''
        normalized=''.join(c for c in name.lower() if c.isalpha())
        self.high_contrast='highcontrast' in normalized
        active=not self.high_contrast
        if active!=self.palette_active:
            operation=Gtk.StyleContext.add_provider_for_screen if active else Gtk.StyleContext.remove_provider_for_screen
            if active:operation(self.screen,self.palette,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
            else:operation(self.screen,self.palette)
            self.palette_active=active
        self.settings.set_property('gtk-application-prefer-dark-theme',self.original_dark if self.high_contrast else True)


def install_theme():
    global _theme
    if _theme is None:_theme=Theme(Gdk.Screen.get_default())
    return _theme
