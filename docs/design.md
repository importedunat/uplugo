# Decisões de interface

A principal tarefa é escolher como cada controle será usado. A tela mostra o
controle físico, sua bateria, quem recebe seus comandos e as três alternativas.

## Instalação e remoção

O assistente apresenta uma operação por vez, requisitos explicados e uma ação
principal que descreve o próximo passo: instalar, atualizar, recuperar, remover
ou abrir. Arquivos e mensagens técnicas ficam em seções expansíveis. A seleção
de idioma não altera as preferências do aplicativo.

As condições são verificadas ao abrir e novamente antes de executar. App aberto,
download incompleto e recuperação pendente impedem a operação correspondente;
a mensagem explica o próximo passo. Remover as permissões USB é uma escolha
separada e desmarcada inicialmente. O removedor administrativo precisa concluir
antes de excluir arquivos do usuário. Não há confirmação genérica adicional:
a prévia e o botão de remoção mostram a consequência concreta.

Não é possível prever uma porcentagem de conclusão para esses comandos. Um
indicador de atividade e texto descrevem a operação; uma thread executa o
trabalho e publica o resultado no loop principal do GTK. Os botões permanecem
visíveis em telas pequenas, com o conteúdo rolável. O fechamento é bloqueado
somente durante a operação, para não interromper uma alteração de arquivos.

Referências: [ações e botões no GNOME HIG](https://developer.gnome.org/hig/patterns/controls/buttons.html),
[indicadores de progresso](https://developer.gnome.org/hig/patterns/feedback/progress-bars.html)
e [threads em PyGObject](https://pygobject.gnome.org/guide/threading.html).
São decisões aplicadas ao GTK existente, verificadas em testes da janela real.

O assistente aberto pelas Preferências usa um escopo systemd separado quando
há um gerenciador de usuário. Encerrar o app para atualizar não deve matar a
janela de manutenção junto com os processos do serviço. Sem esse gerenciador,
um processo separado mantém a janela. O comportamento de encerramento vem de
[systemd.kill](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml)
e a separação de escopos usa [systemd-run](https://github.com/systemd/systemd/blob/main/man/systemd-run.xml).
O teste opcional `python3 tests/setup_lifecycle.py --systemd` cria somente um
serviço sintético temporário e confere se seu processo de teste permanece vivo
após o serviço terminar; não abre a interface nem toca nos controles.

## Pesquisa aplicada

Consultadas em 14–15/10/2026:

| Referência | Aplicação neste app |
| --- | --- |
| [Heurísticas de Nielsen](https://www.nngroup.com/articles/ten-usability-heuristics/) | Modo confirmado visível, escolhas reconhecíveis, consequências antes de trocar, cancelamento e bloqueio de ações após desconexão. |
| [Botões no GNOME HIG](https://developer.gnome.org/hig/patterns/controls/buttons.html) | Alternativas relacionadas agrupadas; ações secundárias discretas; menos botões em formato de cápsula; foco visível. |
| [Feedback no Apple HIG](https://developer.apple.com/design/human-interface-guidelines/feedback) | Retorno junto ao controle afetado e rascunhos identificados, reduzindo avisos globais persistentes. |

A prevenção de erros (poka-yoke) é aplicada a situações concretas: o modo é um
rascunho até confirmar; a confirmação mostra o nome do controle e a consequência;
identidade e conexão são verificadas novamente antes de agir. Uma troca pendente
bloqueia outra. Não há confirmação extra para consultar dados ou abrir um teste.

## Direção visual

- Um seletor mantém nomes, bateria e modos dos controles à vista; a área abaixo
  mostra o controle escolhido em destaque. Fotos usam recortes transparentes
  quando disponíveis; imagens importadas podem trazer um fundo próprio.
- Conteúdo central limitado a 1080 pixels; maximizar não estica os controles pela tela inteira.
- Grafite, branco e azul. Âmbar indica carga recebida, não simplesmente o modo Só carregar.
- Logotipo próprio: um "p" minúsculo cuja barriga é o anel de carga, com um
  trecho âmbar. Sem silhueta de gamepad nem símbolos oficiais da Sony. O mesmo
  ícone é usado no menu, janela e bandeja.
- Cor e forma da carcaça permanecem separadas da cor de luz. Fotos têm escala e
  margens ajustadas na apresentação. O recorte da foto preta foi feito apenas na
  biblioteca pessoal, com o original preservado fora do repositório.
- Botões mostram texto, estado e ✓; a cor nunca é a única indicação.

As fotografias ficam na biblioteca pessoal. Downloads em segundo plano, cache,
pausa e nova tentativa continuam em Preferências → Fotos dos controles. Quando
não existe foto, a ilustração é identificada como tal. A prévia pública usa dados
fictícios e ilustrações próprias.

## Fluxos verificados

1. Escolher outro modo não envia comando antes de confirmar. Desconectar antes
   de confirmar impede a ação. A tela marca o modo somente depois da confirmação.
2. Escolher cor ou gatilho é um rascunho. Cancelar preserva as preferências.
   Salvar revalida o controle. O teste de vibração usa ajustes já salvos, e fica
   indisponível enquanto existe um rascunho diferente.
3. Testar botões não altera o modo. O painel diferencia pressionado agora, já
   observado e ainda não observado. Leituras antigas limpam os valores ativos;
   ausência de registro não é apresentada como defeito.
4. Atualizar bateria preserva os widgets e o foco. Porcentagem antiga não anima.
   Bateria e conexão mostra mudanças efetivamente observadas e não inventa tempo
   restante, corrente de carga ou saúde da bateria.
5. Fechar mantém a bandeja; sem bandeja, a janela é minimizada. O laboratório é
   uma janela separada e pode ser encerrado sem afetar o app real.
6. Compatibilidade dos jogos explica a troca automática, seu alcance e os efeitos
   pausados. IDs e executáveis ficam em uma seção avançada. Cancelar preserva as
   escolhas; Salvar conserva os modos e as demais preferências atuais.

A interface oferece português do Brasil, inglês e espanhol. O seletor usa os
nomes próprios dos idiomas, salva a escolha e refaz apenas os widgets de texto;
as sessões USB permanecem ativas. Identificadores de modos, grupos e efeitos
continuam estáveis, independentemente dos rótulos traduzidos.

## Teclado e nomes acessíveis · revisão de 17/10/2026

Seguindo o [GNOME HIG de acessibilidade](https://developer.gnome.org/hig/guidelines/accessibility.html),
as ações repetidas recebem o nome do controle e um ID curto, inclusive quando
dois controles têm o mesmo apelido. Atualizações iguais não reemitem o nome
acessível continuamente. O modo ativo só é anunciado com uma leitura confirmada;
a barra de bateria fica oculta enquanto a capacidade é desconhecida.

Os rótulos e explicações de vibração/gatilhos estão associados aos campos via
[relações ATK](https://docs.gtk.org/atk/method.Object.add_relationship.html).
As cores usam botões com estado selecionado nativo, além de ✓ visível. Escolher
uma cor continua sendo um rascunho, inclusive pelo teclado. Uma cor personalizada
limpa a seleção dos presets e informa o valor hexadecimal no seletor.

A confirmação de modo mantém o comportamento de teclado do GTK: foco inicial
em Cancelar, Tab/Shift+Tab entre ações, Espaço para ativar e Esc para cancelar
e voltar ao botão original. Invalidar a conexão também invalida a confirmação
se o GTK já tiver fechado o popover. O diálogo de efeitos tem rolagem interna,
com as ações finais fora da área rolável.

Os testes percorrem esses fluxos em português, inglês e espanhol, com eventos de
teclado no Xvfb e inspeção local do ATK. Isso não substitui um teste humano com
Orca/AT-SPI, alto contraste, teclado virtual, outras janelas ou Wayland. A escala
200% foi exercitada nesses fluxos; a revisão de todas as telas continua pendente.

## Espaço disponível e tema do sistema · revisão de 17/10/2026

A janela principal limita seu tamanho inicial ao monitor. As linhas se
reorganizam conforme a largura dos textos: fotos menores ao lado de suas ações
quando o cartão fica vertical, modos empilhados quando necessário, cabeçalho
e rodapé capazes de ocupar mais de uma linha. A área central inteira rola, de
modo que avisos e configuração não consumam todo o espaço reservado aos controles.
As preferências também têm rolagem limitada pelo monitor ao abrir o menu.

`AdaptiveBox` mede as alternativas sem mudar os widgets durante a medição.
A orientação só muda ao receber a área real: isso evita um ciclo contínuo de
recalcular o tamanho. As medidas incluem bordas e espaçamento CSS. Redimensionar
mantém os mesmos objetos, callbacks e foco; não solicita troca de modo.

As fontes usam proporções da fonte GTK, incluindo sua escala de texto. O CSS
de estrutura fica separado da paleta grafite/azul. Ao reconhecer um tema GTK
HighContrast, o app retira a paleta própria e usa as cores nativas. A troca
é observada durante a sessão. Fotos e amostras de luz mantêm suas cores de
conteúdo; o blueprint e os gráficos ainda precisam de revisão específica de
contraste, além de suas informações textuais alternativas.

Essa abordagem segue a recomendação de reduzir cores fixas e testar alto
contraste do [GNOME HIG](https://developer.gnome.org/hig/guidelines/ui-styling.html).
Os testes locais alteram configurações GTK somente dentro do processo isolado.
A integração com cada painel de acessibilidade de GNOME/KDE e outros temas
ainda precisa de validação em sessões reais.

## Nome, aparência e biblioteca · revisão de 17/10/2026

O nome tem rótulo permanente, atalho de teclado e descrição acessível, seguindo
as orientações de [campos de texto do GNOME HIG](https://developer.gnome.org/hig/patterns/controls/text-fields.html).
O ID curto indica qual controle está em edição. Nome e modelo permanecem como
rascunho até Salvar, inclusive com o controle desconectado ou em outra porta.
Salvar lê as preferências atuais e altera apenas esses dois campos por identidade;
mudanças de modo, idioma ou de outro controle feitas durante a edição são mantidas.
Falha de gravação conserva o rascunho e permite repetir a tentativa.

A galeria permite de uma a três colunas conforme o espaço disponível, usando
[o comportamento de FlowBox](https://docs.gtk.org/gtk3/method.FlowBox.set_min_children_per_line.html).
Uma única área rolável contém o formulário e os modelos; Cancelar e Salvar ficam
fora dela. Títulos e origem das imagens quebram linha, e a seleção tem ✓ e estado
nativo. Busca e grupo preservam a escolha, mesmo quando ela não está nos resultados.
Um estado vazio oferece limpar os filtros. Enter na busca não confirma a edição.

A gestão de fotos abre uma janela própria, com Fechar. Ela explica que as fotos
são compartilhadas pelos controles do mesmo modelo e salvas ao adicionar. O
seletor informa o modelo de destino e a ação Adicionar à biblioteca. Cancelar o
seletor não grava; uma imagem inválida não substitui a anterior. Cancelar a edição
de nome/modelo preserva uma foto que o usuário adicionou explicitamente nessa
biblioteca. Downloads em segundo plano não alteram o rascunho nem tomam seu foco.

## Primeiro uso · revisão de 16/10/2026

Foram consultados [onboarding no Apple HIG](https://developer.apple.com/design/human-interface-guidelines/onboarding)
e [estados vazios no GNOME HIG](https://developer.gnome.org/hig/patterns/feedback/placeholders.html).
A ajuda é opcional e fica junto da tarefa. Sem controles, a tela explica cabo e
conexão, mostra o seletor de idioma e oferece uma demonstração sem hardware.
O título genérico “Seus controles” cede espaço à orientação de conexão nesse
estado. Com controles conectados, nomes, bateria e ações permanecem no centro.

“Qual modo usar?” parte da intenção: carregar fora dos jogos, jogar com efeitos
próprios ou receber os recursos nativos do jogo. O guia não escolhe um modo e não
envia comandos. Mapeamento de jogos/emuladores fica em uma explicação expansível.
O diálogo tem rolagem e altura limitada à área disponível do monitor.

A autorização USB mostra a finalidade antes do clique. Cancelamento, falha,
operação em andamento e resultado verificado têm apresentações diferentes;
erros técnicos ficam em uma área expansível. O seletor de idioma respeita a
preferência salva e, na ausência dela, usa o idioma suportado da sessão. Fallback
em inglês. Esses fluxos foram exercitados em conta simulada; a compreensão por
uma pessoa que não participou do desenvolvimento ainda precisa ser observada.

Foram revisados tamanhos 820 × 760, 1040 × 880 e 1850 × 990. Janelas pequenas
usam rolagem vertical. Isso não substitui testes de usabilidade com pessoas nem
homologa todos os temas, leitores de tela, escalas ou ambientes Linux.

## Área de um controle · revisão de 17/10/2026

A tela principal agora usa um seletor de controles com imagem, nome, bateria e
modo de cada um. Selecionar um controle revela sua área de trabalho; não envia
comandos USB nem modifica o modo. A seleção é mantida durante atualizações e
mudanças na ordem de descoberta. Setas, Home e End também navegam pelo seletor.

A foto maior ancora a identidade. Os três modos ficam juntos, com símbolos,
rótulos curtos e marca de confirmação. Quatro atalhos expõem luzes/efeitos,
teste de botões, touchpad/cursor e bateria/conexão. Ações indisponíveis mantêm
seu lugar; uma orientação curta explica como habilitar a personalização.
Explicações repetidas saíram da tela estável, mas erros, leitura antiga e regras
ativas continuam visíveis. Selecionar outro controle fecha o rascunho anterior.

A confirmação mostra o caminho dos comandos com ícones e continua explicando a
consequência antes de aplicar. A transição entre controles usa uma dissolução de
160 ms, respeitando a configuração de animações do GTK. Não há gestos exclusivos:
todas as ações têm botões e acesso por teclado. Não se trata de certificação de
usabilidade; ainda falta observar uma pessoa usando a nova organização.

Referências consultadas: [botões](https://developer.apple.com/design/human-interface-guidelines/buttons),
[movimento](https://developer.apple.com/design/human-interface-guidelines/motion) e
[revelação de conteúdo](https://developer.apple.com/design/human-interface-guidelines/disclosure-controls)
do Apple HIG. Aplicação: hierarquia, feedback localizado e revelação gradual,
sem copiar controles de janela ou materiais exclusivos de outra plataforma.

## Ajuda contextual e edição visual · alpha.28

A janela inicia em 1000 × 700, com margens e grupos mais compactos. A ajuda
ancora cada passo em um elemento real, acompanha a rolagem e termina ao mudar
ou remover o controle. Os passos não ativam as ações que explicam.

Luzes e efeitos usa três abas: Luz, Vibração e Gatilhos. Um desenho do controle
mostra a cor e o tipo de efeito em edição. As escolhas têm estado marcado;
visualizar não envia comandos. Os testes físicos continuam explícitos: mudar
aba ou fechar encerra o teste temporário e restaura a configuração anterior.

## Jogos · alpha.29

O botão Jogos abre a troca automática opcional. Uma sequência de três ícones
mostra antes, durante e depois do jogo. Só carregar fica fora dessa sequência.
A busca tolera acentos e conserva escolhas ocultas; o resumo inclui jogos
adicionados manualmente. Sem escolhas, a troca automática aparece desligada.
As limitações de efeitos e reconexão ficam em detalhes expansíveis. Um erro de
validação ou gravação mantém o rascunho. A tela não afirma compatibilidade nativa
com base apenas na existência do jogo na biblioteca.

## Touchpad e bateria · alpha.30

A opção de cursor oferece uma demonstração local: arrastar o ponto ou usar as
setas move o cursor ilustrado quando o padrão está escolhido; a alternativa sem
cursor mantém a seta parada e exibe um cadeado. A prévia é separada do estado
"No Linux agora" e nunca envia entradas ou solicita autorização. A autorização
permanece apenas em Aplicar. O alcance (este controle, todas as contas, persistente)
fica visível; os detalhes de reaplicação e remoção estão em uma seção expansível.

A bateria mostra um gráfico em degraus das porcentagens recebidas no período
atual. A curva termina na última leitura, sem previsão; uma amostra isolada é
um ponto. Uma nova observação não é ligada à anterior. Leituras antigas ficam
identificadas e o gráfico perde o destaque de leitura atual. Valores exatos,
interpretação e histórico anterior ficam disponíveis em expansores. O desenho
usa cores do tema e rótulos que acompanham a fonte do desktop.

## Preferências · alpha.31

Uso diário, proteção automática e destinos têm grupos separados. Fotos e acesso
USB permanecem diretos; diagnóstico e instalação ficam em Ferramentas e manutenção.
Ícones identificam os destinos, setas indicam abertura de outra tela e sair tem
seu próprio separador. Abrir um destino fecha o menu antes de exibir a próxima tela.

A suspensão ao escolher Jogar fica recuada e indisponível quando a proteção está
desligada, preservando a escolha salva. Reativar a proteção recupera essa escolha
sem alterações implícitas. O funcionamento periódico continua explicado em um
expansor, enquanto Só carregar mantém seu comportamento independente. A largura
do menu acompanha o espaço da janela; rolagem mantém as ações acessíveis.

## Testar botões · alpha.32

Pressionado agora usa um ponto preenchido; já observado usa uma marca de seleção.
A mesma distinção aparece no desenho e no checklist, inclusive sem depender da cor.
O contador e a barra de progresso vêm antes dos detalhes; contam botões observados,
sem emitir diagnóstico de defeito. Reiniciar limpa esse progresso, e uma leitura
antiga remove o estado pressionado preservando o que já respondeu.

As abas nativas se empilham quando necessário. O checklist e as colunas dos
analógicos se reorganizam; detalhes e ações continuam alcançáveis por rolagem.
A medição de largura não reutiliza a largura antiga da imagem ou da orientação
horizontal após reduzir a janela. Nada neste fluxo aplica efeitos ou muda modos.

## Diagnóstico e revisão dos guias · alpha.33

Desenvolvimento e diagnóstico apresenta o laboratório separado, a contagem de
dependências necessárias disponíveis e a quantidade de controles conectados
naquele retrato. Esses números não certificam o funcionamento do hardware.
O JSON completo fica em Ver relatório completo; copiar dá confirmação local
e atualizar remove essa confirmação. O relatório continua filtrando os dados
pessoais. Atualizar e copiar ficam fora da rolagem do conteúdo.

Os guias acompanham o seletor de controles e o novo caminho Ferramentas e
manutenção. As imagens principais, compacta, alto contraste, teste de botões
e bateria foram renderizadas novamente com dados fictícios. Elas usam somente
ilustrações incluídas no projeto, sem fotos da biblioteca pessoal.


## Propósito das funções · alpha.34

Testes de uso mostraram que localizar as ações não bastava: faltava entender
por que usá-las. As quatro ferramentas agora têm uma descrição de finalidade
visível, além do nome, ícone e descrição acessível. As ferramentas se reorganizam
em pares na janela estreita. O resultado do modo atual
continua visível mesmo depois de uma troca confirmada.

“Modo por jogo” substitui o rótulo ambíguo “Jogos”. A tela apresenta a situação
de uso: manter os próprios efeitos no dia a dia e deixar um jogo escolhido cuidar
deles. Explica que a configuração é opcional, que não é preciso cadastrar jogos
para jogar e que os itens instalados não certificam suporte nativo. O exemplo
mais detalhado permanece recolhido junto das consequências de conexão.

A ajuda guiada acompanha essa linguagem de finalidade. Os textos existem nos
três idiomas. Esta revisão não modifica detecção de jogos, modos ou efeitos.

## Uplugo · alpha.35

O app passou a se chamar Uplugo. Os IDs internos (pastas, serviço, regras USB)
continuam iguais, então instalações existentes seguem funcionando.

Os modos de jogo foram renomeados pelo efeito que a pessoa sente, não pelo
caminho técnico: "Minhas configurações" e "Configurações do jogo". Cada botão
ganhou uma linha curta embaixo do nome.

Nova opção em Preferências: abrir ao ligar o computador. O app começa na bandeja
e não muda os modos salvos.
