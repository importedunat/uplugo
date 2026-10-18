# SPDX-License-Identifier: GPL-3.0-only
"""Diagnostic UI with synthetic state and a private X clipboard; no host USB."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='dualsense-diagnostic-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    import doctor
    from gi.repository import Gtk,GLib,Gdk
    from presentation import ControllerState
    from i18n import _,set_language
    from tests.display_smoke import pump
    def descendants(widget):
        yield widget
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():yield from descendants(child)
    usb=root/'usb';usb.mkdir()
    window.core.write_json(window.core.SETTINGS,{'ui':{'download_photos':False},'modes':{'hid:private-serial':'charge'}})
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window,'HELPER',root/'absent'),patch.object(window.GLib,'timeout_add_seconds',return_value=0):
        app=window.Window()
    state=ControllerState('hid:private-serial','private name',port='1-9',connected=True,requested='charge')
    app.models={state.identity:state}
    before=window.core.SETTINGS.read_bytes();failures=[]
    Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
    dependencies=[{'name':'Required A','ok':True,'required':True},{'name':'Required B','ok':False,'required':True},{'name':'Optional','ok':False,'required':False}]
    for code in ('pt-BR','en','es'):
        for font in (10,18):
            set_language(code);Gtk.Settings.get_default().set_property('gtk-font-name','Sans '+str(font))
            Gtk.Settings.get_default().set_property('gtk-theme-name','HighContrast' if font==18 else 'Adwaita')
            def drive():
                dialog=next(w for w in Gtk.Window.list_toplevels() if w.get_title()==_('Desenvolvimento e diagnóstico'))
                try:
                    nodes=list(descendants(dialog))
                    detail=next(w for w in nodes if isinstance(w,Gtk.Expander))
                    text=next(w for w in nodes if isinstance(w,Gtk.TextView))
                    actions={w.get_label():w for w in nodes if isinstance(w,Gtk.Button) and w.get_label()}
                    labels=[w for w in nodes if isinstance(w,Gtk.Label)]
                    assert not detail.get_expanded()
                    assert any(w.get_text()==_('Dependências necessárias: {0} de {1} disponíveis').format(1,2)+'\n'+_('Controles conectados nesta leitura: {0}').format(1) for w in labels)
                    for width,height in ((640,620),(480,448)):
                        dialog.resize(width,height);pump(.08)
                        for expanded in (False,True):
                            detail.set_expanded(expanded);pump(.08)
                            assert dialog.get_size()==(width,height),(code,font,dialog.get_size())
                            for key in (_('Atualizar diagnóstico'),_('Copiar diagnóstico'),_('Fechar')):
                                action=actions[key];x,y=action.translate_coordinates(dialog,0,0)
                                assert 0<=x and x+action.get_allocated_width()<=width
                                assert 0<=y and y+action.get_allocated_height()<=height
                    actions[_('Copiar diagnóstico')].clicked();pump(.04)
                    copied=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
                    assert json.loads(copied)['controllers'][0]['requested']=='charge'
                    assert 'private' not in copied and '1-9' not in copied
                    confirmation=next(w for w in labels if w.get_text()==_('✓ Diagnóstico copiado'))
                    assert confirmation.get_mapped()
                    actions[_('Atualizar diagnóstico')].clicked();pump(.04)
                    assert not confirmation.get_visible()
                    assert Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()==copied
                    with patch.object(window.subprocess,'Popen') as launched:
                        actions[_('Abrir laboratório sem USB')].clicked()
                        assert launched.call_count==1 and launched.call_args.args[0][-1].endswith('/development.py')
                    if args.output and code=='pt-BR':
                        detail.set_expanded(False);dialog.resize(640,620);pump(.08)
                        args.output.mkdir(parents=True,exist_ok=True)
                        w=dialog.get_window();Gdk.pixbuf_get_from_window(w,0,0,w.get_width(),w.get_height()).savev(str(args.output/('diagnostic-'+str(font)+'.png')),'png',[],[])
                except BaseException as exc:failures.append(exc)
                dialog.response(Gtk.ResponseType.CLOSE)
                return False
            with patch.object(doctor,'checks',return_value=dependencies):
                GLib.idle_add(drive);app.development_dialog()
            assert window.core.SETTINGS.read_bytes()==before and not app.streams
    app.destroy()
    if failures:raise failures[0]
print('DIAGNOSTIC OK: three languages, fonts 10/18, 480x448, collapsed/expanded report, clipboard feedback/reset, sanitized data, lab launch only on click, no settings or USB changes.')
