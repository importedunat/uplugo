# SPDX-License-Identifier: GPL-3.0-only
"""Offline appearance library. Images never grant hardware capabilities.

Official product images are personal local files, not GPL repository assets.
No network requests, device identifiers or USB operations are used here.
"""
from i18n import _
import json
import hashlib
import os
import shutil
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf, GLib

ASSETS = Path(__file__).resolve().parent/'assets'
MODELS = json.loads((ASSETS/'models.json').read_text())
BY_ID = {entry['id']:entry for entry in MODELS}
NEUTRAL = {'id':'neutral','name':'Padrão','group':'Ilustração','color':'#dfe3eb'}
_library_lock = threading.RLock()


def model(key):
    return BY_ID.get(key,NEUTRAL)


def library():
    value=os.environ.get('XDG_DATA_HOME','')
    base=Path(value) if value and Path(value).is_absolute() else Path.home()/'.local/share'
    return base/'dualsense-usb/appearance-library'


def photo_path(key, local=True):
    if not local or key not in BY_ID:return None
    for suffix in ('.png','.jpg','.jpeg','.webp'):
        path=library()/(key+suffix)
        if path.is_file():return path
    return None


def photo_stamp(key, local=True):
    path=photo_path(key,local)
    try:return str(path),path.stat().st_mtime_ns
    except (OSError,AttributeError):return None


def validate_image(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError(_('Escolha uma imagem de até 16 MB.'))
    info=GdkPixbuf.Pixbuf.get_file_info(str(path))
    fmt,width,height=info
    if not fmt or fmt.get_name() not in ('png','jpeg','webp'):
        raise ValueError(_('Escolha uma foto PNG, JPEG ou WebP.'))
    if not 0<width<=8192 or not 0<height<=8192 or width*height>24_000_000:
        raise ValueError(_('A imagem deve ter até 8192 pixels por lado e 24 megapixels.'))
    return fmt.get_name()


def photo_digest(key):
    path=photo_path(key)
    try:return hashlib.sha256(path.read_bytes()).hexdigest() if path else None
    except OSError:return None


def import_photo(key,path,replace=True,expected_sha256=None):
    # Download completion must never overwrite a photo imported meanwhile.
    with _library_lock:
        if expected_sha256 is not None and photo_digest(key)!=expected_sha256:
            return photo_path(key)
        if not replace and photo_path(key):return photo_path(key)
        return _import_photo(key,path)


def _import_photo(key,path):
    if key not in BY_ID:raise ValueError(_('Escolha o modelo antes de importar a foto.'))
    fmt=validate_image(path)
    # Decode before replacing a working photo; truncated/corrupt files fail here.
    GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),900,600,True)
    folder=library();folder.mkdir(parents=True,exist_ok=True)
    suffix={'jpeg':'.jpg','png':'.png','webp':'.webp'}[fmt]
    target=folder/(key+suffix)
    fd,temporary=tempfile.mkstemp(prefix='.import-',dir=folder)
    try:
        with os.fdopen(fd,'wb') as output,open(path,'rb') as source:shutil.copyfileobj(source,output)
        os.replace(temporary,target)
        for extension in ('.png','.jpg','.jpeg','.webp'):
            previous=folder/(key+extension)
            if previous!=target:previous.unlink(missing_ok=True)
    finally:Path(temporary).unlink(missing_ok=True)
    _photo.cache_clear()
    return target


def visible_bounds(pixbuf):
    """Find the product's display bounds; original image bytes stay untouched."""
    width,height=pixbuf.get_width(),pixbuf.get_height()
    pixels=pixbuf.get_pixels();channels=pixbuf.get_n_channels();stride=pixbuf.get_rowstride()
    alpha=pixbuf.get_has_alpha()
    x0,y0,x1,y1=width,height,0,0
    # Ignore transparent margins and near-white studio background consistently.
    for y in range(0,height,3):
        for x in range(0,width,3):
            pos=y*stride+x*channels
            if (not alpha or pixels[pos+3]>40) and min(pixels[pos:pos+3])<242:
                x0=min(x0,x);y0=min(y0,y);x1=max(x1,x);y1=max(y1,y)
    if x0==width:return 0,0,width,height
    x0=max(0,x0-8);y0=max(0,y0-8)
    x1=min(width,x1+11);y1=min(height,y1+11)
    return x0,y0,x1-x0,y1-y0


@lru_cache(maxsize=64)
def _photo(path,stamp,width,height):
    validate_image(path)
    original=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,900,600,True)
    x,y,w,h=visible_bounds(original)
    cropped=original.new_subpixbuf(x,y,w,h)
    ratio=min(width/w,height/h)
    return cropped.scale_simple(max(1,round(w*ratio)),max(1,round(h*ratio)),GdkPixbuf.InterpType.BILINEAR)


@lru_cache(maxsize=128)
def _illustration(key,width,height):
    svg=(ASSETS/'controller.svg').read_text().replace('#SHELL#',model(key)['color']).replace('#ACCENT#','#1769ec')
    loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.set_size(width,height)
    loader.write(svg.encode());loader.close()
    return loader.get_pixbuf()


def picture(key,width=300,height=190,local=True):
    stamp=photo_stamp(key,local)
    if stamp:
        try:return _photo(*stamp,width,height),True
        except (OSError,ValueError,GLib.Error):pass
    return _illustration(key,width,height),False
