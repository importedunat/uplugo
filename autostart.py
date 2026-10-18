# SPDX-License-Identifier: GPL-3.0-only
"""Optional "open at login": an XDG autostart entry that starts in the tray.

The entry belongs to the user, lives in XDG_CONFIG_HOME/autostart and is only
written or removed when the user changes the preference (or uninstalls). Its
existence is the source of truth, so removing it from the desktop's own startup
settings also turns the option off here. The hidden start is requested with a
short-lived marker in the private state directory, consumed by the window.
"""
import os
from pathlib import Path
import time

NAME = 'dualsense-usb.desktop'
MARKER = 'X-DualSense-USB-Autostart=true'
HIDDEN = 'start-hidden'
HIDDEN_MAX_AGE = 120


def config_home():
    value = os.environ.get('XDG_CONFIG_HOME')
    return Path(value) if value and os.path.isabs(value) else Path.home()/'.config'


def entry_path(config=None):
    return Path(config if config is not None else config_home())/'autostart'/NAME


def desktop_quoted(value):
    # Exec quoting from the Desktop Entry spec, plus the string-level escape.
    escaped = str(value).replace('\\', '\\\\\\\\').replace('"', '\\\\\\"').replace('`', '\\\\`').replace('$', '\\\\$').replace('%', '%%')
    return '"'+escaped+'"'


def entry_text(launcher):
    return ('[Desktop Entry]\n'
            'Type=Application\n'
            'Name=Uplugo\n'
            'Comment=Opens in the tray when you log in\n'
            'Comment[pt_BR]=Abre na bandeja ao entrar na sessão\n'
            'Comment[es]=Se abre en la bandeja al iniciar sesión\n'
            f'Exec=/usr/bin/python3 {desktop_quoted(launcher)} --background\n'
            'Icon=dualsense-usb\n'
            'Terminal=false\n'
            'NoDisplay=true\n'
            'X-GNOME-Autostart-enabled=true\n'
            'X-GNOME-Autostart-Delay=3\n'
            f'{MARKER}\n')


def _ours(path):
    try:
        if path.is_symlink() or not path.is_file():return False
        return MARKER in path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return False


def enabled(config=None):
    path = entry_path(config)
    if not _ours(path):return False
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    return not any(line.strip().lower() in ('hidden=true', 'x-gnome-autostart-enabled=false') for line in lines)


def set_enabled(on, launcher, config=None):
    path = entry_path(config)
    if path.is_symlink() or (path.exists() and not _ours(path)):
        raise ValueError('Outro programa usa '+str(path)+'. Ele foi preservado.')
    if not on:
        if path.exists():path.unlink()
        return False
    launcher = Path(launcher)
    if not launcher.is_absolute() or not launcher.is_file():
        raise ValueError('Instale o app antes de ativar a abertura automática.')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.'+NAME+'.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(entry_text(launcher))
    os.replace(temporary, path)
    return True


def remove_if_ours(config=None):
    """Used by uninstall: remove only an entry this app created."""
    path = entry_path(config)
    if _ours(path):
        path.unlink()
        return path
    return None


def request_hidden_start(state_dir):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(state_dir/HIDDEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(str(time.time()))


def consume_hidden_start(state_dir, now=None):
    path = Path(state_dir)/HIDDEN
    try:
        if path.is_symlink():
            path.unlink();return False
        text = path.read_text()
        path.unlink()
        stamp = float(text.strip() or 0)
    except (OSError, ValueError):
        return False
    now = time.time() if now is None else now
    return 0 <= now-stamp <= HIDDEN_MAX_AGE
