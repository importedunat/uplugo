# SPDX-License-Identifier: GPL-3.0-only
"""Build a prefilled GitHub issue link. Nothing is sent: the browser opens the
form and the person reviews every field before submitting."""
import json
import os
import platform
from urllib.parse import urlencode

from app_info import VERSION, REPOSITORY

# GitHub and some browsers reject very long addresses; the full report is also
# copied to the clipboard, so a long one is left out of the link.
MAX_URL = 7000


def environment(release=None, env=None):
    env = os.environ if env is None else env
    if release is None:
        try:release = platform.freedesktop_os_release()
        except OSError:release = {}
    distro = release.get('PRETTY_NAME') or release.get('NAME') or 'Linux'
    desktop = env.get('XDG_CURRENT_DESKTOP') or 'desconhecido'
    session = env.get('XDG_SESSION_TYPE') or 'desconhecida'
    return f'{distro} · {desktop} ({session}) · kernel {platform.release()}'


def issue_url(report, mode=None, release=None, env=None):
    """report: the allowlisted diagnostics snapshot (dict)."""
    fields = {'template': 'bug_report.yml', 'version': VERSION,
              'environment': environment(release, env)}
    if mode:fields['mode'] = mode
    text = json.dumps(report, ensure_ascii=False, separators=(',', ':'))
    url = REPOSITORY+'/issues/new?'+urlencode(dict(fields, diagnostics=text))
    if len(url) <= MAX_URL:return url, True
    return REPOSITORY+'/issues/new?'+urlencode(fields), False
