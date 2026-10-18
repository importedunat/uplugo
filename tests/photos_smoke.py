# SPDX-License-Identifier: GPL-3.0-only
"""Exercise opt-in photo downloads, pause/resume and the native photo UI.

Synthetic images, private XDG directories, no network and no host USB.
"""
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='dualsense-photos-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    from i18n import set_language
    set_language("pt-BR")
    import photo_download
    import artwork
    from gi.repository import GLib,Gtk,Gdk,GdkPixbuf
    source=root/'fixture.png'
    image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,32,24)
    image.fill(0xaaaaffff);image.savev(str(source),'png',[],[])
    usb=root/'usb';usb.mkdir()
    def descendants(widget):
        yield widget
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():yield from descendants(child)
    entered=threading.Event();release=threading.Event();failures=[]
    def download(entry,cancel):
        entered.set();release.wait(5)
        if cancel.is_set():raise photo_download.Cancelled()
        artwork.import_photo(entry['id'],source,replace=False)
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',root/'missing'),patch.object(photo_download,'fetch_photo',side_effect=download):
        app=window.Window()
        phase={'value':'starting','ticks':0}
        def exercise():
            phase['ticks']+=1
            try:
                assert phase['ticks']<800,'Photo UI test timed out'
                assert not app.streams
                if phase['value']=='starting':
                    # Official photos are opt-in: nothing is fetched in a fresh account.
                    if phase['ticks']<30:return True
                    assert not entered.is_set() and not app.photos.state['active'],'Photos must not download by default'
                    phase['value']='dialog'
                    GLib.idle_add(open_dialog)
                elif phase['value']=='enabled':
                    if not entered.is_set():return True
                    phase['value']='paused';phase['toggle'].set_active(False);release.set()
                elif phase['value']=='paused' and not app.photos.state['active'] and 'pausado' in app.photo_controls[1].get_text():
                    assert app.photos.state['stopped']
                    assert 'pausado' in app.photo_controls[1].get_text()
                    phase['value']='resuming';phase['toggle'].set_active(True)
                elif phase['value']=='resuming' and not app.photos.state['active'] and '41 fotos salvas' in app.photo_controls[1].get_text():
                    assert app.photos.state['available']==41
                    assert app.photo_controls[0].get_fraction()==1
                    assert '41 fotos salvas' in app.photo_controls[1].get_text()
                    assert app.photo_controls[2].get_sensitive()
                    assert len([p for p in artwork.library().iterdir() if p.suffix=='.png'])==41
                    assert window.core.settings()['modes']=={}
                    # Let GTK draw the final callback before capturing pixels.
                    phase['value']='capture';return True
                elif phase['value']=='capture':
                    if '--capture' in sys.argv:
                        output=sys.argv[sys.argv.index('--capture')+1]
                        dialog=phase['dialog'];w,h=dialog.get_size()
                        shot=Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,w,h)
                        shot.savev(output,'png',[],[])
                    phase['toggle'].set_active(False)
                    assert window.core.settings()['ui']['download_photos'] is False
                    phase['value']='finished';phase['dialog'].response(Gtk.ResponseType.CLOSE)
                    print('PHOTOS UI OK: off by default, opt-in download, responsive while waiting, pause/resume, cache, progress; no USB changes.')
                    return False
            except BaseException as exc:
                failures.append(exc);release.set()
                if phase.get('dialog'):phase['dialog'].response(Gtk.ResponseType.CLOSE)
                app.quit_app();return False
            return True
        def prepare_dialog():
            try:
                dialog=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='Fotos dos controles')
                toggle=next(w for w in descendants(dialog) if isinstance(w,Gtk.CheckButton))
                assert not toggle.get_active(),'Photo downloads must be off by default'
                phase.update(dialog=dialog,toggle=toggle,value='enabled')
                toggle.set_active(True)
            except BaseException as exc:
                failures.append(exc);app.quit_app()
            return False
        def open_dialog():
            GLib.idle_add(prepare_dialog)
            app.photos_dialog()
            app.quit_app()
            return False
        GLib.timeout_add(10,exercise);Gtk.main()
        release.set()
        if app.photos.worker:app.photos.worker.join(5)
        if failures:raise failures[0]
        assert phase['value']=='finished'
