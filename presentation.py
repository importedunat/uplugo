# SPDX-License-Identifier: GPL-3.0-only
"""Human-facing state, separate from requested configuration and USB I/O."""
from i18n import _
from dataclasses import dataclass

class ModeCatalog(dict):
    def __getitem__(self, key):
        title, description, tone = super().__getitem__(key)
        return _(title), _(description), tone


MODES = ModeCatalog({
    'proxy': ('Minhas configurações', 'Suas luzes, vibração e peso dos gatilhos têm prioridade.', 'cyan'),
    'play': ('Configurações do jogo', 'O jogo controla os recursos nativos e os efeitos.', 'purple'),
    'charge': ('Só carregar', 'Fica fora dos jogos. A bateria continua sendo lida.', 'amber'),
})
# One short line under each mode button: the consequence, not the mechanism.
MODE_HINTS = {
    'proxy': 'Sua cor, vibração e gatilhos',
    'play': 'Gatilhos e vibração do jogo',
    'charge': 'Fora dos jogos, só bateria',
}


def mode_hint(key):
    return _(MODE_HINTS[key])


@dataclass
class AccessSetup:
    phase: str = 'idle'
    detail: str = ''
    reviewing: bool = False

    def visible(self,ready):
        return not ready or self.reviewing or self.phase in ('busy','cancelled','failed')

    def title(self,ready):
        if self.phase=='busy':return _('Configurando acesso USB…')
        if self.phase=='cancelled':return _('Configuração cancelada')
        if self.phase=='failed':return _('Não foi possível configurar o acesso USB')
        return _('Atualizar o suporte USB') if ready else _('Prepare o acesso USB')

    def description(self,ready):
        if self.phase=='busy':return _('Conclua a autorização na janela do sistema. Ao terminar, o app verifica o resultado.')
        if self.phase=='cancelled':return _('Seus modos e preferências foram mantidos. Quando quiser, tente novamente.')
        if self.phase=='failed':return _('Confira os detalhes abaixo e tente novamente. Seus nomes e modos salvos continuam disponíveis.')
        if ready:return _('O Linux pedirá autorização para atualizar o suporte. Os controles reconectam nos modos salvos após a atualização.')
        return _('O Linux pedirá sua senha para instalar o suporte USB. A autorização vale para este app na sua sessão local.')

    def action(self,ready):
        if self.phase=='busy':return _('Aguarde…')
        if self.phase in ('cancelled','failed'):return _('Tentar novamente')
        return _('Atualizar suporte USB') if ready else _('Configurar acesso')


@dataclass
class ControllerState:
    identity: str
    name: str
    port: str = ''
    connected: bool = True
    requested: str = 'play'
    effective: str = 'play'
    confirmed: bool = False
    fresh: bool = False
    reading: dict | None = None
    error: str = ''
    helper_ready: bool = True
    transition: bool = False
    native_game: str | None = None
    observation: str = ''
    rgb: list | None = None
    appearance: str = 'neutral'
    guard_reason: str = ''

    @property
    def tone(self):
        if self.error: return 'error'
        if not self.connected or not self.fresh: return 'muted'
        return MODES[self.effective][2]

    @property
    def title(self):
        if not self.connected: return _('Desconectado')
        if self.error: return _('Precisa de atenção')
        if not self.helper_ready: return _('Configuração inicial')
        if self.transition: return _('Mudando de modo…')
        if not self.confirmed: return _('Aguardando confirmação…')
        return _('Só carregando') if self.effective == 'charge' else _('Pronto para jogar')

    @property
    def availability(self):
        if not self.connected: return _('Preferências salvas para a próxima conexão.')
        if not self.confirmed: return _('Aguardando o controle confirmar a conexão.')
        if self.effective == 'charge': return _('Oculto da Steam e dos jogos.')
        return _('Disponível para a Steam e os jogos.')

    @property
    def can_change(self):
        return self.connected and self.helper_ready and not self.transition and not self.identity.startswith('connection:')

    @property
    def can_customize(self):
        return self.can_change and self.confirmed and self.fresh and self.effective == 'proxy' and not self.error

    @property
    def charging(self):
        return bool(self.connected and self.fresh and self.reading and self.reading.get('status') == 'Charging')

    @property
    def battery_label(self):
        if not self.reading: return _('Aguardando leitura')
        if not self.fresh or not self.connected: return _('Última leitura · ') + self.reading.get('time', '—')
        return {'Charging':_('Carregando'), 'Full':_('Bateria cheia'),
                'Discharging':_('Usando a bateria'), 'Not charging':_('Sem carga informada')}.get(self.reading.get('status'), _('Estado não informado'))


def confirmed_mode(mode, status, fresh, kind, physical_available=False):
    if not fresh: return False
    if mode == 'play': return kind == 'direct' and physical_available
    if status.get('mode') != mode or not status.get('exclusive'): return False
    return mode == 'charge' or bool(status.get('virtual_started'))


def mode_consequence(current, target, native_game=None):
    if target == 'charge':
        return _('O controle sai dos jogos e seus efeitos são desligados. A bateria continua sendo acompanhada.')
    if target == 'proxy' and native_game:
        return _('A regra de {0} mantém o acesso direto enquanto esse jogo estiver aberto. Depois, volta ao app.').format(native_game)
    if target == 'play':
        return _('Suas preferências de luzes, vibração e peso dos gatilhos ficam pausadas. O jogo e a Steam passam a controlar os efeitos. A troca reconecta o controle ao sistema.')
    if current == 'play':
        return _('Suas preferências passam a ter prioridade. O jogo recebe um controle virtual; a troca reconecta o controle ao sistema.')
    return _('O controle volta a aparecer nos jogos, com as preferências de luzes e vibração do app.')
