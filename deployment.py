# SPDX-License-Identifier: GPL-3.0-only
"""Select program ownership without changing the user's XDG data locations.

Native packaging writes the small marker beside the immutable runtime. It is
not an authorization token: all privileged commands still have fixed paths and
polkit checks. A misplaced or invalid marker must never select the user installer.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import stat
from app_info import VERSION
from i18n import _

BASE = Path(__file__).resolve().parent
SYSTEM_APP = Path('/usr/share/dualsense-usb')
SYSTEM_UNIT = 'dualsense-usb-system.service'
SYSTEM_UNIT_PATH = Path('/usr/lib/systemd/user') / SYSTEM_UNIT
SYSTEM_HELPER = Path('/usr/libexec/dualsense-usb-helper')
SYSTEM_ACCESS = Path('/usr/libexec/dualsense-usb-access')
MARKER = 'system-package.json'


@dataclass(frozen=True)
class Deployment:
    directory: Path
    manager: str = ''

    @property
    def system(self):return bool(self.manager)

    @property
    def helper(self):
        return SYSTEM_HELPER if self.system else Path('/usr/local/libexec/dualsense-usb-helper')


def inspect_deployment(directory=None):
    directory=Path(directory if directory is not None else BASE).resolve()
    marker=directory/MARKER
    if directory!=SYSTEM_APP and not marker.exists() and not marker.is_symlink():
        return Deployment(directory)
    error=_('Os arquivos da instalação do sistema estão incompletos ou fora do local esperado. Reinstale o pacote pelo gerenciador da distribuição.')
    if directory!=SYSTEM_APP or marker.is_symlink():raise ValueError(error)
    try:
        info=marker.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size>4096:raise ValueError(error)
        data=json.loads(marker.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:raise ValueError(error) from exc
    if not isinstance(data,dict) or set(data)!={'format','manager','version'} or type(data['format']) is not int or data['format']!=1 or data['manager'] not in ('deb','rpm') or data['version']!=VERSION:
        raise ValueError(error)
    return Deployment(directory,data['manager'])


def require_user_maintenance(directory=None,installing=False):
    profile=inspect_deployment(directory)
    if profile.system or (installing and (SYSTEM_APP.exists() or SYSTEM_APP.is_symlink())):
        raise RuntimeError(_('Esta instalação pertence ao gerenciador de pacotes do sistema. Use-o para atualizar ou remover o Uplugo.'))


def legacy_conflicts(locations):
    """Report only program/entrypoint remnants; personal data alone is fine."""
    from migration import program_paths,JOURNAL
    paths=[locations.pending,locations.base/JOURNAL,*program_paths(locations).values()]
    return [str(path) for path in paths if path.exists() or path.is_symlink()]


def require_no_legacy(locations):
    conflicts=legacy_conflicts(locations)
    if conflicts:
        raise RuntimeError(_('Há uma instalação por usuário que pode abrir outra versão. Migre ou remova essa instalação antes de abrir o pacote do sistema. Seus dados pessoais devem ser preservados.')+'\n'+'\n'.join(conflicts))
