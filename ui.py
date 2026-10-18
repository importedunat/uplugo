# SPDX-License-Identifier: GPL-3.0-only
"""GTK presentation widgets. No USB access or persistent writes here."""
from pathlib import Path
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango, Atk, GObject
from presentation import MODES, mode_consequence, mode_hint, AccessSetup
import artwork
from i18n import _, LANGUAGES, language
from layout import AdaptiveBox

ASSETS = Path(__file__).resolve().parent/'assets'
TONES = {'cyan':'#75a9ff', 'purple':'#75a9ff', 'amber':'#ffc879',
         'error':'#ff9fb4', 'muted':'#7888a7'}


def style(widget, *names):
    for name in names: widget.get_style_context().add_class(name)
    return widget


def label(text='', *classes, wrap=False):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_line_wrap(wrap)
    if wrap:
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        widget.set_max_width_chars(40)
    return style(widget, *classes)


def button(text, callback, *classes):
    widget = style(Gtk.Button(label=text), *classes)
    widget.get_child().set_line_wrap(True)
    widget.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    widget.connect('clicked', callback)
    return widget



def purpose_button(title, purpose, symbol, callback):
    """Keep the reason for a tool visible, including for keyboard users."""
    widget=style(Gtk.Button(),'tool-action')
    content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
    content.pack_start(icon(symbol,22),False,False,0)
    heading=label(title,wrap=True);heading.set_xalign(.5);heading.set_max_width_chars(18)
    detail=label(purpose,'muted','small',wrap=True);detail.set_xalign(.5);detail.set_max_width_chars(20)
    content.pack_start(heading,False,False,0);content.pack_start(detail,False,False,0)
    widget.add(content);widget.connect('clicked',callback)
    accessible(widget,title,purpose)
    return widget


class ModeButton(Gtk.Button):
    """Mode tab with a title and a one-line consequence; get_label() is the title."""
    def __init__(self, key, image, hint):
        super().__init__()
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
        content.pack_start(icon(image,22),False,False,0)
        self.title,self.hint=Gtk.Label(),Gtk.Label(label=hint)
        for line,name in ((self.title,'mode-name'),(self.hint,'mode-hint')):
            style(line,name);line.set_xalign(.5);line.set_justify(Gtk.Justification.CENTER)
            line.set_line_wrap(True);line.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);line.set_max_width_chars(18)
            content.pack_start(line,False,False,0)
        self.add(content)

    def get_label(self):
        return self.title.get_text()

    def set_label(self, text):
        self.title.set_text(text)


def icon(name, size=18):
    widget = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.BUTTON)
    widget.set_pixel_size(size)
    return widget


def accessible(widget, name, description=None):
    """Keep names stable during polling; emit changes only for new context."""
    obj=widget.get_accessible()
    if obj.get_name()!=name:obj.set_name(name)
    if description is not None and obj.get_description()!=description:
        obj.set_description(description)


def themed_dialog(title, parent, width=510):
    dialog = style(Gtk.Dialog(title=title, transient_for=parent, modal=True), 'dualsense')
    dialog.set_default_size(width, -1)
    content = dialog.get_content_area()
    content.set_border_width(22)
    content.set_spacing(15)
    return dialog


class AppearanceGallery(Gtk.Box):
    """Selection stays a draft until the enclosing dialog is saved."""
    def __init__(self, selected='neutral', local_images=True, on_change=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.selected=selected if selected in artwork.BY_ID else 'neutral'
        self.tiles={};self.titles={};self.local_images=local_images;self.on_change=on_change
        controls=AdaptiveBox(spacing=10)
        self.search=Gtk.SearchEntry();self.search.set_placeholder_text(_('Buscar cor ou edição…'))
        self.search.get_accessible().set_name(_('Buscar modelo do controle'))
        controls.pack_start(self.search,True,True,0)
        self.group=Gtk.ComboBoxText()
        for name in ['Todos','Cores','Edições especiais','DualSense Edge']:self.group.append(name,_(name))
        self.group.set_active_id('Todos');self.group.get_accessible().set_name(_('Filtrar modelos'))
        controls.pack_end(self.group,False,False,0);self.pack_start(controls,False,False,0)
        self.grid=Gtk.FlowBox();self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_min_children_per_line(1);self.grid.set_max_children_per_line(3)
        self.grid.set_column_spacing(10);self.grid.set_row_spacing(10);self.grid.set_homogeneous(True)
        self.grid.set_valign(Gtk.Align.START)
        for entry in [artwork.NEUTRAL,*artwork.MODELS]:
            key=entry['id'];tile=style(Gtk.ToggleButton(),'model-tile')
            tile.set_size_request(190,-1)
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
            picture=Gtk.Image();frame=style(Gtk.EventBox(),'art-frame');frame.add(picture)
            content.pack_start(frame,False,False,0)
            title=label(_(entry['name']),'model-caption',wrap=True);title.set_max_width_chars(24)
            content.pack_start(title,False,False,0);self.titles[key]=title
            origin=label('','muted','small',wrap=True);origin.set_max_width_chars(22)
            content.pack_start(origin,False,False,0)
            tile.add(content);tile.set_active(key==self.selected)
            tile.get_accessible().set_name(_(entry['name']))
            tile.connect('toggled',self.select,key)
            self.tiles[key]=(tile,picture,origin,entry)
            self.refresh_picture(key);self.grid.add(tile)
            tile.get_parent().set_can_focus(False)
        self.grid.set_filter_func(self.matches)
        self.count=label('','gallery-count',wrap=True);self.pack_start(self.count,False,False,0)
        self.empty=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.empty.pack_start(label(_('Nenhum modelo encontrado. Tente outro nome ou limpe os filtros.'),'muted',wrap=True),False,False,0)
        self.clear=button(_('Limpar filtros'),self.clear_filters,'quiet')
        self.empty.pack_start(self.clear,False,False,0);self.empty.show_all()
        self.empty.set_no_show_all(True)
        self.pack_start(self.empty,False,False,0)
        self.pack_start(self.grid,False,False,0)
        self.search.connect('search-changed',self.filter_changed)
        self.group.connect('changed',self.filter_changed)
        self.filter_changed()

    def refresh_picture(self,key):
        tile,picture,origin,entry=self.tiles[key]
        pixbuf,photo=artwork.picture(key,160,102,self.local_images)
        picture.set_from_pixbuf(pixbuf)
        origin.set_text(_('Foto local') if photo else _('Ilustração · foto não adicionada'))

    def select(self,tile,key):
        if not tile.get_active():
            if self.selected==key:tile.set_active(True)
            return
        changed=self.selected!=key;self.selected=key
        for other,(button_,*_) in self.tiles.items():
            if other!=key:button_.set_active(False)
        self.filter_changed()
        if changed and self.on_change:self.on_change()

    def clear_filters(self,*args):
        self.search.set_text('');self.group.set_active_id('Todos')
        self.filter_changed();self.search.grab_focus()

    def includes(self,entry):
        import unicodedata
        def normalized(value):return ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))
        query=normalized(self.search.get_text()).strip()
        group=self.group.get_active_id()
        searchable=' '.join((entry['name'],entry['group'],_(entry['name']),_(entry['group'])))
        return (group=='Todos' or entry['group']==group) and query in normalized(searchable)

    def matches(self,child):
        return any(tile is child.get_child() and self.includes(entry) for tile,_,_,entry in self.tiles.values())

    def filter_changed(self,*args):
        self.grid.invalidate_filter()
        total=sum(self.includes(entry) for *_,entry in self.tiles.values())
        self.count.set_text(_('{0} opções · Selecionado: ').format(total)+_(artwork.model(self.selected)['name']))
        self.empty.set_visible(total==0)
        for key,title in self.titles.items():
            title.set_text(('✓  ' if key==self.selected else '')+_(artwork.model(key)['name']))


class AppearanceEditor(Gtk.Box):
    """Name and model drafts; library management is a separate explicit action."""
    def __init__(self,state,on_change,manage_photos,local_images=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.original_name=state.name.strip()
        self.original_model=state.appearance if state.appearance in artwork.BY_ID else 'neutral'
        self.on_change=on_change
        context=label(state.name+' · '+state.identity[-8:],'muted','small',wrap=True)
        self.pack_start(context,False,False,0)
        caption=label(_('Nome do _controle'),'mode-title');caption.set_use_underline(True)
        self.pack_start(caption,False,False,0)
        self.name=Gtk.Entry();self.name.set_max_length(60);self.name.set_text(state.name)
        self.name.set_activates_default(False);caption.set_mnemonic_widget(self.name)
        accessible(self.name,_('Nome do controle'),_('O nome acompanha este controle mesmo quando você troca a porta USB.'))
        self.name.set_tooltip_text(_('O nome acompanha este controle mesmo quando você troca a porta USB.'))
        self.pack_start(self.name,False,False,0)
        self.name_help=label('','muted','small',wrap=True);self.name_help.set_no_show_all(True)
        self.pack_start(self.name_help,False,False,0)
        heading=AdaptiveBox(spacing=8)
        caption=label(_('Escolha seu modelo'),'mode-title')
        caption.set_tooltip_text(_('A aparência é escolhida por você; o USB não informa a edição. Trocar a imagem não muda o modo do controle.'))
        heading.pack_start(caption,True,True,0);self.pack_start(heading,False,False,0)
        self.photo_hint=label(_('Quer fotos reais? Adicione a sua em Biblioteca de fotos ou ative o download das fotos oficiais em Preferências → Fotos dos controles (desligado por padrão).'),'muted','small',wrap=True)
        self.pack_start(self.photo_hint,False,False,0)
        self.gallery=AppearanceGallery(state.appearance,local_images,self.changed)
        self.pack_start(self.gallery,False,False,0)
        self.library=button(_('Biblioteca de fotos…'),lambda b:manage_photos(self.gallery.selected),'quiet')
        heading.pack_end(self.library,False,False,0)
        self.name.connect('changed',self.changed)
        self.update_help()

    @property
    def valid(self):return bool(self.name.get_text().strip())

    @property
    def dirty(self):
        return self.name.get_text().strip()!=self.original_name or self.gallery.selected!=self.original_model

    def update_help(self):
        self.name_help.set_text(_('Digite um nome para salvar.'))
        self.name_help.set_visible(not self.valid)

    def changed(self,*args):
        self.update_help();self.on_change()


class ControllerSelector(Gtk.ToggleButton):
    """Persistent device navigation; selecting never changes a hardware mode."""
    def __init__(self, model, select, local_images):
        super().__init__()
        style(self, 'device-selector')
        self.identity=model.identity;self.art_key=None;self.local_images=local_images
        row=Gtk.Box(spacing=8);self.add(row)
        self.picture=Gtk.Image();row.pack_start(self.picture,False,False,0)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.title=label('','selector-title');self.title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.title.set_max_width_chars(21);self.title.set_width_chars(10)
        self.status=label('','small',wrap=True);self.status.set_max_width_chars(26)
        text.pack_start(self.title,False,False,0);text.pack_start(self.status,False,False,0)
        row.pack_start(text,True,True,0)
        self.select=select;self.selecting=False
        self.connect('clicked',self.activate_selector)
        self.update(model)

    def activate_selector(self,button_):
        if not self.selecting:self.select(self.identity)

    def mark_selected(self,selected):
        self.selecting=True
        try:self.set_active(selected)
        finally:self.selecting=False

    def update(self,model):
        self.title.set_text(model.name)
        key=(model.appearance,artwork.photo_stamp(model.appearance,self.local_images))
        if key!=self.art_key:
            self.picture.set_from_pixbuf(artwork.picture(model.appearance,46,32,self.local_images)[0]);self.art_key=key
        capacity=model.reading.get('capacity') if model.reading else None
        stable=model.connected and model.confirmed and model.fresh and not model.error and not model.transition
        state=MODES[model.effective][0] if stable else model.title
        if model.connected and model.confirmed and not model.fresh and not model.error and not model.transition:state=_('Aguardando leitura atual…')
        power=(str(capacity)+'%' if capacity is not None else '—')
        if not model.fresh or not model.connected:power='—'
        if model.charging:power='ϟ '+power
        self.status.set_text(power+' · '+state)
        accessible(self,model.name+' — '+power+' · '+state,model.battery_label)
        self.set_tooltip_text(model.name+' · '+model.battery_label)
        for tone in TONES:self.status.get_style_context().remove_class(tone)
        if model.error:style(self.status,'error')


class ControllerCard(Gtk.Box):
    """Selected controller workspace. Draft modes still require confirmation."""
    def __init__(self, model, action, change, preview=False, local_images=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        style(self,'controller-workspace')
        self.model,self.action,self.change=model,action,change
        self.local_images=not preview or local_images
        self.art_key=None;self.popover=None;self.target=None
        self.get_accessible().set_role(Atk.Role.PANEL)
        self.menu_actions=[]
        hero=self.hero=style(AdaptiveBox(spacing=24),'controller-hero')
        portrait=self.portrait=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
        portrait.set_valign(Gtk.Align.CENTER)
        self.art=Gtk.Image();self.art_size=(240,156)
        self.art.set_halign(Gtk.Align.CENTER)
        self.art.get_accessible().set_name(_('Aparência escolhida para este controle'))
        self.art_frame=style(Gtk.EventBox(),'product-stage');self.art_frame.add(self.art)
        portrait.pack_start(self.art_frame,False,False,0)
        self.locate=button(_('Identificar controle'),lambda b:self.action(self.model.identity,'identify'),'quiet','small')
        self.locate.set_image(icon('find-location-symbolic',16));self.locate.set_always_show_image(True)
        self.locate.set_halign(Gtk.Align.CENTER)
        self.locate.set_tooltip_text(_('Pisca as luzes brancas apenas deste controle.'))
        portrait.pack_start(self.locate,False,False,0)
        hero.pack_start(portrait,False,False,0)
        info=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);info.set_valign(Gtk.Align.CENTER)
        hero.pack_start(info,True,True,0)
        header=Gtk.Box(spacing=12)
        self.name=label('','controller-name');self.name.set_ellipsize(Pango.EllipsizeMode.END)
        self.name.set_max_width_chars(28);header.pack_start(self.name,True,True,0)
        more=self.more=style(Gtk.Button() if preview else Gtk.MenuButton(),'quiet')
        more.add(icon('view-more-symbolic'));more.get_accessible().set_name(_('Mais opções deste controle'))
        if not preview:
            menu=style(Gtk.Popover.new(more),'dualsense');options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);options.set_border_width(10)
            for title,command in [(_('Nome e aparência'),'rename'),(_('Bateria e conexão'),'details'),(_('Touchpad e cursor'),'touchpad')]:
                item=button(title,lambda b,c=command:(menu.popdown(),self.action(self.model.identity,c)),'quiet')
                self.menu_actions.append((item,title));options.pack_start(item,False,False,0)
            menu.add(options);options.show_all();more.set_popover(menu)
        header.pack_end(more,False,False,0);info.pack_start(header,False,False,0)
        self.appearance_button=button('',lambda b:self.action(self.model.identity,'rename'),'quiet','model-link')
        self.appearance_button.set_halign(Gtk.Align.START)
        self.appearance_button.set_tooltip_text(_('Escolher modelo e renomear. Não altera o modo de uso.'))
        info.pack_start(self.appearance_button,False,False,0)
        power=Gtk.Box(spacing=10)
        self.capacity=label('—','hero-battery');power.pack_start(self.capacity,False,False,0)
        power_status=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);power_status.set_valign(Gtk.Align.CENTER)
        state_line=Gtk.Box(spacing=6)
        self.spinner=Gtk.Spinner();self.spinner.set_no_show_all(True);state_line.pack_start(self.spinner,False,False,0)
        self.battery=label('','muted','small',wrap=True);state_line.pack_start(self.battery,True,True,0)
        power_status.pack_start(state_line,False,False,0)
        self.bar=Gtk.ProgressBar();self.bar.set_size_request(92,-1);self.bar.set_no_show_all(True)
        power_status.pack_start(self.bar,False,False,0);power.pack_start(power_status,True,True,0)
        info.pack_start(power,False,False,0)
        self.mode=label('','mode-status');info.pack_start(self.mode,False,False,0)
        self.battery.set_tooltip_text(_('Leitura do controle, em passos aproximados de 10%. Não mede a corrente do cabo.'))
        self.pack_start(hero,False,False,0)
        self.mode_buttons={};switch=style(AdaptiveBox(spacing=6),'mode-switch')
        for key,image in [('charge','battery-symbolic'),('proxy','preferences-system-symbolic'),('play','input-gaming-symbolic')]:
            choice=style(ModeButton(key,image,mode_hint(key)),'mode-tab');choice.set_label(MODES[key][0])
            choice.connect('clicked',lambda b,k=key:self.choose_mode(b,k))
            choice.set_tooltip_text(MODES[key][1]);self.mode_buttons[key]=choice
            switch.pack_start(choice,True,True,0)
        self.pack_start(switch,False,False,0)
        self.description=label('','muted','small',wrap=True);self.description.set_max_width_chars(64)
        self.description.set_no_show_all(True);self.pack_start(self.description,False,False,0)
        self.rule=label('','warning','small',wrap=True);self.rule.set_no_show_all(True)
        self.pack_start(self.rule,False,False,0)
        actions=self.tools=style(AdaptiveBox(spacing=8),'controller-tools')
        self.customize=purpose_button(_('Luzes e efeitos'),_('Escolha cores, vibração e peso dos gatilhos.'),
                                      'applications-graphics-symbolic',lambda b:self.action(self.model.identity,'effects'))
        self.test_input=purpose_button(_('Testar botões'),_('Confira se cada botão e analógico responde.'),
                                       'input-gaming-symbolic',lambda b:self.action(self.model.identity,'input'))
        self.touchpad=purpose_button(_('Touchpad e cursor'),_('Evite mover o mouse enquanto joga.'),
                                     'input-touchpad-symbolic',lambda b:self.action(self.model.identity,'touchpad'))
        self.details=purpose_button(_('Bateria e conexão'),_('Veja se a carga aumentou com o tempo.'),
                                    'battery-good-symbolic',lambda b:self.action(self.model.identity,'details'))
        for pair in ((self.customize,self.test_input),(self.touchpad,self.details)):
            group=AdaptiveBox(spacing=8)
            for tool in pair:group.pack_start(tool,True,True,0)
            actions.pack_start(group,True,True,0)
        self.pack_start(actions,False,False,0)
        self.effects_hint=label('','muted','small',wrap=True);self.effects_hint.set_no_show_all(True)
        self.effects_hint.set_halign(Gtk.Align.CENTER);self.pack_start(self.effects_hint,False,False,0)
        self.update(model)

    def do_get_preferred_width_for_height(self,height):
        # A vertically scrolling workspace may grow taller. GTK Box otherwise
        # asks horizontal mode controls for their width at a constrained height.
        return self.get_preferred_width()

    def do_size_allocate(self,allocation):
        art_size=(160,104) if allocation.width<620 else (240,156)
        if art_size!=self.art_size:
            self.art_size=art_size;self.update_art()
        Gtk.Box.do_size_allocate(self,allocation)

    def update_art(self):
        model=self.model
        art_key=(model.appearance,artwork.photo_stamp(model.appearance,self.local_images),self.art_size)
        if art_key==self.art_key:return
        pixbuf,is_photo=artwork.picture(model.appearance,*self.art_size,self.local_images)
        self.art.set_from_pixbuf(pixbuf);title=_(artwork.model(model.appearance)['name'])
        self.appearance_button.set_label(title+'  ⌄')
        self.art.set_tooltip_text(title+(_(' · Foto local') if is_photo else _(' · Ilustração')))
        self.art_key=art_key

    def update(self,model):
        self.model=model
        for tone in TONES:self.mode.get_style_context().remove_class(tone)
        style(self.mode,model.tone)
        self.name.set_text(model.name)
        suffix=model.identity.removeprefix('hid:').replace(':','')[-4:].upper()
        self.context=model.name+' · ID '+suffix
        self.name.set_tooltip_text(self.context)
        accessible(self,self.context)
        for widget,title in [(self.appearance_button,_('Nome e aparência')),
                             (self.locate,_('Qual é este? Piscar luzes')),
                             (self.more,_('Mais opções deste controle')),
                             (self.customize,_('Luzes e efeitos')),
                             (self.test_input,_('Testar botões')),(self.touchpad,_('Touchpad e cursor')),
                             (self.details,_('Bateria e conexão')),*self.menu_actions]:
            accessible(widget,title+' — '+self.context)
        accessible(self.art,_(artwork.model(model.appearance)['name'])+' — '+self.context)
        self.update_art()
        capacity=model.reading.get('capacity') if model.reading else None
        self.capacity.set_text(f'{capacity}%' if capacity is not None else '—')
        self.bar.set_fraction(capacity/100 if capacity is not None else 0)
        self.bar.set_visible(capacity is not None)
        accessible(self.bar,_('Bateria')+' — '+self.context,model.battery_label)
        self.battery.set_text(model.battery_label);self.bar.set_tooltip_text(model.observation or model.battery_label)
        self.bar.get_style_context().remove_class('charging')
        if model.charging:style(self.bar,'charging');self.spinner.start()
        else:self.spinner.stop()
        self.spinner.set_visible(model.charging)
        stable=model.connected and model.confirmed and model.fresh and not model.error and not model.transition
        pending_title=model.title
        if model.connected and model.confirmed and not model.fresh and not model.error and not model.transition:
            pending_title=_('Aguardando leitura atual…')
        self.mode.set_text((_('●  Fora dos jogos') if model.effective=='charge' else _('●  Disponível para os jogos')) if stable else pending_title)
        for key,choice in self.mode_buttons.items():
            active=stable and model.effective==key
            context=choice.get_style_context();context.remove_class('selected')
            if active:context.add_class('selected')
            title=MODES[key][0]
            choice.set_label(('✓  ' if active else '')+title)
            if choice.hint.get_text()!=mode_hint(key):choice.hint.set_text(mode_hint(key))
            accessible(choice,title+(_(' · modo ativo') if active else '')+' — '+self.context,MODES[key][1])
            choice.set_sensitive(model.can_change)
        description={'charge':_('A Steam não recebe este controle. Luzes e vibração desligadas.'),
                     'proxy':_('Suas luzes e efeitos têm prioridade, mesmo com a Steam aberta.'),
                     'play':_('A Steam e o jogo controlam os efeitos e os recursos nativos.')}[model.effective]
        if not model.connected:description=_('Reconecte este controle para usar. Seu nome e suas preferências estão salvos.')
        elif model.error:description=model.error
        elif not model.helper_ready:description=_('Configure o acesso USB para começar.')
        elif model.transition:description=_('Aguarde a troca terminar. O novo modo aparece depois da confirmação.')
        elif not model.confirmed or not model.fresh:description=_('Aguardando uma leitura atual do controle.')
        self.description.set_visible(True)
        self.description.set_text(description);self.description.set_tooltip_text(description)
        accessible(self,self.context,self.mode.get_text()+'. '+description)
        if model.native_game and model.requested=='proxy':
            self.rule.set_text(_('Regra de ')+model.native_game+_(': acesso direto enquanto o jogo estiver aberto.'));self.rule.show()
        elif stable and model.effective=='charge' and model.guard_reason:
            self.rule.set_text(model.guard_reason);self.rule.show()
        else:self.rule.hide()
        self.locate.set_sensitive(stable)
        self.test_input.set_sensitive(stable)
        self.customize.set_visible(True)
        self.customize.set_sensitive(model.can_customize)
        self.effects_hint.set_text(_('Luzes e efeitos: escolha Minhas configurações.') if model.effective!='proxy' else '')
        self.customize.set_tooltip_text(_('Luzes e efeitos: escolha Minhas configurações.') if not model.can_customize else MODES['proxy'][1])
        self.effects_hint.set_visible(stable and model.effective!='proxy')
        # GTK can close the popover when its anchor becomes insensitive. Keep
        # its confirmation disabled too, including queued activation events.
        if self.popover:self.update_choice()

    def choose_mode(self,anchor=None,initial=None):
        if not self.model.can_change:return
        selected=initial if initial in MODES else ('proxy' if self.model.requested=='charge' else 'charge')
        if selected==self.model.requested and not self.model.error:return
        self.target=selected
        if self.popover:self.popover.destroy()
        self.popover=style(Gtk.Popover.new(anchor or self.mode_buttons[selected]),'dualsense')
        self.popover.set_position(Gtk.PositionType.BOTTOM)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);box.set_border_width(20)
        box.pack_start(label(self.model.name,'controller-name',wrap=True),False,False,0)
        box.pack_start(label(_('Mudar para ')+MODES[selected][0]+'?','mode-title'),False,False,0)
        route=Gtk.Box(spacing=12);route.set_halign(Gtk.Align.CENTER)
        nodes=[('input-gaming-symbolic',_('Controle'))]
        nodes+=([('battery-symbolic',_('Fora dos jogos'))] if selected=='charge' else [('preferences-system-symbolic',_('Seus efeitos')),('applications-games-symbolic',_('Jogo'))] if selected=='proxy' else [('applications-games-symbolic',_('Jogo'))])
        for index,(symbol,title) in enumerate(nodes):
            if index:route.pack_start(icon('go-next-symbolic',18),False,False,0)
            node=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            node.pack_start(icon(symbol,28),False,False,0)
            text=label(title,'small',wrap=True);text.set_xalign(.5);node.pack_start(text,False,False,0)
            route.pack_start(node,False,False,0)
        box.pack_start(route,False,False,4)
        self.consequence=label('','muted',wrap=True);self.consequence.set_max_width_chars(48)
        box.pack_start(self.consequence,False,False,0)
        row=Gtk.Box(spacing=10);row.set_halign(Gtk.Align.END)
        self.cancel=button(_('Cancelar'),lambda b:self.popover.popdown(),'quiet')
        row.pack_start(self.cancel,False,False,0)
        self.apply=button(_('Confirmar'),self.apply_choice,'primary');row.pack_start(self.apply,False,False,0)
        box.pack_start(row,False,False,0);self.popover.add(box);box.show_all();self.update_choice();self.popover.popup()

    def selected_mode(self):return self.target

    def update_choice(self):
        same=self.target==self.model.requested and not self.model.error
        self.consequence.set_text(_('Este modo já está selecionado.') if same else mode_consequence(self.model.effective,self.target,self.model.native_game))
        self.apply.set_sensitive(self.model.can_change and not same)
        self.apply.set_label(_('Tentar novamente') if self.target==self.model.requested and self.model.error else _('Confirmar ')+MODES[self.target][0].lower())
        accessible(self.popover,_('Mudar para ')+MODES[self.target][0]+' — '+self.context,self.consequence.get_text())
        accessible(self.apply,self.apply.get_label()+' — '+self.context,self.consequence.get_text())

    def apply_choice(self,_):
        if not self.model.can_change or not self.apply.get_sensitive():return
        self.popover.popdown();self.change(self.model.identity,self.target)


class ChoiceStrip(Gtk.FlowBox):
    """Visible, exclusive choices with native focus and checked states."""
    __gsignals__={'changed':(GObject.SignalFlags.RUN_FIRST,None,())}

    def __init__(self,columns=3):
        super().__init__()
        self.buttons={};self.titles={};self.active=None;self.updating=False
        self.set_selection_mode(Gtk.SelectionMode.NONE);self.set_homogeneous(True)
        self.set_min_children_per_line(1);self.set_max_children_per_line(columns)
        self.set_column_spacing(6);self.set_row_spacing(6)
        self.get_accessible().set_role(Atk.Role.GROUPING)

    def append(self,key,title):
        choice=style(Gtk.ToggleButton(label=title),'effect-choice')
        choice.get_child().set_line_wrap(True);choice.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.buttons[key]=choice;self.titles[key]=title
        choice.connect('toggled',self.choose,key);choice.connect('key-press-event',self.navigate,key)
        self.add(choice);choice.get_parent().set_can_focus(False)

    def choose(self,choice,key):
        if not self.updating:self.set_active_id(key)

    def set_active_id(self,key):
        if key not in self.buttons:return False
        changed=key!=self.active;self.active=key;self.updating=True
        try:
            for value,choice in self.buttons.items():
                choice.set_active(value==key);choice.set_label(('✓ ' if value==key else '')+self.titles[value])
        finally:self.updating=False
        if changed:self.emit('changed')
        return True

    def get_active_id(self):return self.active
    def get_active_text(self):return self.titles.get(self.active,'')
    def grab_focus(self):
        if self.active in self.buttons:self.buttons[self.active].grab_focus()

    def navigate(self,choice,event,key):
        if event.keyval not in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Up,Gdk.KEY_Down):return False
        keys=list(self.buttons);step=1 if event.keyval in (Gdk.KEY_Right,Gdk.KEY_Down) else -1
        self.set_active_id(keys[(keys.index(key)+step)%len(keys)]);self.grab_focus();return True


class EffectIllustration(Gtk.Stack):
    """Local preference preview using the licensed DualSense geometry, not telemetry."""
    def __init__(self):
        super().__init__()
        self.set_transition_type(Gtk.StackTransitionType.CROSSFADE);self.set_transition_duration(140)
        self.frames=[Gtk.Image(),Gtk.Image()];self.frame=0;self.last=None
        for index,picture in enumerate(self.frames):self.add_named(picture,str(index))
        self.set_halign(Gtk.Align.CENTER)
        accessible(self,_('Prévia dos efeitos'),_('Ilustração dos ajustes escolhidos. Não envia comandos ao controle.'))

    def update(self,values,section):
        from controller_blueprint import geometry
        key=(tuple(values['rgb']),values['vibration'],values['triggers'],section)
        if key==self.last:return
        self.last=key;shapes=geometry();rgb='#'+''.join(f'{v:02x}' for v in values['rgb'])
        accent=rgb if section=='color' else '#80b5ff'
        # Original 910×735 silhouette: no guessed gamepad geometry or photo edits.
        pieces=['<svg xmlns="http://www.w3.org/2000/svg" width="360" height="220" viewBox="-100 -20 1110 780">',
                '<g fill="#172231">'+shapes['shell_fill']+'</g>',
                '<g fill="#29394f">'+shapes['panels_fill']+'</g>',
                '<g fill="#8395ae">'+shapes['Controller']+'</g>',
                f'<g fill="none" stroke="{rgb}" stroke-width="12" stroke-linecap="round"><path d="M248 176L271 291Q277 325 305 337 M660 176L637 291Q631 325 603 337"/></g>']
        for part in ('Trackpad','Up','Down','Left','Right','Triangle','Circle','Cross','Square','Create','Options','L3','R3','PS','Mute'):
            pieces.append('<g fill="#26364a">'+shapes.get(part+'_infill','')+'</g>')
            pieces.append('<g fill="#b5c2d4">'+shapes.get(part+'_outline','')+'</g>')
        strength={'game':0,'off':0,'light':1,'medium':2,'firm':3}[values['triggers']]
        for key,x in [('L2',157),('R2',751)]:
            selected=section=='triggers'
            pieces.append('<g fill="'+(accent if selected else '#52657e')+'">'+shapes[key+'_infill']+'</g>')
            pieces.append(f'<text x="{x}" y="70" text-anchor="middle" font-family="sans-serif" font-size="35" fill="#ffffff">{key}</text>')
            if selected:
                for level in range(3):
                    pieces.append(f'<rect x="{x-43+level*32}" y="110" width="24" height="12" rx="4" fill="'+(accent if level<strength else '#37455a')+'"/>')
        if section=='vibration' and values['vibration']!='off':
            for radius in range(1,2 if values['vibration']=='low' else 4):
                x=-8-radius*23
                pieces.append(f'<path d="M{x+10} 420q-35 55-10 110 M{910-x-10} 420q35 55 10 110" fill="none" stroke="{accent}" stroke-width="9" stroke-linecap="round"/>')
        pieces.append('</svg>');loader=GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.write(''.join(pieces).encode());loader.close()
        self.frame=1-self.frame;self.frames[self.frame].set_from_pixbuf(loader.get_pixbuf())
        self.set_visible_child_name(str(self.frame))


class EffectsEditor(Gtk.Box):
    """Visual local draft. Hardware trials remain separate, explicit actions."""
    def __init__(self,config,trigger_ready=True,configured=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.on_change=lambda:None;self.on_section_change=lambda:None
        self.trigger_ready=trigger_ready;self.baseline=None;self.swatches={};self.updating_swatches=False
        self.illustration=EffectIllustration();self.pack_start(self.illustration,False,False,0)
        self.draft_state=label('','small','muted');self.draft_state.set_halign(Gtk.Align.CENTER)
        self.pack_start(self.draft_state,False,False,0)
        self.sections=Gtk.Stack();self.sections.set_hhomogeneous(False);self.sections.set_vhomogeneous(False)
        self.sections.set_transition_type(Gtk.StackTransitionType.CROSSFADE);self.sections.set_transition_duration(140)
        tabs=Gtk.StackSwitcher();tabs.set_stack(self.sections);tabs.set_halign(Gtk.Align.CENTER)
        style(tabs,'effect-tabs');self.pack_start(tabs,False,False,0)
        color_section=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),'effects-section')
        heading=Gtk.Box(spacing=12);heading.pack_start(label(_('Cor da luz'),'setting-title'),True,True,0)
        self.hex_label=label('','effect-hex');heading.pack_end(self.hex_label,False,False,0)
        color_section.pack_start(heading,False,False,0)
        colors=Gtk.FlowBox();colors.set_selection_mode(Gtk.SelectionMode.NONE)
        colors.set_min_children_per_line(1);colors.set_max_children_per_line(7);colors.set_homogeneous(True)
        colors.set_column_spacing(6);colors.set_row_spacing(6)
        self.color=Gtk.ColorButton();self.color.set_use_alpha(False);self.color.set_title(_('Escolher a cor da luz'))
        self.color.set_tooltip_text(_('Escolher outra cor'));self.color.get_accessible().set_name(_('Outra cor da luz'))
        self.color.set_size_request(46,34)
        self.pick(config.get('rgb',[0,100,255]))
        for name,rgb in [(_('Azul'),(0,120,255)),(_('Violeta'),(151,81,255)),(_('Rosa'),(245,82,152)),(_('Vermelho'),(240,66,66)),(_('Verde'),(0,200,90)),(_('Branco'),(240,244,255))]:
            choice=style(Gtk.ToggleButton(label=''),'swatch');choice.set_halign(Gtk.Align.CENTER);choice.set_valign(Gtk.Align.CENTER);choice.set_tooltip_text(name);choice.get_accessible().set_name(_('Luz ')+name.lower())
            css=Gtk.CssProvider();css.load_from_data(f'button.swatch {{ background: rgb{rgb}; color: #0e1117; }}'.encode())
            choice.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
            choice.connect('toggled',self.select_swatch,rgb);colors.add(choice);choice.get_parent().set_can_focus(False)
            self.swatches[rgb]=choice
        colors.add(self.color);self.color.get_parent().set_can_focus(False);color_section.pack_start(colors,False,False,0)
        self.light=style(Gtk.EventBox(),'effect-preview');self.light.set_size_request(-1,5)
        self.light.set_no_show_all(True)
        self.sections.add_titled(color_section,'color',_('Luz'))
        self.vibration=ChoiceStrip()
        for key,title in [('off',_('Desligada')),('low',_('Reduzida')),('game',_('Normal'))]:self.vibration.append(key,title)
        self.vibration.set_active_id(config.get('vibration','game'))
        self.sections.add_titled(self.setting(_('Vibração'),_('Intensidade dos efeitos enviados pelo jogo.'),self.vibration),'vibration',_('Vibração'))
        self.triggers=ChoiceStrip(5)
        for key,title in [('game',_('Jogo')),('off',_('Livre')),('light',_('Leve')),('medium',_('Média')),('firm',_('Firme'))]:self.triggers.append(key,title)
        self.triggers.set_active_id(config.get('triggers','game'));self.triggers.set_sensitive(trigger_ready)
        trigger_section=self.setting(_('Peso dos gatilhos'),_('Resistência ao apertar L2 e R2.'),self.triggers)
        self.trigger_note=label('','muted','small',wrap=True);trigger_section.pack_start(self.trigger_note,False,False,0)
        self.sections.add_titled(trigger_section,'triggers',_('Gatilhos'))
        self.pack_start(self.sections,False,False,0)
        self.color.connect('color-set',lambda w:self.changed())
        self.vibration.connect('changed',lambda w:self.changed());self.triggers.connect('changed',lambda w:self.changed())
        self.sections.connect('notify::visible-child-name',self.section_changed)
        self.baseline=self.values() if configured else None
        self.changed()

    def do_get_preferred_width_for_height(self,height):return self.get_preferred_width()

    def setting(self,title,detail,control):
        row=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10),'effects-section')
        heading=label(title,'setting-title');explanation=label(detail,'muted','small',wrap=True)
        row.pack_start(heading,False,False,0);row.pack_start(explanation,False,False,0)
        accessible(control,title,detail)
        control.get_accessible().add_relationship(Atk.RelationType.LABELLED_BY,heading.get_accessible())
        heading.get_accessible().add_relationship(Atk.RelationType.LABEL_FOR,control.get_accessible())
        control.get_accessible().add_relationship(Atk.RelationType.DESCRIBED_BY,explanation.get_accessible())
        row.pack_start(control,False,False,0)
        return row

    def section_changed(self,*args):
        if not hasattr(self,'triggers'):return
        self.illustration.update(self.values(),self.sections.get_visible_child_name())
        self.on_section_change()

    def select_swatch(self,choice,rgb):
        if self.updating_swatches:return
        # A preset cannot be deselected without choosing another color.
        # set_active also emits clicked/toggled, so guard programmatic updates.
        if choice.get_active():self.pick(rgb)
        else:self.changed()

    def pick(self,rgb):
        rgba=Gdk.RGBA();rgba.red,rgba.green,rgba.blue=[v/255 for v in rgb];rgba.alpha=1
        self.color.set_rgba(rgba)
        if hasattr(self,'triggers'):self.changed()

    def values(self):
        rgba=self.color.get_rgba()
        return {'rgb':[round(v*255) for v in (rgba.red,rgba.green,rgba.blue)],
                'vibration':self.vibration.get_active_id() or 'game',
                'triggers':self.triggers.get_active_id() if self.trigger_ready else 'game'}

    @property
    def dirty(self):return self.values()!=self.baseline

    def changed(self):
        values=self.values();rgb=tuple(values['rgb'])
        self.hex_label.set_text('#'+''.join(f'{v:02X}' for v in rgb))
        self.updating_swatches=True
        try:
            for color,choice in self.swatches.items():
                context=choice.get_style_context();context.remove_class('chosen')
                selected=color==rgb
                choice.set_active(selected);choice.set_label('✓' if selected else '')
                if selected:context.add_class('chosen')
        finally:self.updating_swatches=False
        accessible(self.color,_('Outra cor da luz'),self.hex_label.get_text())
        if hasattr(self,'light_css'):self.light.get_style_context().remove_provider(self.light_css)
        self.light_css=Gtk.CssProvider();self.light_css.load_from_data(f'.effect-preview {{ background: rgb{rgb}; }}'.encode())
        self.light.get_style_context().add_provider(self.light_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        descriptions={'game':_('O jogo define a resistência e os efeitos dos gatilhos.'),
                      'off':_('L2 e R2 ficam livres, sem resistência adicional.'),
                      'light':_('Resistência leve e constante nos dois gatilhos.'),
                      'medium':_('Resistência média e constante nos dois gatilhos.'),
                      'firm':_('Resistência firme e constante nos dois gatilhos.')}
        self.trigger_note.set_text(descriptions.get(values['triggers'],'') if self.trigger_ready else _('Atualize o suporte USB para ajustar os gatilhos.'))
        accessible(self.triggers,_('Peso dos gatilhos'),self.trigger_note.get_text())
        self.illustration.update(values,self.sections.get_visible_child_name())
        self.draft_state.set_text(_('Prévia · alterações não salvas') if self.dirty else _('Prévia dos ajustes salvos'))
        self.on_change()


class ContentClamp(Gtk.Bin):
    """Center the content without stretching it across a maximized desktop."""
    def __init__(self,child,maximum=1080):
        super().__init__();self.maximum=maximum;self.set_has_window(False);self.add(child)
    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_get_preferred_width(self):
        minimum,natural=self.get_child().get_preferred_width()
        return minimum,min(self.maximum,max(minimum,natural))
    def do_get_preferred_height(self):return self.get_child().get_preferred_height()
    def do_get_preferred_height_for_width(self,width):return self.get_child().get_preferred_height_for_width(min(width,self.maximum))
    def do_size_allocate(self,allocation):
        self.set_allocation(allocation)
        rect=Gdk.Rectangle();rect.width=min(allocation.width,self.maximum);rect.height=allocation.height
        rect.x=allocation.x+(allocation.width-rect.width)//2;rect.y=allocation.y
        self.get_child().size_allocate(rect)


class Dashboard(Gtk.Box):
    def __init__(self, owner):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.set_border_width(18)
        self.owner=owner;self.items={};self.selectors={};self.selected=None;self.tour=None
        self.connect('destroy',lambda w:self.tour.close(False) if self.tour else None)
        bar=AdaptiveBox(spacing=10)
        brand_row=Gtk.Box(spacing=10)
        bar.pack_start(brand_row,True,True,0)
        brand=Gtk.Image.new_from_file(str(ASSETS/'dualsense-usb.svg'))
        brand.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS/'brand-mark.svg'),32,32,True))
        brand_row.pack_start(brand,False,False,0);brand_row.pack_start(label('UPLUGO','brand'),True,True,0)
        bar_actions=Gtk.Box(spacing=8);bar.pack_end(bar_actions,False,False,0)
        compatibility=self.compatibility=button(_('Modo por jogo'),lambda b:owner.profiles_dialog(),'quiet')
        compatibility.set_tooltip_text(_('Trocar para os efeitos do jogo ao abri-lo e voltar aos seus ajustes ao fechar.'))
        compatibility.set_image(icon('input-gaming-symbolic',18));compatibility.set_always_show_image(True)
        bar_actions.pack_start(compatibility,False,False,0)
        self.help=button(_('Ajuda'),lambda b:self.start_tour(),'quiet')
        self.help.set_image(icon('help-browser-symbolic'));self.help.set_always_show_image(True)
        bar_actions.pack_start(self.help,False,False,0)
        preview=getattr(owner,'preview',False)
        preferences=self.preferences=style(Gtk.Button() if preview else Gtk.MenuButton(),'quiet');preferences.add(icon('preferences-system-symbolic'))
        preferences.set_tooltip_text(_('Preferências'));preferences.get_accessible().set_name(_('Preferências'))
        settings=style(Gtk.Popover.new(preferences),'dualsense') if not preview else None
        options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);options.set_border_width(16)
        def section(title):
            group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            group.pack_start(label(title,'setting-title',wrap=True),False,False,0)
            options.pack_start(group,False,False,0)
            return group
        general=section(_('Uso diário'))
        language_row=Gtk.Box(spacing=12)
        language_row.pack_start(label(_('Idioma'),'setting-title'),True,True,0)
        self.language_choice=Gtk.ComboBoxText()
        for code,title in LANGUAGES.items():self.language_choice.append(code,title)
        self.language_choice.set_active_id(language())
        self.language_choice.get_accessible().set_name(_('Idioma da interface'))
        self.language_choice.set_tooltip_text(_('A troca é imediata e não reconecta os controles.'))
        def change_language(combo):
            from gi.repository import GLib
            code=combo.get_active_id()
            if hasattr(owner,'change_language') and code != language():
                def apply():
                    owner.change_language(code)
                    return False
                GLib.idle_add(apply)
        self.language_choice.connect('changed',change_language)
        general.pack_start(language_row,False,False,0)
        language_row.pack_end(self.language_choice,False,False,0)
        self.above=Gtk.CheckButton(label=_('Manter a janela sempre visível'))
        self.above.set_tooltip_text(_('Mantém esta janela sobre outras janelas. Não altera quem controla os efeitos.'))
        self.protect=Gtk.CheckButton(label=_('Usar meus efeitos no modo Minhas configurações'))
        self.protect.set_tooltip_text(_('Aplica suas cores, vibração e peso dos gatilhos. Em Configurações do jogo, os efeitos ficam com o jogo.'))
        self.autostart=Gtk.CheckButton(label=_('Abrir ao ligar o computador'))
        self.autostart.set_tooltip_text(_('Começa na bandeja quando você entra na sua conta. Os modos dos controles não mudam.'))
        general.pack_start(self.autostart,False,False,0)
        general.pack_start(self.above,False,False,0);general.pack_start(self.protect,False,False,0)
        options.pack_start(Gtk.Separator(),False,False,0)
        protection=section(_('Proteção automática'))
        self.guard=Gtk.CheckButton(label=_('Voltar a Só carregar se outro app usar o controle'))
        self.allow_play=Gtk.CheckButton(label=_('Suspender esse bloqueio ao escolher Jogar'))
        protection.pack_start(self.guard,False,False,0)
        self.allow_play.set_margin_start(24)
        protection.pack_start(self.allow_play,False,False,0)
        def protection_changed(choice):
            # Preserve the saved choice when the parent is off. Only its
            # availability changes; no extra toggled signal or settings write.
            self.allow_play.set_sensitive(choice.get_active())
        self.guard.connect('toggled',protection_changed);protection_changed(self.guard)
        for choice in (self.autostart,self.above,self.protect,self.guard,self.allow_play):
            choice.get_child().set_line_wrap(True);choice.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            choice.get_child().set_max_width_chars(36)
        help_=self.protection_help=Gtk.Expander()
        help_.set_label_widget(label(_('Como funciona o bloqueio?'),'small',wrap=True))
        explanation=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        explanation.set_margin_top(8)
        explanation.pack_start(label(_('O bloqueio verifica periodicamente o acesso de outros apps. Com a suspensão marcada, escolher Jogar permite esse acesso até você voltar a Só carregar.'),'muted','small',wrap=True),False,False,0)
        explanation.pack_start(label(_('Só carregar sempre mantém o controle fora dos jogos.'),'muted','small',wrap=True),False,False,0)
        help_.add(explanation);protection.pack_start(help_,False,False,0)
        options.pack_start(Gtk.Separator(),False,False,0)
        self.preference_actions={}
        def destination(parent,title,symbol,method,disclosure=True):
            def open_destination(widget):
                if settings:settings.popdown()
                callback=getattr(owner,method,None)
                if callback:callback()
            action=style(Gtk.Button(),'quiet')
            row=Gtk.Box(spacing=10)
            row.pack_start(icon(symbol),False,False,0)
            row.pack_start(label(title,wrap=True),True,True,0)
            if disclosure:row.pack_end(icon('go-next-symbolic',14),False,False,0)
            action.add(row);action.get_accessible().set_name(title)
            action.connect('clicked',open_destination)
            parent.pack_start(action,False,False,0)
            self.preference_actions[method]=action
        destination(options,_('Fotos dos controles'),'image-x-generic-symbolic','photos_dialog')
        destination(options,_('Acesso USB'),'drive-removable-media-symbolic','review_access')
        maintenance=self.maintenance=Gtk.Expander()
        maintenance.set_label_widget(label(_('Ferramentas e manutenção'),wrap=True))
        tools=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        tools.set_margin_top(8)
        destination(tools,_('Desenvolvimento e diagnóstico'),'utilities-terminal-symbolic','development_dialog')
        destination(tools,_('Instalação e remoção'),'system-software-install-symbolic','open_setup')
        maintenance.add(tools);options.pack_start(maintenance,False,False,0)
        destination(options,_('Relatar um problema'),'dialog-warning-symbolic','report_problem')
        destination(options,_('Sobre e créditos'),'help-about-symbolic','about_dialog')
        options.pack_start(Gtk.Separator(),False,False,0)
        destination(options,_('Encerrar e liberar controles'),'application-exit-symbolic','quit_app',False)
        if settings:
            settings_scroll=Gtk.ScrolledWindow();settings_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
            def fit_preferences(*args):
                parent=self.get_toplevel();display=self.get_display()
                monitor=display.get_monitor_at_window(parent.get_window()) if parent.get_window() else display.get_primary_monitor()
                if monitor is None and display.get_n_monitors():monitor=display.get_monitor(0)
                area=monitor.get_workarea() if monitor else None
                height=area.height if area else 600
                width=min(parent.get_allocated_width(),area.width if area else 480)
                # NEVER horizontal scrolling lets GTK ignore min-content-width;
                # give the popover an actual, bounded minimum instead.
                settings_scroll.set_size_request(min(380,max(200,width-80)),-1)
                settings_scroll.set_max_content_height(max(160,min(640,height-120,parent.get_allocated_height()-64)))
            fit_preferences();settings.connect('show',fit_preferences)
            settings_scroll.set_propagate_natural_height(True);settings_scroll.set_overlay_scrolling(False)
            settings_scroll.add(options);settings.add(settings_scroll);settings_scroll.show_all();preferences.set_popover(settings)
        bar_actions.pack_end(preferences,False,False,0);self.pack_start(bar,False,False,0)
        heading=AdaptiveBox(spacing=12)
        self.heading=heading
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        left.pack_start(label(_('Seus controles'),'workspace-title',wrap=True),False,False,0)
        self.count=label(_('Conecte um DualSense para começar.'),'muted',wrap=True)
        left.pack_start(self.count,False,False,0)
        self.count.set_no_show_all(True);self.count.set_visible(preview)
        self.guide=button(_('Qual modo usar?'),lambda b:self.show_mode_guide(),'quiet','small')
        self.guide.set_halign(Gtk.Align.END);heading.pack_end(self.guide,False,False,0)
        heading.pack_start(left,True,True,0)
        self.health=label(_('USB • AO VIVO'),'status-pill','cyan')
        self.health.set_valign(Gtk.Align.CENTER);self.health.set_no_show_all(True)
        heading.show_all();heading.set_no_show_all(True)
        self.pack_start(heading,False,False,0)
        self.guard_notice=label('','muted','small',wrap=True)
        self.guard_notice.set_no_show_all(True)
        self.pack_start(self.guard_notice,False,False,0)
        self.setup=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10),'setup')
        setup_row=AdaptiveBox(spacing=18)
        setup_text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        self.setup_title=label('','setting-title',wrap=True)
        self.setup_description=label('','muted','small',wrap=True)
        self.setup_description.set_max_width_chars(70)
        setup_text.pack_start(self.setup_title,False,False,0)
        setup_text.pack_start(self.setup_description,False,False,0)
        setup_row.pack_start(setup_text,True,True,0)
        self.setup_spinner=Gtk.Spinner();self.setup_spinner.set_no_show_all(True)
        setup_row.pack_start(self.setup_spinner,False,False,0)
        self.unlock=button(_('Configurar acesso'),lambda b:owner.install(),'primary')
        self.unlock.set_valign(Gtk.Align.CENTER);setup_row.pack_end(self.unlock,False,False,0)
        self.setup.pack_start(setup_row,False,False,0)
        self.setup_details=Gtk.Expander(label=_('Detalhes da configuração'))
        self.setup_details.set_no_show_all(True)
        self.setup_error=label('','small',wrap=True);self.setup_error.set_selectable(True)
        self.setup_error.set_max_width_chars(80)
        detail_scroll=Gtk.ScrolledWindow();detail_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        detail_scroll.set_min_content_height(70);detail_scroll.set_max_content_height(110);detail_scroll.set_propagate_natural_height(True)
        detail_scroll.add(self.setup_error);detail_scroll.show_all();self.setup_details.add(detail_scroll)
        self.setup.pack_start(self.setup_details,False,False,0)
        self.setup_dismiss=button(_('Fechar explicação'),lambda b:self.dismiss_setup(),'quiet','small')
        self.setup_dismiss.set_halign(Gtk.Align.START);self.setup_dismiss.set_no_show_all(True)
        self.setup.pack_start(self.setup_dismiss,False,False,0)
        self.setup.show_all();self.setup.set_no_show_all(True);self.setup.hide()
        self.pack_start(self.setup,False,False,0)
        self.support_update=style(AdaptiveBox(spacing=16),'setup')
        self.support_update_text=label('','muted','small',wrap=True)
        self.support_update_text.set_max_width_chars(70)
        self.support_update.pack_start(self.support_update_text,True,True,0)
        self.support_update_button=button(_('Revisar suporte USB'),lambda b:self.review_support(),'quiet')
        self.support_update.pack_end(self.support_update_button,False,False,0)
        self.support_update.show_all();self.support_update.set_no_show_all(True);self.support_update.hide()
        self.pack_start(self.support_update,False,False,0)
        self.stack=Gtk.Stack()
        self.stack.set_vhomogeneous(False);self.stack.set_hhomogeneous(False)
        self.selector_row=Gtk.Box(spacing=10);self.selector_row.set_homogeneous(True)
        self.selector_scroll=Gtk.ScrolledWindow()
        self.selector_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.NEVER)
        self.selector_scroll.set_propagate_natural_height(True)
        self.selector_scroll.set_overlay_scrolling(False)
        self.selector_scroll.add(self.selector_row)
        self.pack_start(self.selector_scroll,False,False,0)
        self.selector_scroll.show_all();self.selector_scroll.set_no_show_all(True)
        self.cards=Gtk.Stack();self.cards.set_vhomogeneous(False);self.cards.set_hhomogeneous(False)
        self.cards.set_transition_type(Gtk.StackTransitionType.CROSSFADE);self.cards.set_transition_duration(160)
        self.stack.add_named(self.cards,'controllers')
        empty=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12),'empty')
        empty.set_valign(Gtk.Align.CENTER)
        illustration=Gtk.Image.new_from_pixbuf(artwork.picture('white',220,140,False)[0])
        empty.pack_start(illustration,False,False,0)
        for text,cls in [(_('Conecte seu DualSense'),'controller-name'),(_('Use um cabo USB de dados. O controle aparecerá automaticamente.'),'muted')]:
            line=label(text,cls,wrap=True);line.set_halign(Gtk.Align.CENTER);empty.pack_start(line,False,False,0)
        first_language=Gtk.Box(spacing=12);first_language.set_halign(Gtk.Align.CENTER)
        first_language.pack_start(label(_('Idioma'),'small'),False,False,0)
        self.first_language=Gtk.ComboBoxText()
        for code,title in LANGUAGES.items():self.first_language.append(code,title)
        self.first_language.set_active_id(language());self.first_language.get_accessible().set_name(_('Idioma da interface'))
        self.first_language.connect('changed',change_language)
        first_language.pack_start(self.first_language,False,False,0);empty.pack_start(first_language,False,False,0)
        self.connection_help=Gtk.Expander(label=_('O controle não apareceu?'))
        self.connection_help.set_halign(Gtk.Align.CENTER)
        self.connection_help.add(label(_('Este app funciona por USB. Bluetooth não é suportado.\nVerifique se o cabo transmite dados; alguns cabos só carregam.\nTente outra porta USB, de preferência sem um hub.'),'muted','small',wrap=True))
        empty.pack_start(self.connection_help,False,False,0)
        self.empty_guide=button(_('Qual modo usar?'),lambda b:self.show_mode_guide(),'quiet')
        self.empty_guide.set_halign(Gtk.Align.CENTER);empty.pack_start(self.empty_guide,False,False,0)
        self.try_lab=button(_('Explorar com controles de demonstração'),lambda b:self.open_demo(),'quiet')
        self.try_lab.set_halign(Gtk.Align.CENTER);empty.pack_start(self.try_lab,False,False,0)
        self.stack.add_named(empty,'empty');self.pack_start(self.stack,False,False,0)
        self.notice_row=Gtk.Box(spacing=6);style(self.notice_row,'notice')
        self.notice=label('',wrap=True);self.notice.set_max_width_chars(110)
        self.notice_row.pack_start(self.notice,True,True,0)
        self.dismiss_notice=button('×',lambda b:self.notice.set_text(''),'quiet')
        accessible(self.dismiss_notice,_('Fechar aviso'))
        self.notice_row.pack_end(self.dismiss_notice,False,False,0)
        self.notice_row.show_all()
        self.notice_row.hide()
        self.notice_row.set_no_show_all(True)
        self.notice.connect('notify::label',lambda *a:self.notice_row.set_visible(bool(self.notice.get_text())))
        self.pack_start(self.notice_row,False,False,0)
        footer=style(AdaptiveBox(spacing=8),'footer')
        self.footer_note=label(_('Fechar a janela mantém seus modos ativos na bandeja.'),'small',wrap=True)
        footer.pack_start(self.footer_note,True,True,0)
        self.photo_status=label('','muted','small',wrap=True)
        self.photo_status.set_tooltip_text(_('Gerencie os downloads em Preferências → Fotos dos controles.'))
        footer.pack_start(self.photo_status,False,False,0)
        from app_info import VERSION
        footer.pack_end(label('v'+VERSION+' • USB','muted','small'),False,False,0)
        self.pack_end(footer,False,False,0)
        page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for child in list(self.get_children()):
            if child in (bar,footer):continue
            self.remove(child);page.pack_start(child,False,False,0)
        page.reorder_child(self.selector_scroll,1)
        self.scroll=Gtk.ScrolledWindow();self.scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_overlay_scrolling(False)
        self.scroll.add(page);self.pack_start(self.scroll,True,True,0);self.reorder_child(self.scroll,1)

    def update(self, models, helper_ready):
        self.heading.set_visible(bool(models))
        self.guard_notice.set_visible(bool(models) and self.guard.get_active() and not self.allow_play.get_active())
        self.guard_notice.set_text(_('Proteção automática ativa. Ao escolher um modo de jogo, você libera o controle.') if self.allow_play.get_active() else _('Proteção automática ativa · Acesso de qualquer app faz o controle voltar a Só carregar.'))
        count=sum(model.connected for model in models)
        self.count.set_text((_('{0} controle conectado · cada controle tem seu próprio modo') if count==1 else _('{0} controles conectados · cada controle tem seu próprio modo')).format(count))
        fresh=sum(model.connected and model.fresh for model in models)
        self.health.set_text(_('●  USB conectado') if fresh else _('Aguardando USB'))
        access=getattr(self.owner,'access_setup',AccessSetup())
        self.setup.set_visible(access.visible(helper_ready))
        self.setup_title.set_text(access.title(helper_ready))
        self.setup_description.set_text(access.description(helper_ready))
        self.unlock.set_label(access.action(helper_ready))
        self.unlock.set_sensitive(access.phase!='busy' and not getattr(self.owner,'busy',False))
        self.setup_spinner.set_visible(access.phase=='busy')
        if access.phase=='busy':self.setup_spinner.start()
        else:self.setup_spinner.stop()
        self.setup_error.set_text(access.detail[:4096])
        self.setup_details.set_visible(bool(access.detail))
        self.setup_dismiss.set_visible(helper_ready and access.phase!='busy')
        revision=getattr(self.owner,'support_revision',None)
        different=revision is not None and revision.state()=='different'
        native=revision is not None and revision.native
        self.support_update_text.set_text(
            _('O serviço USB é diferente do incluído neste app. Atualize ou repare o pacote pelo gerenciador da distribuição. Nenhum controle será reiniciado por este aviso.') if native else
            _('O serviço USB é diferente do incluído neste app; algumas correções podem não estar ativas. Revise o suporte quando terminar de jogar. A atualização pede autorização e reconecta os controles nos modos salvos.'))
        self.support_update_button.set_label(_('Verificar instalação') if native else _('Revisar suporte USB'))
        self.support_update_button.set_sensitive(not getattr(self.owner,'busy',False))
        self.support_update.set_visible(bool(different and helper_ready and not access.visible(helper_ready)))
        ids={model.identity for model in models}
        for identity in list(self.items):
            if identity not in ids:
                card=self.items.pop(identity);self.cards.remove(card);card.destroy()
                selector=self.selectors.pop(identity);self.selector_row.remove(selector);selector.destroy()
        for model in models:
            if model.identity not in self.items:
                card=ControllerCard(model,self.owner.card_action,self.owner.request_mode,getattr(self.owner,'preview',False),getattr(self.owner,'local_images',False))
                self.items[model.identity]=card;self.cards.add_named(card,model.identity);card.show_all()
                selector=ControllerSelector(model,self.select_controller,not getattr(self.owner,'preview',False) or getattr(self.owner,'local_images',False))
                selector.connect('key-press-event',self.navigate_controller)
                self.selectors[model.identity]=selector;self.selector_row.pack_start(selector,True,True,0);selector.show_all()
            self.items[model.identity].update(model)
            self.selectors[model.identity].update(model)
        self.selector_scroll.set_visible(bool(models))
        if self.selected not in ids:self.select_controller(models[0].identity if models else None)
        self.stack.set_visible_child_name('controllers' if models else 'empty')

    def start_tour(self):
        from first_use import InterfaceTour
        if self.tour:self.tour.close(False)
        self.tour=InterfaceTour(self)

    def navigate_controller(self,widget,event):
        if event.keyval not in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Home,Gdk.KEY_End):return False
        keys=list(self.selectors);index=keys.index(widget.identity)
        if event.keyval==Gdk.KEY_Home:index=0
        elif event.keyval==Gdk.KEY_End:index=len(keys)-1
        else:index=(index+(1 if event.keyval==Gdk.KEY_Right else -1))%len(keys)
        self.select_controller(keys[index]);self.selectors[keys[index]].grab_focus()
        return True

    def select_controller(self,identity):
        changed=identity!=self.selected
        if changed and self.tour:self.tour.close(False)
        if changed and self.selected in self.items:
            old=self.items[self.selected]
            if old.popover:
                old.apply.set_sensitive(False);old.popover.popdown();old.popover.hide()
        self.selected=identity
        for key,selector in self.selectors.items():selector.mark_selected(key==identity)
        if identity in self.items:
            self.cards.set_visible_child_name(identity)
            if changed:self.scroll.get_vadjustment().set_value(0)

    def review_support(self):
        revision=getattr(self.owner,'support_revision',None)
        if revision is not None and revision.native:self.owner.open_setup()
        else:self.owner.review_access()

    def show_mode_guide(self):
        from first_use import mode_guide_dialog
        dialog=mode_guide_dialog(self.get_toplevel())
        try:dialog.show_all();dialog.run()
        finally:dialog.destroy()

    def dismiss_setup(self):
        if hasattr(self.owner,'dismiss_access'):self.owner.dismiss_access()

    def open_demo(self):
        if hasattr(self.owner,'open_demo'):self.owner.open_demo()
