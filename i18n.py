# SPDX-License-Identifier: GPL-3.0-only
"""Local UI catalogs. Language changes never touch USB or system locale."""
import json
import os
from pathlib import Path

LANGUAGES = {'pt-BR': 'Português (Brasil)', 'en': 'English', 'es': 'Español'}
CATALOG_DIR = Path(__file__).resolve().parent / 'locales'
_language = 'pt-BR'
_catalog = {}


def language():
    return _language


def set_language(code):
    global _language, _catalog
    if code not in LANGUAGES:
        code = 'pt-BR'
    catalog = {}
    if code != 'pt-BR':
        try:
            data = json.loads((CATALOG_DIR / (code + '.json')).read_text())
            if isinstance(data, dict):
                catalog = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError):
            code = 'pt-BR'
    _language, _catalog = code, catalog


def _(message):
    return _catalog.get(message, message)


def system_language(environment=None):
    """Choose a bundled language on first use, without changing system locale."""
    environment=os.environ if environment is None else environment
    candidates=environment.get('LANGUAGE','').split(':')
    candidates.append(environment.get('LC_ALL') or environment.get('LC_MESSAGES') or environment.get('LANG',''))
    for candidate in candidates:
        base=candidate.strip().replace('-','_').split('.')[0].split('@')[0].split('_')[0].lower()
        if base in ('pt','en','es'):return {'pt':'pt-BR','en':'en','es':'es'}[base]
    return 'en'


def saved_language():
    folder = os.environ.get('XDG_CONFIG_HOME', '')
    root = Path(folder) if folder and Path(folder).is_absolute() else Path.home() / '.config'
    try:
        data = json.loads((root / 'dualsense-usb/controllers.json').read_text())
        code = data.get('ui', {}).get('language')
        return code if code in LANGUAGES else system_language()
    except (OSError, ValueError, AttributeError, TypeError):
        return system_language()


set_language(saved_language())
