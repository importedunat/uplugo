#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Graphical installation/removal assistant. Does not access controllers."""
import os
import argparse
import sys
from i18n import _


def main():
    parser=argparse.ArgumentParser(description=_('Instalação e remoção'))
    parser.parse_args()
    if os.geteuid()==0:
        print(_('Abra o assistente como seu usuário, sem sudo.'),file=sys.stderr);return 1
    try:
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
    except (ImportError,ValueError) as exc:
        print(_('Não foi possível abrir o assistente gráfico. Instale Python 3, PyGObject e GTK 3 conforme o README da pasta do download.'),file=sys.stderr)
        print(str(exc),file=sys.stderr);return 1
    if not Gtk.init_check()[0]:
        print(_('Abra o assistente dentro da sua sessão gráfica.'),file=sys.stderr);return 1
    try:
        from setup_ui import SetupDialog
        from theme import install_theme
    except (ImportError,OSError,ValueError) as exc:
        message=Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,buttons=Gtk.ButtonsType.CLOSE,
            text=_('Faltam arquivos neste pacote. Extraia novamente o download completo e abra o assistente dessa pasta.'))
        message.format_secondary_text(str(exc))
        try:message.run()
        finally:message.destroy()
        return 1
    install_theme()
    dialog=SetupDialog();dialog.show_all();dialog.refresh()
    try:
        while True:
            response=dialog.run()
            if response!=Gtk.ResponseType.OK:break
            if dialog.finish_requested:break
            dialog.start()
    finally:dialog.destroy()
    return 0


if __name__=='__main__':raise SystemExit(main())
