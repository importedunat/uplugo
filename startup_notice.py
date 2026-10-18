# SPDX-License-Identifier: GPL-3.0-only
"""Standalone startup failure UI, also embedded in native entrypoints.

No application imports, assets or writable state. A partially replaced package
must be able to explain why it cannot load the rest of the app. GTK is imported
only after the failure, for a regular user in a graphical session.
"""
import json
import os
from pathlib import Path
import stat
import sys

STARTUP_TEXT = {
    'pt-BR': {
        'package_title': 'A instalação precisa terminar',
        'package_body': 'O Uplugo não pôde verificar se a instalação está pronta. Se uma atualização estiver em andamento, aguarde a conclusão. Se ela terminou ou falhou, repare ou reinstale o Uplugo pelo gerenciador de pacotes da sua distribuição.',
        'launch_title': 'Não foi possível abrir o Uplugo',
        'launch_body': 'Confira os detalhes abaixo. Se precisar reparar a instalação, feche este aviso antes de usar o instalador ou o gerenciador de pacotes. Depois, abra o app novamente.',
        'retry': 'Tentar abrir novamente', 'close': 'Fechar',
        'details': 'Detalhes técnicos', 'dialog_failed': 'Não foi possível mostrar o aviso gráfico.',
    },
    'en': {
        'package_title': 'Installation needs to finish',
        'package_body': 'Uplugo could not verify that the installation is ready. If an update is in progress, wait for it to finish. If it has finished or failed, repair or reinstall Uplugo using your distribution’s package manager.',
        'launch_title': 'Could not open Uplugo',
        'launch_body': 'Check the details below. If the installation needs repair, close this notice before using the installer or package manager. Then open the app again.',
        'retry': 'Try opening again', 'close': 'Close',
        'details': 'Technical details', 'dialog_failed': 'Could not display the graphical notice.',
    },
    'es': {
        'package_title': 'La instalación debe finalizar',
        'package_body': 'Uplugo no pudo verificar si la instalación está lista. Si hay una actualización en curso, espera a que termine. Si ya terminó o falló, repara o reinstala Uplugo con el gestor de paquetes de tu distribución.',
        'launch_title': 'No se pudo abrir Uplugo',
        'launch_body': 'Consulta los detalles a continuación. Si necesitas reparar la instalación, cierra este aviso antes de usar el instalador o el gestor de paquetes. Después, abre la aplicación de nuevo.',
        'retry': 'Intentar abrir de nuevo', 'close': 'Cerrar',
        'details': 'Detalles técnicos', 'dialog_failed': 'No se pudo mostrar el aviso gráfico.',
    },
}


def notice_language(environment=None):
    environment = os.environ if environment is None else environment
    folder = environment.get('XDG_CONFIG_HOME', '')
    root = Path(folder) if folder and Path(folder).is_absolute() else Path(environment.get('HOME') or Path.home()) / '.config'
    # A damaged preference must not block startup on a FIFO or an unbounded read.
    try:
        fd = os.open(root / 'dualsense-usb/controllers.json', os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if stat.S_ISREG(info.st_mode) and info.st_size <= 256 * 1024:
                data = json.loads(stream.read(256 * 1024 + 1))
                code = data.get('ui', {}).get('language')
                if code in STARTUP_TEXT: return code
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    candidates = environment.get('LANGUAGE', '').split(':')
    candidates.append(environment.get('LC_ALL') or environment.get('LC_MESSAGES') or environment.get('LANG', ''))
    for value in candidates:
        base = value.strip().replace('-', '_').split('.')[0].split('@')[0].split('_')[0].lower()
        if base in ('pt', 'en', 'es'): return {'pt': 'pt-BR', 'en': 'en', 'es': 'es'}[base]
    return 'en'


def notice_details(error):
    parts = [str(error)]
    for key in ('stderr', 'stdout'):
        value = getattr(error, key, None)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    # Plain text only: filenames and command output are not GTK markup.
    return '\n'.join(parts)[:12000].replace('\x00', '')


def notice_dialog(Gtk, text, reason, details, retry):
    from gi.repository import Gdk, Pango
    dialog = Gtk.Dialog(title='Uplugo', modal=True)
    display=Gdk.Display.get_default(); monitor=display.get_primary_monitor() or display.get_monitor(0)
    area=monitor.get_workarea() if monitor else None
    width=min(540,area.width-48) if area else 540
    height=min(360,area.height-64) if area else 360
    dialog.set_default_size(width, height)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.add_button(text['close'], Gtk.ResponseType.CLOSE)
    if retry:
        button = dialog.add_button(text['retry'], Gtk.ResponseType.OK)
        button.get_style_context().add_class('suggested-action')
    actions=dialog.get_action_area()
    for button in actions.get_children(): actions.set_child_non_homogeneous(button,True)
    # Closing is the default; retry is always an explicit action.
    dialog.set_default_response(Gtk.ResponseType.CLOSE)
    content = dialog.get_content_area(); content.set_border_width(20)
    scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(180)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    box.set_valign(Gtk.Align.START)
    for key in (reason + '_title', reason + '_body'):
        label = Gtk.Label(label=text[key], xalign=0)
        label.set_line_wrap(True); label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR); label.set_max_width_chars(48)
        if key.endswith('_title'):
            attributes=Pango.AttrList();attributes.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
            attributes.insert(Pango.attr_scale_new(1.15));label.set_attributes(attributes)
        box.pack_start(label, False, False, 0)
    expander = Gtk.Expander(label=text['details'])
    label = Gtk.Label(label=details, xalign=0)
    label.set_line_wrap(True); label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR); label.set_max_width_chars(48); label.set_selectable(True)
    expander.add(label); box.pack_start(expander, False, False, 0)
    scroll.add(box); content.pack_start(scroll, True, True, 0)
    return dialog


def report_startup_failure(error, reason='package', graphical=True, retry=None):
    """Report and return a failure exit code; retry replaces this interpreter."""
    reason = reason if reason in ('package', 'launch') else 'launch'
    code = 78 if reason == 'package' else 1
    text = STARTUP_TEXT[notice_language()]; details = notice_details(error)
    print('Uplugo: ' + text[reason + '_title'] + '\n' + text[reason + '_body'] + '\n' + details, file=sys.stderr)
    # A service must not pop up an error on every restart. Its launcher displays
    # the start failure; the native unit does not retry exit status 78.
    if not graphical or os.geteuid() == 0 or os.environ.get('INVOCATION_ID') or os.environ.get('NOTIFY_SOCKET'):
        return code
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        return code
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        if not Gtk.init_check()[0]: return code
        dialog = notice_dialog(Gtk, text, reason, details, bool(retry)); dialog.show_all()
        try: response = dialog.run()
        finally: dialog.destroy()
    except Exception as exc:
        print(text['dialog_failed'] + ' ' + str(exc), file=sys.stderr)
        return code
    if retry and response == Gtk.ResponseType.OK:
        try: os.execv(retry[0], retry)
        except OSError as exc:
            # Do not silently disappear if retry itself cannot start.
            return report_startup_failure(exc, reason='launch', graphical=graphical)
    return code
