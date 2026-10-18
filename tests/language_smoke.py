# SPDX-License-Identifier: GPL-3.0-only
"""Live language changes preserve USB processes and preferences. No hardware."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix='dualsense-language-') as temporary:
    root=Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),XDG_DATA_HOME=str(root/'data'))
    import window
    import i18n
    i18n.set_language('pt-BR')
    from gi.repository import Gtk
    from presentation import ControllerState
    from ui import EffectsEditor, AppearanceGallery, label
    from input_view import InputPanel

    usb=root/'usb';usb.mkdir()
    original={'ui':{'download_photos':False},'names':{'sample':'Meu controle'},'modes':{'sample':'charge'},'effects':{'sample':{'triggers':'firm'}}}
    original['protection']={'enabled':False,'allow_manual_play':True,'play_exceptions':['sample']}
    window.core.write_json(window.core.SETTINGS,original)
    with patch.object(window.core,'USB',usb),patch.object(window.core,'migrate_legacy'),patch.object(window.GLib,'timeout_add_seconds',return_value=0):
        app=window.Window()
    state=ControllerState('sample','Meu controle',port='1-1',requested='charge',effective='charge',confirmed=True,fresh=True,reading={'status':'Charging','capacity':55})
    second=ControllerState('second','Outro controle',requested='charge',effective='charge',confirmed=True,fresh=True)
    app.models={'sample':state,'second':second}
    app.dashboard.update(list(app.models.values()),True)
    app.dashboard.select_controller('second')
    process=Mock();process.poll.return_value=None
    streams={'1-1':process};app.streams=streams
    before=window.core.settings()
    for code, mode in [('en','Charge only'),('es','Solo cargar'),('pt-BR','Só carregar')]:
        # Exercise the actual selector callback and rebuild without a USB refresh.
        with patch.object(app,'stop_all') as stop,patch.object(window.subprocess,'Popen') as spawn,patch.object(app,'refresh') as refresh:
            app.dashboard.language_choice.set_active_id(code)
            while Gtk.events_pending():Gtk.main_iteration_do(False)
            assert i18n.language()==code
            assert app.dashboard.language_choice.get_active_id()==code
            assert app.dashboard.items['sample'].mode_buttons['charge'].get_label()=='✓  '+mode
            assert app.dashboard.selected=='second', 'Language change must preserve the selected controller'
            assert app.streams is streams
            process.stdin.write.assert_not_called()
            stop.assert_not_called();spawn.assert_not_called();refresh.assert_not_called()
        after=window.core.settings()
        for field in ('names','modes','effects','protection'):assert after[field]==before[field]
        assert after['ui']['language']==code
        assert i18n.saved_language()==code
        assert app.dashboard.allow_play.get_active() and not app.dashboard.allow_play.get_sensitive()
        assert label('Branco').get_text()=='Branco', 'User-provided names must not be translated implicitly'
        gallery=AppearanceGallery(local_images=False)
        gallery.group.set_active_id('Cores');gallery.search.set_text('Midnight');gallery.filter_changed()
        assert gallery.includes(gallery.tiles['black'][3]), 'Display translation changed filter IDs'
        gallery.search.set_text(i18n._('Branco'));gallery.filter_changed()
        assert gallery.includes(gallery.tiles['white'][3]), 'Search must accept translated appearance names'
        gallery.destroy()
        editor=EffectsEditor({'triggers':'firm'})
        assert editor.values()['triggers']=='firm', 'Display language changed protocol value'
        editor.destroy()
        panel=InputPanel();panel.update({'buttons':['L1'],'sticks':[128]*4,'triggers':[0,255]})
        assert panel.current.get_text().startswith(i18n._('Pressionado agora: '))
        panel.destroy()
    with patch.object(app,'refresh') as refresh:
        app.dashboard.guard.set_active(True)
        assert app.dashboard.allow_play.get_sensitive()
        app.dashboard.guard.set_active(False)
        assert not app.dashboard.allow_play.get_sensitive()
        assert app.dashboard.allow_play.get_active()
        assert refresh.call_count==2
    assert window.core.settings()['protection']==before['protection']
    app.streams={};app.destroy()
    print('LANGUAGE OK: pt-BR/en/es live selector, persistence, translated controls, stable filter/protocol IDs; no USB restart or writes.')
