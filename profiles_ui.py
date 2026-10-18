# SPDX-License-Identifier: GPL-3.0-only
"""Draft-only game choices. No process detection, USB commands or writes."""
import unicodedata
from gi.repository import Gtk
from i18n import _
from game_profiles import parse_profiles
from ui import label, icon, style, accessible, button


def search_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))


class GameProfileEditor(Gtk.Box):
    def __init__(self,games,saved):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.set_valign(Gtk.Align.START)
        self.checks={};self.names=games
        self.pack_start(label(_('Seus ajustes no dia a dia. Os efeitos do jogo quando precisar.'),'controller-name',wrap=True),False,False,0)
        self.pack_start(label(_('Use se você joga com as cores e os gatilhos do app, mas prefere que um jogo específico cuide dos efeitos. Marque esse jogo para trocar de modo automaticamente.'),'muted',wrap=True),False,False,0)
        route=style(Gtk.FlowBox(),'game-route');route.set_selection_mode(Gtk.SelectionMode.NONE)
        route.set_min_children_per_line(1);route.set_max_children_per_line(3);route.set_homogeneous(True)
        route.set_column_spacing(8);route.set_row_spacing(8)
        for number,when,mode,symbol in ((1,_('Antes de abrir'),_('Minhas configurações'),'preferences-system-symbolic'),
                                       (2,_('Jogo aberto'),_('Configurações do jogo'),'input-gaming-symbolic'),
                                       (3,_('Ao fechar'),_('Minhas configurações'),'edit-undo-symbolic')):
            step=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5),'game-step')
            image=icon(symbol,24);step.pack_start(image,False,False,0)
            caption=label(str(number)+' · '+when,'muted','small',wrap=True);caption.set_xalign(.5);caption.set_max_width_chars(18)
            title=label(mode,'setting-title',wrap=True);title.set_xalign(.5);title.set_max_width_chars(18)
            step.pack_start(caption,False,False,0);step.pack_start(title,False,False,0);route.add(step)
        self.pack_start(route,False,False,0)
        guard=Gtk.Box(spacing=8);guard.pack_start(icon('battery-symbolic'),False,False,0)
        guard.pack_start(label(_('Só carregar não muda.'),'setting-title',wrap=True),False,False,0)
        self.pack_start(guard,False,False,0)
        self.pack_start(label(_('A troca vale para todos os controles em Minhas configurações.'),'muted','small',wrap=True),False,False,0)
        self.pack_start(label(_('É opcional: para jogar, basta escolher um modo na tela inicial e abrir o jogo normalmente.'),'muted','small',wrap=True),False,False,0)
        self.pack_start(label(_('Usar os efeitos do jogo ao abrir:'),'setting-title',wrap=True),False,False,0)
        self.search=Gtk.SearchEntry();self.search.set_placeholder_text(_('Buscar jogo…'))
        accessible(self.search,_('Buscar jogos instalados'));self.pack_start(self.search,False,False,0)
        self.choices=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2)
        for appid,name in games.items():
            check=style(Gtk.CheckButton(),'game-choice');caption=label(name,wrap=True);caption.set_max_width_chars(38)
            check.add(caption);check.set_active(appid in saved);accessible(check,name,_('Usar Configurações do jogo enquanto este jogo estiver aberto.'))
            self.choices.pack_start(check,False,False,0);self.checks[appid]=check
            check.connect('toggled',lambda w:self.update_summary())
        self.empty=label(_('Nenhum jogo encontrado.'),'muted',wrap=True);self.empty.set_no_show_all(True)
        self.choices.pack_start(self.empty,False,False,12)
        self.clear=button(_('Limpar busca'),lambda w:self.search.set_text(''),'quiet');self.clear.set_no_show_all(True)
        self.choices.pack_start(self.clear,False,False,0)
        game_scroll=Gtk.ScrolledWindow();game_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        game_scroll.set_min_content_height(min(140,max(48,len(games)*42)));game_scroll.set_max_content_height(180);game_scroll.set_propagate_natural_height(True)
        game_scroll.add(self.choices);self.pack_start(game_scroll,False,False,0)
        self.summary=label('','muted','small',wrap=True);self.pack_start(self.summary,False,False,0)
        self.search.connect('search-changed',lambda w:self.filter_games())
        if not games:
            self.search.set_sensitive(False)
            self.empty.set_text(_('Nenhum jogo da Steam encontrado nesta instalação. Você pode adicionar um jogo abaixo.'))
        extra=[p for p in saved if p not in games]
        self.advanced=Gtk.Expander(label=_('Adicionar outro jogo (avançado)')+(_(' · {0} salvo(s)').format(len(extra)) if extra else ''))
        self.advanced.get_label_widget().set_line_wrap(True);self.advanced.get_label_widget().set_max_width_chars(24)
        manual=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        manual.pack_start(label(_('Um ID da Steam ou nome de arquivo .exe por linha. Não coloque caminhos nem comandos.'),'small',wrap=True),False,False,0)
        manual.pack_start(label(_('O ID é o número após /app/ no endereço da página do jogo na loja Steam. Fora da Steam, use o nome do executável, como jogo.exe.'),'muted','small',wrap=True),False,False,0)
        self.manual=Gtk.TextView();self.manual.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        accessible(self.manual,_('IDs da Steam ou nomes de executáveis, um por linha'))
        self.manual.get_buffer().set_text('\n'.join(extra))
        manual_scroll=Gtk.ScrolledWindow();manual_scroll.set_min_content_height(75);manual_scroll.add(self.manual)
        manual.pack_start(manual_scroll,False,False,0);self.advanced.add(manual);self.pack_start(self.advanced,False,False,0)
        details=Gtk.Expander(label=_('Quando usar e o que muda?'))
        details.get_label_widget().set_line_wrap(True);details.get_label_widget().set_max_width_chars(24)
        details.add(label(_('Exemplo: você usa sua cor favorita, mas quer sentir os gatilhos e as vibrações que um jogo compatível oferece. Marque esse jogo aqui. Se você sempre usa Configurações do jogo, pode deixar a lista vazia.\n\nEm Configurações do jogo, suas cores, vibração e peso dos gatilhos ficam pausados: a Steam e o jogo controlam os efeitos. Ao voltar para Minhas configurações, seus ajustes retornam.\n\nA troca reconecta o controle ao sistema. Se o jogo não reconhecer a troca, escolha Configurações do jogo antes de abri-lo. Alguns jogos também exigem desativar Steam Input nas propriedades do jogo na Steam.'),'muted','small',wrap=True))
        self.pack_start(details,False,False,0)
        self.pack_start(label(_('Jogos instalados na Steam. Estar nesta lista não confirma suporte aos efeitos do DualSense.'),'muted','small',wrap=True),False,False,0)
        self.manual.get_buffer().connect('changed',lambda b:self.update_summary())
        self.filter_games();self.update_summary()

    def filter_games(self):
        query=search_key(self.search.get_text().strip());visible=0
        for appid,check in self.checks.items():
            show=query in search_key(self.names[appid]);check.set_no_show_all(not show);check.set_visible(show);visible+=show
        self.empty.set_visible(not visible);self.clear.set_visible(bool(query))

    def update_summary(self):
        callback=getattr(self,'on_change',None)
        if callback:callback()
        try:count=len(parse_profiles(self.profile_text()))
        except ValueError:
            self.summary.set_text(_('Revise os jogos adicionados manualmente.'));return
        self.summary.set_text(_('Jogos escolhidos: {0}').format(count) if count else _('Nenhum jogo escolhido · troca automática desligada.'))

    def profile_text(self):
        buffer=self.manual.get_buffer()
        return '\n'.join(appid for appid,check in self.checks.items() if check.get_active())+'\n'+buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)

    def do_get_preferred_width_for_height(self,height):return self.get_preferred_width()
