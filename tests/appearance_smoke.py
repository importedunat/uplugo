# SPDX-License-Identifier: GPL-3.0-only
"""Real name/model dialog: drafts, keyboard, resizing, recovery and photo scope.

Run under private Xvfb; synthetic images and devices, no network or host USB.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dualsense-appearance-') as temporary:
        root=Path(temporary)
        os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'))
        import window
        import artwork
        from gi.repository import Gtk,GLib,Gdk,GdkPixbuf,Atk
        from ui import AppearanceEditor
        from presentation import ControllerState
        from i18n import _,set_language
        from tests import accessibility_smoke as keyboard

        def pump(delay=.08):
            start=time.monotonic()
            while True:
                while Gtk.events_pending():
                    assert time.monotonic()-start<3,'GTK event queue did not settle'
                    Gtk.main_iteration_do(False)
                if time.monotonic()-start>=delay:return
                time.sleep(.005)
        keyboard.pump=pump
        def descendants(widget):
            yield widget
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():yield from descendants(child)
        def inside(widget,dialog,vertical=False):
            x,y=widget.translate_coordinates(dialog,0,0);width,height=dialog.get_size()
            assert x>=0 and x+widget.get_allocated_width()<=width,(type(widget),x,widget.get_allocation(),width)
            if vertical:assert y>=0 and y+widget.get_allocated_height()<=height

        usb=root/'usb';usb.mkdir()
        original={'names':{'hid:demo:a1234':'Meu controle','hid:demo:b5678':'Outro controle'},
                  'appearance':{'hid:demo:a1234':'black','hid:demo:b5678':'white'},
                  'modes':{'hid:demo:a1234':'proxy','hid:demo:b5678':'charge'},
                  'ui':{'download_photos':False}}
        window.core.write_json(window.core.SETTINGS,original)
        with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',root/'missing'),patch.object(window.GLib,'timeout_add_seconds',return_value=0):
            app=window.Window()
        state=ControllerState('hid:demo:a1234','Meu controle',appearance='black',port='1-1',connected=False)
        app.models={state.identity:state}
        failures=[]
        old_hook=sys.excepthook
        def hook(*info):failures.append(info[1]);old_hook(*info)
        sys.excepthook=hook
        settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False)
        source=root/'photo.png'
        image=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,True,8,32,24)
        image.fill(0x334488ff);image.savev(str(source),'png',[],[])

        def exercise(code,theme,font,scenario):
            print('APPEARANCE:',code,theme,font,scenario,flush=True)
            set_language(code);settings.set_property('gtk-theme-name',theme);settings.set_property('gtk-font-name',font)
            window.core.write_json(window.core.SETTINGS,original)
            before=window.core.SETTINGS.read_bytes()
            def drive():
                dialog=next(w for w in Gtk.Window.list_toplevels() if w.get_title()==_('Nome e aparência'))
                try:
                    editor=next(w for w in descendants(dialog) if isinstance(w,AppearanceEditor));gallery=editor.gallery
                    save=dialog.get_widget_for_response(Gtk.ResponseType.OK)
                    cancel=dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
                    assert not save.get_sensitive()
                    assert editor.name.get_accessible().get_name()==_('Nome do controle')
                    assert keyboard.related(editor.name,Atk.RelationType.LABELLED_BY)
                    area=dialog.get_display().get_monitor_at_window(dialog.get_window()).get_workarea()
                    for width,height in ((830,740),(480,448),(640,480)):
                        width=min(width,area.width);height=min(height,area.height-48)
                        dialog.resize(width,height);pump()
                        assert dialog.get_size()==(width,height),(dialog.get_size(),width,height)
                        for item in (save,cancel):inside(item,dialog,True)
                        for item in (editor.name,gallery.search,gallery.group,*[t[0] for t in gallery.tiles.values()]):inside(item,dialog)
                    editor.name.set_text('   ');assert not save.get_sensitive()
                    assert editor.name_help.get_text()==_('Digite um nome para salvar.')
                    editor.name.set_text('  Branco da sala  ');gallery.tiles['white'][0].set_active(True)
                    assert save.get_sensitive() and gallery.selected=='white'
                    editor.name.set_text(state.name);gallery.tiles['black'][0].set_active(True)
                    assert not save.get_sensitive(),'Undoing the draft left Save enabled'
                    editor.name.set_text('  Branco da sala  ');gallery.tiles['white'][0].set_active(True)
                    assert window.core.SETTINGS.read_bytes()==before
                    gallery.search.set_text('no-such-edition');gallery.filter_changed();pump()
                    assert gallery.empty.get_visible() and _('Branco') in gallery.count.get_text()
                    assert gallery.clear.get_mapped() and gallery.empty.get_children()[0].get_mapped(),'Empty-result actions are hidden'
                    responses=[];dialog.connect('response',lambda d,r:responses.append(r))
                    gallery.search.grab_focus();dialog.get_window().focus(Gdk.CURRENT_TIME)
                    keyboard.key(dialog,Gdk.KEY_Return)
                    assert not responses,'Searching submitted the form'
                    gallery.clear.grab_focus();keyboard.key(dialog,Gdk.KEY_space);pump()
                    assert not gallery.empty.get_visible() and gallery.selected=='white'
                    assert dialog.get_focus() is gallery.search
                    gallery.refresh_picture('white');pump()
                    assert dialog.get_focus() is gallery.search and editor.name.get_text()=='  Branco da sala  '
                    selected=gallery.tiles['white'][0]
                    selected.grab_focus();pump()
                    scroll=next(w for w in descendants(dialog) if isinstance(w,Gtk.ScrolledWindow))
                    x,y=selected.translate_coordinates(scroll,0,0)
                    assert y>=0 and y+selected.get_allocated_height()<=scroll.get_allocated_height(),(y,selected.get_allocated_height(),scroll.get_allocated_height())
                    keyboard.key(dialog,Gdk.KEY_space)
                    assert gallery.selected=='white' and selected.get_active(),'Selected model was deselected'
                    if args.output and code=='pt-BR' and scenario=='cancel':
                        gallery.group.set_active_id('Cores');gallery.search.set_text('');gallery.filter_changed()
                        scroll.get_vadjustment().set_value(0);pump()
                        args.output.mkdir(parents=True,exist_ok=True)
                        w,h=dialog.get_size()
                        Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,w,h).savev(str(args.output/f'appearance-{theme}-{font.replace(" ","-")}-{dialog.get_scale_factor()}x.png'),'png',[],[])
                    if scenario=='photos':
                        def photos():
                            photo_dialog=next(w for w in Gtk.Window.list_toplevels() if w.get_title()==_('Fotos dos controles'))
                            try:
                                width,height=photo_dialog.get_size();assert width<=area.width and height<=area.height
                                inside(photo_dialog.get_widget_for_response(Gtk.ResponseType.CLOSE),photo_dialog,True)
                                add=next(w for w in descendants(photo_dialog) if isinstance(w,Gtk.Button) and w.get_label()==_('Adicionar ou substituir foto…'))
                                chooser=Mock();chooser.run.return_value=Gtk.ResponseType.CANCEL
                                with patch.object(window.Gtk,'FileChooserDialog',return_value=chooser):add.clicked()
                                assert not artwork.photo_path('white')
                                chooser.run.return_value=Gtk.ResponseType.OK;chooser.get_filename.return_value=str(source)
                                with patch.object(window.Gtk,'FileChooserDialog',return_value=chooser):add.clicked()
                                assert artwork.photo_path('white').read_bytes()==source.read_bytes()
                                assert artwork.photo_path('black') is None
                                # A corrupt replacement cannot destroy the working image.
                                bad=root/'bad.png';bad.write_text('broken');chooser.get_filename.return_value=str(bad)
                                with patch.object(window.Gtk,'FileChooserDialog',return_value=chooser):add.clicked()
                                assert artwork.photo_path('white').read_bytes()==source.read_bytes()
                                assert window.core.SETTINGS.read_bytes()==before
                            except BaseException as exc:failures.append(exc)
                            photo_dialog.response(Gtk.ResponseType.CLOSE);return False
                        GLib.timeout_add(60,photos);editor.library.clicked()
                        dialog.response(Gtk.ResponseType.CANCEL)
                    elif scenario=='save':
                        # Simulate a port move and a separate settings change during the modal.
                        state.port='9-4'
                        data=window.core.settings();data['ui']['download_photos']=True
                        data['names']['hid:demo:b5678']='Outro, atualizado'
                        window.core.write_json(window.core.SETTINGS,data)
                        dialog.response(Gtk.ResponseType.OK)
                    elif scenario=='retry':
                        real_write=window.core.write_json
                        writes=patch.object(window.core,'write_json',side_effect=OSError('simulated full disk'));writes.start()
                        def retry():
                            writes.stop()
                            try:
                                assert any(isinstance(w,Gtk.Label) and w.get_text()==_('Não foi possível salvar. Suas alterações continuam aqui; tente novamente.') for w in descendants(dialog))
                                assert window.core.SETTINGS.read_bytes()==before and editor.name.get_text()=='  Branco da sala  '
                                assert window.core.write_json is real_write
                            except BaseException as exc:failures.append(exc)
                            dialog.response(Gtk.ResponseType.OK);return False
                        GLib.timeout_add(80,retry);dialog.response(Gtk.ResponseType.OK)
                    else:
                        cancel.grab_focus();keyboard.key(dialog,Gdk.KEY_Escape)
                        assert responses and responses[-1] in (Gtk.ResponseType.CANCEL,Gtk.ResponseType.DELETE_EVENT)
                except BaseException as exc:failures.append(exc);dialog.response(Gtk.ResponseType.CANCEL)
                return False
            GLib.timeout_add(60,drive)
            with patch.object(app,'refresh'),patch.object(window.subprocess,'Popen') as spawn,patch.object(app,'run') as commands:
                app.rename_dialog(state.identity)
                spawn.assert_not_called();commands.assert_not_called()
            if failures:raise failures[0]
            after=window.core.settings()
            assert after['modes']==original['modes']
            assert app.photo_gallery is None
            if scenario in ('save','retry'):
                assert after['names'][state.identity]=='Branco da sala' and after['appearance'][state.identity]=='white'
            else:assert window.core.SETTINGS.read_bytes()==before
            if scenario=='save':
                assert after['ui']['download_photos'] and after['names']['hid:demo:b5678']=='Outro, atualizado'
            if scenario=='photos':
                assert artwork.photo_path('white').read_bytes()==source.read_bytes()
                artwork.photo_path('white').unlink()

        try:
            for code in ('pt-BR','en','es'):
                for theme,font in (('Adwaita','Sans 10'),('HighContrast','Sans 16')):
                    exercise(code,theme,font,'cancel')
                for scenario in ('save','retry','photos'):exercise(code,'Adwaita','Sans 10',scenario)
            assert not failures
        finally:
            sys.excepthook=old_hook;app.destroy()
        print('APPEARANCE OK: three languages, small windows, large fonts, keyboard, drafts/cancel/save/retry, stable identity and merged settings, shared photos; no USB commands.')


if __name__=='__main__':main()
