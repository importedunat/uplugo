# SPDX-License-Identifier: GPL-3.0-only
"""Input pages at narrow widths and large fonts, using synthetic samples only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.display_smoke import Gtk, pump, set_language, install_theme
from ui import themed_dialog
from input_view import InputPanel, attach_input_panel
from i18n import _

install_theme()
settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False)
for code in ('pt-BR','en','es'):
    for font in (10,18):
        set_language(code);settings.set_property('gtk-font-name','Sans '+str(font))
        settings.set_property('gtk-theme-name','HighContrast' if font==18 else 'Adwaita')
        dialog=themed_dialog(_('Testar botões'),None,700)
        close=dialog.add_button(_('Concluir'),Gtk.ResponseType.CLOSE)
        panel=InputPanel();attach_input_panel(dialog,panel);dialog.show_all()
        panel.update({'buttons':['×','L2'],'observed':['×','L2','Options'],
                      'sticks':[0,255,128,128],'triggers':[180,0],
                      'touches':[{'slot':0,'id':1,'x':700,'y':350}]})
        tabs=panel.tabs.get_children()
        for width in (760,480,760):
            dialog.resize(width,640);pump(.06)
            for page,detail in (('controller',panel.details),('analogs',panel.analog.detail),('motion',panel.motion.detail)):
                panel.pages.set_visible_child_name(page)
                for expanded in (False,True):
                    detail.set_expanded(expanded);pump(.06)
                    assert dialog.get_size()[0]==width,(code,font,width,page,dialog.get_size())
                    assert panel.get_allocated_width()<=width-44,(code,font,width,page,panel.get_allocated_width())
                    assert close.translate_coordinates(dialog,0,0)[1]+close.get_allocated_height()<=dialog.get_allocated_height()
                    assert panel.tabs.get_children()==tabs,'Reflow replaced tabs'
                    for widget in (panel.tabs,panel.pages,panel.pages.get_visible_child()):
                        x,y=widget.translate_coordinates(dialog,0,0)
                        assert x>=0 and x+widget.get_allocated_width()<=width,(type(widget).__name__,page,width)
        dialog.destroy();pump(.02)
print('INPUT LAYOUT OK: all three pages and languages, 10/18 font, 480/760 widths, expanded details, dark/high contrast, stable tabs and visible close.')
