# SPDX-License-Identifier: GPL-3.0-only
"""Contextual GTK help. Reading this guide never sends controller commands."""
from gi.repository import Gtk
from i18n import _


class ModeGuide(Gtk.Box):
    def __init__(self):
        from ui import label, style
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=18)
        self.pack_start(label(_('Escolha o que você quer fazer'),'controller-name',wrap=True),False,False,0)
        self.pack_start(label(_('Cada controle tem seu próprio modo. Consultar esta ajuda não muda nenhum deles.'),'muted',wrap=True),False,False,0)
        entries=[
            (_('Quero carregar sem aparecer nos jogos'),_('Só carregar'),
             _('A Steam e os jogos deixam de receber este controle. Luzes, vibração e resistência adicional ficam desligadas. A bateria continua sendo lida.')),
            (_('Quero jogar com minhas luzes e efeitos'),_('Minhas configurações'),
             _('Os jogos recebem um DualSense virtual. Suas cores, vibração e resistência dos gatilhos têm prioridade. Se o jogo não responder, confira o mapeamento dele.')),
            (_('Quero os recursos nativos do jogo'),_('Configurações do jogo'),
             _('O jogo recebe o controle físico e controla os efeitos. Prefira este modo para áudio e háptica USB nativa. Suas personalizações do app ficam pausadas.')),
        ]
        for intent,mode,description in entries:
            row=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6),'guide-choice')
            row.pack_start(label(intent,'setting-title',wrap=True),False,False,0)
            row.pack_start(label(mode,'guide-mode'),False,False,0)
            row.pack_start(label(description,'muted','small',wrap=True),False,False,0)
            self.pack_start(row,False,False,0)
        advanced=Gtk.Expander(label=_('O jogo não reconhece os botões?'))
        advanced.add(label(_('Confira se o controle está em um modo de jogo. No PCSX2, abra Settings → Controllers, habilite SDL e escolha o DualSense em Controller Port 1 → Automatic Mapping. Outros jogos podem precisar de um mapeamento próprio.\n\nModo por jogo é opcional: automatiza a troca entre seus efeitos e os efeitos de jogos escolhidos. Para jogar, você não precisa cadastrar nenhum jogo.'),'muted','small',wrap=True))
        self.pack_start(advanced,False,False,0)
        self.pack_start(label(_('Só carregar não aumenta a potência da porta USB. Com o computador desligado, a alimentação depende do hardware e das configurações dele.'),'dialog-note',wrap=True),False,False,0)


def mode_guide_dialog(parent):
    from ui import themed_dialog
    dialog=themed_dialog(_('Qual modo usar?'),parent,610)
    display=dialog.get_display()
    monitor=display.get_monitor_at_window(parent.get_window()) if parent and parent.get_window() else display.get_primary_monitor()
    monitor=monitor or display.get_monitor(0)
    area=monitor.get_workarea() if monitor else None
    dialog.set_default_size(min(610,max(320,area.width-64)) if area else 610,
                            min(650,max(240,area.height-64)) if area else 650)
    dialog.add_button(_('Entendi'),Gtk.ResponseType.CLOSE)
    content=ModeGuide()
    scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
    scroll.add(content);dialog.get_content_area().pack_start(scroll,True,True,0)
    return dialog


class InterfaceTour:
    """Anchored, dismissible guidance. Never invokes the highlighted actions."""
    def __init__(self,dashboard):
        self.dashboard=dashboard;self.popup=None;self.target=None;self.index=0;self.closed=False
        from i18n import _
        card=dashboard.items.get(dashboard.selected)
        self.steps=[(dashboard.help,_('Conhecer o app'),_('Siga os destaques. Este guia não muda os modos nem aciona os controles.'))]
        if card:
            self.steps += [
                (dashboard.selector_row,_('Escolha um controle'),_('Cada controle tem seus próprios ajustes. O seletor mostra a bateria e o modo dos dois.')),
                (card.appearance_button,_('Reconheça seu controle'),_('Aqui você muda nome e aparência. Identificar controle pisca as luzes para localizar o controle físico.')),
                (card.mode_buttons['charge'].get_parent(),_('Escolha como usar'),_('Só carregar: fora dos jogos. Minhas configurações: seus efeitos. Configurações do jogo: efeitos e recursos nativos do jogo.')),
                (card.tools,_('Dê seu toque e confira os comandos'),_('Luzes e efeitos muda a cor, a vibração e o peso dos gatilhos. Se um botão não responde no jogo, Testar botões ajuda a conferir se o app recebe esse comando.')),
                (card.touchpad,_('Touchpad sem surpresas'),_('Escolha se o touchpad pode mover o cursor do Linux. Isso é separado do clique usado pelo jogo.')),
                (card.details,_('Acompanhe a bateria'),_('Veja a última leitura e o histórico de carga. Uma porcentagem antiga fica identificada; o app não mede a potência do cabo.')),
            ]
        else:
            self.steps.append((dashboard.stack,_('Conecte um controle'),_('Use um cabo USB de dados. O controle aparece aqui automaticamente. Bluetooth ainda não é suportado.')))
        self.steps += [
            (dashboard.compatibility,_('Seus efeitos ou os do jogo?'),_('Usa seus próprios efeitos, mas quer os efeitos nativos em um jogo específico? Modo por jogo faz essa troca ao abrir e fechar o jogo. É opcional; Só carregar permanece igual.')),
            (dashboard.preferences,_('Ajuste o app'),_('Idioma, fotos, acesso USB e diagnóstico ficam aqui. Você pode refazer este guia pelo botão Ajuda.')),
            (dashboard.footer_note,_('Continue na bandeja'),_('Fechar a janela mantém os modos ativos na bandeja. Para encerrar e liberar os controles, use Preferências.')),
        ]
        self.show(0)

    def show(self,index):
        from ui import style,label,button,accessible
        from gi.repository import Gtk
        if self.closed:return
        self.clear()
        self.index=index;target,title,body=self.steps[index];self.target=target
        target.get_style_context().add_class('tour-focus')
        page=self.dashboard.scroll.get_child().get_child()
        point=target.translate_coordinates(page,0,0)
        if point and target.is_ancestor(page):
            adjustment=self.dashboard.scroll.get_vadjustment()
            y=point[1];height=target.get_allocated_height();span=adjustment.get_page_size()
            adjustment.set_value(max(adjustment.get_lower(),min(y-max(0,(span-height)/2),adjustment.get_upper()-span)))
        anchor=target if target.get_sensitive() else target.get_parent()
        popup=self.popup=style(Gtk.Popover.new(anchor),'dualsense','tour-popover')
        popup.set_position(Gtk.PositionType.BOTTOM);popup.set_modal(True)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);box.set_border_width(16)
        heading=Gtk.Box(spacing=8)
        number=label(f'{index+1} / {len(self.steps)}','muted','small');heading.pack_start(number,True,True,0)
        close=button('×',lambda b:self.close(),'quiet');accessible(close,_('Fechar ajuda'))
        heading.pack_end(close,False,False,0);box.pack_start(heading,False,False,0)
        caption=label(title,'setting-title',wrap=True);caption.set_max_width_chars(24)
        detail=label(body,'muted','small',wrap=True);detail.set_max_width_chars(32)
        box.pack_start(caption,False,False,0);box.pack_start(detail,False,False,0)
        actions=Gtk.Box(spacing=8)
        self.back=button(_('Anterior'),lambda b:self.show(index-1),'quiet');self.back.set_sensitive(index>0)
        self.next=button(_('Concluir') if index==len(self.steps)-1 else _('Próximo'),lambda b:self.close() if index==len(self.steps)-1 else self.show(index+1),'primary')
        actions.pack_start(self.back,False,False,0);actions.pack_end(self.next,False,False,0)
        box.pack_start(actions,False,False,0);popup.add(box);box.show_all()
        accessible(popup,title,body)
        popup.connect('closed',lambda widget:self.close() if self.popup is widget else None)
        popup.popup();self.next.grab_focus()

    def clear(self):
        if self.target:self.target.get_style_context().remove_class('tour-focus');self.target=None
        popup=self.popup;self.popup=None
        if popup:popup.destroy()

    def close(self,focus=True):
        if self.closed:return
        self.closed=True;self.clear()
        if focus and self.dashboard.help.get_mapped():self.dashboard.help.grab_focus()
