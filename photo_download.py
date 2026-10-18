# SPDX-License-Identifier: GPL-3.0-only
"""Optional, bounded product-image downloads. No USB or controller identities.

The shipped manifest contains source URLs, never third-party image bytes.
Downloads retain the image owners' rights; see THIRD_PARTY.md.
"""
from i18n import _
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import artwork

CATALOG = json.loads((artwork.ASSETS/'photo-sources.json').read_text())['photos']
ALLOWED_HOSTS = {'gmedia.playstation.com', 'media.direct.playstation.com',
                 'www.sony.jp', 'blog.playstation.com'}
MAX_BYTES = 16 * 1024 * 1024
TIMEOUT = 8


def checked_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS
            or parsed.port not in (None, 443) or parsed.username or parsed.password):
        raise ValueError(_('A origem da foto não faz parte do catálogo oficial.'))
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)  # Check before sending a request to the destination.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Cancelled(Exception):
    pass


def fetch_photo(entry, cancel):
    key = entry['id']
    if key not in artwork.BY_ID:raise ValueError(_('Modelo desconhecido.'))
    # Only known old catalog bytes may be upgraded; custom imports always win.
    previous=artwork.photo_digest(key)
    if artwork.photo_path(key) and previous not in entry.get('replaces_sha256',[]):return False
    url = checked_url(entry['url'])
    folder = artwork.library();folder.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.download-', dir=folder)
    deadline = time.monotonic() + 30
    try:
        with os.fdopen(fd, 'wb') as output:
            if cancel.is_set():raise Cancelled()
            request = Request(url, headers={'User-Agent':'DualSenseUSB/0.4 (product image cache)',
                                           'Accept':'image/png,image/jpeg,image/webp'})
            with build_opener(OfficialRedirect()).open(request, timeout=TIMEOUT) as response:
                checked_url(response.geturl())
                if response.headers.get_content_type() not in ('image/png','image/jpeg','image/webp'):
                    raise ValueError(_('O servidor não retornou uma foto.'))
                length = int(response.headers.get('Content-Length', '0'))
                if length < 0 or length > MAX_BYTES:raise ValueError(_('Foto maior que 16 MB.'))
                size = 0
                while True:
                    if cancel.is_set():raise Cancelled()
                    if time.monotonic() > deadline:raise TimeoutError(_('Tempo de download excedido.'))
                    chunk = response.read(64*1024)
                    if not chunk:break
                    size += len(chunk)
                    if size > MAX_BYTES:raise ValueError(_('Foto maior que 16 MB.'))
                    output.write(chunk)
                if length and size != length:raise ValueError(_('Download incompleto.'))
        if cancel.is_set():raise Cancelled()
        artwork.import_photo(key, temporary, replace=previous is not None,
                             expected_sha256=previous)
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


class PhotoDownloads:
    """One daemon worker; UI receives immutable snapshots via its main loop."""
    def __init__(self, notify):
        self.notify = notify
        self.cancel = threading.Event()
        self.worker = None
        self.state = dict(active=False, done=0, total=len(CATALOG), available=0,
                          failed=(), stopped=False, finished=False)

    def start(self, preferred=()):
        if self.worker and self.worker.is_alive():return False
        self.cancel.clear()
        entries = sorted(CATALOG, key=lambda entry:entry['id'] not in preferred)
        self.state = dict(active=True, done=0, total=len(entries), available=0,
                          failed=(), stopped=False, finished=False)
        self.worker = threading.Thread(target=self._run, args=(entries,), daemon=True,
                                       name='dualsense-photos')
        self.worker.start()
        return True

    def stop(self):
        self.cancel.set()

    def _run(self, entries):
        failed = [];done = available = consecutive = 0
        try:
            for entry in entries:
                if self.cancel.is_set():break
                key = entry['id']
                try:
                    fetch_photo(entry, self.cancel)
                    available += 1;consecutive = 0
                except Cancelled:
                    break
                except Exception:
                    # Keep working for individual missing assets; avoid hammering
                    # an offline connection or unavailable host on every frame.
                    failed.append(key);consecutive += 1
                done += 1
                self._publish(True,done,available,failed,key)
                if consecutive >= 3:break
        finally:
            self._publish(False,done,available,failed,None)

    def _publish(self, active, done, available, failed, key):
        self.state = dict(active=active, done=done, total=len(CATALOG), available=available,
                          failed=tuple(failed), stopped=self.cancel.is_set(), finished=not active)
        self.notify(key, self.state.copy())


def status_text(state):
    if state['active']:return _('Baixando fotos · {0} de {1} verificadas').format(state['done'], state['total'])
    if state['stopped']:return _('Download pausado. As fotos salvas continuam disponíveis.')
    if state['failed']:return _('Algumas fotos não foram baixadas. Tente novamente quando houver conexão.')
    if state['finished']:return _('{0} fotos salvas · disponíveis sem internet').format(state['available'])
    return _('As fotos são salvas neste computador para usar sem internet.')
