# SPDX-License-Identifier: GPL-3.0-only
"""Exercise compatibility choices without constructing a USB session."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)


with tempfile.TemporaryDirectory(prefix='dualsense-profiles-') as temporary:
    root = Path(temporary)
    os.environ.update(XDG_CONFIG_HOME=str(root/'config'), XDG_STATE_HOME=str(root/'state'), XDG_DATA_HOME=str(root/'data'))
    import window
    from i18n import set_language
    set_language("pt-BR")
    from gi.repository import Gtk, GLib, Gdk
    from theme import install_theme
    install_theme()
    from tests.display_smoke import pump
    from tests.accessibility_smoke import key

    app = Gtk.Window()
    app.notice = Gtk.Label()
    original = ['123', 'previous.exe']
    window.core.write_json(window.core.SETTINGS, {'native_games': original, 'modes': {'example': 'charge'}})
    failures = []

    def exercise(scenario):
        def inspect():
            dialog = next(w for w in Gtk.Window.list_toplevels() if w.get_title() == 'Jogos e troca de modo')
            try:
                pump()
                if scenario=='cancel':dialog.resize(480,640);pump()
                width,height=dialog.get_size()
                for response in (Gtk.ResponseType.OK,Gtk.ResponseType.CANCEL):
                    action=dialog.get_widget_for_response(response)
                    x,y=action.translate_coordinates(dialog,0,0)
                    assert action.get_mapped() and x>=0 and x+action.get_allocated_width()<=width and y+action.get_allocated_height()<=height
                if scenario=='preserve_hidden' and '--capture' in sys.argv:
                    Gdk.pixbuf_get_from_window(dialog.get_window(),0,0,width,height).savev(sys.argv[sys.argv.index('--capture')+1]+'.dialog.png','png',[],[])
                widgets = list(descendants(dialog))
                check = next(w for w in widgets if isinstance(w, Gtk.CheckButton))
                text = next(w for w in widgets if isinstance(w, Gtk.TextView))
                advanced = next(w for w in widgets if isinstance(w, Gtk.Expander) and w.get_label().startswith('Adicionar'))
                assert not advanced.get_expanded()
                assert check.get_active()
                assert not dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive()
                check.grab_focus();key(dialog,Gdk.KEY_space)
                assert not check.get_active()
                assert dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive()
                if scenario == 'cancel':
                    text.get_buffer().set_text('replacement.exe')
                    dialog.response(Gtk.ResponseType.CANCEL)
                elif scenario == 'save_error':
                    text.get_buffer().set_text('replacement.exe')
                    failure=patch.object(window.core,'write_json',side_effect=OSError('read-only fixture'))
                    failure.start()
                    dialog.response(Gtk.ResponseType.OK)
                    def recover():
                        try:
                            assert window.core.settings()['native_games']==original
                            assert text.get_buffer().get_text(text.get_buffer().get_start_iter(),text.get_buffer().get_end_iter(),True)=='replacement.exe'
                            assert any(isinstance(w,Gtk.Label) and 'Suas alterações continuam aqui' in w.get_text() and w.get_visible() for w in descendants(dialog))
                        except BaseException as exc:failures.append(exc)
                        finally:failure.stop();dialog.response(Gtk.ResponseType.CANCEL)
                        return False
                    GLib.idle_add(recover)
                elif scenario == 'preserve_hidden':
                    # Saving a checklist change must retain collapsed manual entries.
                    dialog.response(Gtk.ResponseType.OK)
                else:
                    text.get_buffer().set_text('/invalid/path.exe')
                    dialog.response(Gtk.ResponseType.OK)

                    def retry():
                        try:
                            assert advanced.get_expanded()
                            assert window.core.settings()['native_games'] == original
                            # A background change while editing must not be overwritten.
                            data = window.core.settings()
                            data['modes']['example'] = 'proxy'
                            window.core.write_json(window.core.SETTINGS, data)
                            text.get_buffer().set_text('456\nNewGame.exe')
                            dialog.response(Gtk.ResponseType.OK)
                        except BaseException as exc:
                            failures.append(exc)
                            dialog.response(Gtk.ResponseType.CANCEL)
                        return False

                    GLib.idle_add(retry)
            except BaseException as exc:
                failures.append(exc)
                dialog.response(Gtk.ResponseType.CANCEL)
            return False

        GLib.idle_add(inspect)
        with patch.object(window, 'installed_games', return_value={'123': 'Installed game'}):
            window.Window.profiles_dialog(app)
        if failures:
            raise failures[0]

    exercise('cancel')
    assert window.core.settings()['native_games'] == original
    exercise('save_error')
    assert window.core.settings()['native_games'] == original
    exercise('preserve_hidden')
    assert window.core.settings()['native_games'] == ['previous.exe']
    data = window.core.settings()
    data['native_games'] = original
    window.core.write_json(window.core.SETTINGS, data)
    exercise('retry')
    assert window.core.settings()['native_games'] == ['456', 'NewGame.exe']
    assert window.core.settings()['modes']['example'] == 'proxy'
    app.destroy()
    print('PROFILES OK: cancel, collapsed entries preserved, validation retry, concurrent settings preserved; no USB access.')

# The draft editor remains navigable with large libraries and translated text.
from profiles_ui import GameProfileEditor
from tests.display_smoke import pump
from theme import install_theme
from ui import style
from gi.repository import Gdk
from game_profiles import parse_profiles
install_theme()
for code in ('pt-BR','en','es'):
    set_language(code)
    for width,font in ((720,'Sans 10'),(436,'Sans 16')):
        Gtk.Settings.get_default().set_property('gtk-font-name',font)
        host=style(Gtk.Window(),'dualsense');host.set_decorated(False);host.set_default_size(width,720)
        games={'123':'FINAL FANTASY XV','456':'Jogo com ação','789':'Game with a very long name '*3}
        games.update({str(i):'Example game '+str(i) for i in range(1000,1100)})
        editor=GameProfileEditor(games,['123','previous.exe'])
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.add(editor);host.add(scroll);host.show_all();editor.filter_games();pump()
        assert host.get_size()[0]==width,(code,font,host.get_size())
        editor.search.set_text('ACAO');editor.filter_games();pump()
        assert editor.checks['456'].get_visible() and not editor.checks['123'].get_visible()
        assert editor.checks['123'].get_active()
        editor.checks['456'].set_active(True)
        assert parse_profiles(editor.profile_text())==['123','456','previous.exe']
        editor.search.set_text('nothing matches');editor.filter_games();pump()
        assert editor.empty.get_visible() and editor.clear.get_visible()
        editor.clear.clicked();editor.filter_games();pump()
        assert editor.checks['123'].get_visible() and editor.checks['456'].get_active()
        assert not editor.empty.get_visible()
        if '--capture' in sys.argv and code=='pt-BR' and width==720:
            Gdk.pixbuf_get_from_window(host.get_window(),0,0,*host.get_size()).savev(sys.argv[sys.argv.index('--capture')+1],'png',[],[])
        host.destroy();pump()
    empty=GameProfileEditor({},['old.exe']);empty.show_all();empty.filter_games()
    assert not empty.search.get_sensitive() and empty.empty.get_visible()
    assert parse_profiles(empty.profile_text())==['old.exe']
    empty.manual.get_buffer().set_text('');assert '0' not in empty.summary.get_text() and parse_profiles(empty.profile_text())==[]
    empty.destroy()
print('GAME EDITOR OK: three languages, 103 games, narrow/large font, accent search, hidden choices retained, clear and empty state.')
