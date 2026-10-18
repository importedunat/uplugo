# Plano de evolução

Objetivo: um gerenciador DualSense abrangente para Linux, polido e fácil de
entender. Uma execução de testes ou um pacote instalável, isoladamente, não
comprova esse objetivo. Este plano mantém o escopo completo e indica a evidência
necessária para avançar. Estado revisto em 2026-10-17.

## Fundação e distribuição

- **Implementado e testado em userspace:** instância única com D-Bus, abertura
  sem systemd de usuário, bandeja com fallback, diretórios XDG, instalação por
  usuário independente da pasta de download e preservação das preferências.
  Pacote alpha de código-fonte com lista explícita, SHA256 por arquivo,
  reconstrução reproduzível e instalação testada a partir da cópia extraída.
  Suíte compartilhada e relatórios de versões/etapas: Ubuntu 24.04, Debian 13 e
  Fedora 44 passaram em userspace isolado, com dependências configuradas. CI para Debian/Fedora
  preparado; execução remota e hardware continuam separados dessa evidência.
- **Manutenção implementada:** bloqueio de atualização com app aberto, registro
  dos arquivos instalados, prévia de remoção e preservação de dados/arquivos
  alterados. Remoção administrativa separada com autenticação, verificação de
  conta e restauração em falhas simuladas. Atualização preparada separadamente,
  troca atômica da árvore, journal de recuperação e janela de recuperação em
  três idiomas. Encerramentos forçados em commit, rollback e limpeza testados,
  com preservação de arquivos desconhecidos e bloqueio de abertura pendente.
  Assistente gráfico de instalação, atualização, recuperação e remoção em três
  idiomas, com requisitos explicados, prévia, progresso, falhas recuperáveis e
  opção administrativa separada. Testes GTK e operações em arquivos temporários
  verificam preservação dos dados e cancelamento de autorização simulado.
  Guias de atualização e remoção.
  A alpha.26 avisa quando o serviço USB instalado difere do conteúdo do app,
  sem pedir autorização, mudar modos ou reiniciar controles. A comparação em
  segundo plano distingue revisão manual de manutenção pelo gerenciador de
  pacotes; não equivale a uma validação de segurança ou do hardware.
- **Empacotamento nativo experimental:** os gerenciadores resolvem dependências
  antes de abrir o assistente gráfico; a tradução dos comandos técnicos continua pendente.
  Download com arquivo ausente já é recusado antes de substituir a instalação.
  A preparação do acesso USB já funciona sem escrever na pasta do programa;
  solicitações usam temporários privados e deixam o GTK responsivo. O helper
  manual gerado permanece idêntico. Propriedade de arquivos, concessões e ciclo
  de vida já estão integrados aos gerenciadores `.deb`/`.rpm`; veja os limites e
  a validação ainda necessária em [instalação nativa](native-packaging.md).
  O perfil do sistema já abre os próprios arquivos, separa helper/unidade,
  impede cópia por usuário e identifica conflitos com instalações antigas.
  O assistente explica a propriedade pelo gerenciador. Concessões nativas por
  conta já têm administrador fixo, política, verificação no helper e revogação
  pelo assistente. Testes isolados preservaram outras contas, dados e arquivos
  do pacote; repetir uma configuração válida não reiniciou os controles.
  A alpha.16 gera `.deb`/`.rpm` e passou por instalação, atualização, reparação,
  remoção e reinstalação reais em APT/dpkg e DNF/RPM isolados. O estado persistente
  bloqueia novas aberturas durante a manutenção e recusa alterar uma sessão ativa.
  A alpha.17 acrescenta aviso gráfico de manutenção na abertura pelo menu,
  traduzido e independente dos arquivos visuais, com nova abertura em processo
  limpo após reparo. A alpha.18 implementa migração guiada da instalação antiga,
  inclusive sem registro, com arquivamento integral, importação sem sobrescrita,
  recuperação e limpeza administrativa opcional. Testes isolados cobrem SIGKILL
  e retomada nos três idiomas. Migração em sessão real, revisão das convenções
  de empacotamento e validação de polkit numa sessão local continuam pendentes.
- **Pendente de evidência real:** primeira autorização administrativa em conta
  limpa, Ubuntu/Debian/Fedora, GNOME/KDE, Wayland/X11 e reinstalação/remoção do
  helper. Containers verificam bibliotecas; VM com USB ou máquina real verifica
  acesso ao hardware. Recuperação após queda de energia real/VM e filesystems
  diferentes ainda precisa de matriz própria, além do SIGKILL já testado.
  Não anunciar suporte universal antes dessa matriz.
- **Publicação:** revisar conteúdo do Git e licenças, gerar pacote a partir de
  uma cópia limpa (geração/testes locais concluídos), executar CI remoto e testar instruções de instalação com outra
  pessoa. `tests/git_inventory.py` compara a seleção do Git com o inventário e
  os arquivos atuais antes dos testes no CI; não prepara commits nem verifica
  segredos/licenças. Repositório remoto e primeira versão pública ainda não foram definidos.

## Clareza e apresentação

- **Implementado:** português, inglês e espanhol; modo solicitado separado do
  confirmado; consequências antes da troca; nomes por identidade; confirmação
  física por luzes; biblioteca de aparências; logotipo próprio; teste por blueprint.
  Guias de primeiro uso em inglês e espanhol, com nomes iguais aos da interface.
  Idioma inicial acompanha o sistema; seletor visível sem controle. Ajuda opcional
  por intenção de uso, orientação de conexão e acesso ao laboratório sem hardware.
  Configuração USB diferencia cancelamento, falha, espera e resultado verificado,
  com nova tentativa e preservação das escolhas em caso de falha.
- **A validar/melhorar:** primeiro uso sem orientação do autor, explicações de
  compatibilidade por jogo, navegação integral por teclado e leitor de tela,
  escala 200%, telas pequenas, abertura de diálogos no monitor secundário e
  revisão humana das traduções.
  Os fluxos de modo e efeitos já têm testes de teclado e nomes/estados ATK nos
  três idiomas; efeitos têm rolagem com ações acessíveis em 200%. Ainda falta
  revisão humana com Orca/AT-SPI, alto contraste e o restante das telas.
  A janela principal agora se reorganiza em larguras menores, respeita fonte
  e escala de texto GTK e usa a paleta de temas GTK HighContrast. Há testes
  isolados de redimensionamento, foco, menus e configuração. A revisão humana
  de alto contraste, gráficos/blueprint e demais diálogos continua pendente.
  Nome/aparência e a biblioteca de fotos agora têm rolagem limitada à tela,
  escolha em rascunho, filtros com estado vazio e recuperação de erro ao salvar.
  A revisão humana de nomes, fotos compartilhadas e leitor de tela ainda falta.
- **Catálogo:** completar fotos que faltam, normalizar enquadramento e tratar
  fundos de forma consistente, mantendo origem/licença e alternativa offline.
  Um recorte na biblioteca pessoal não representa melhoria distribuída a todos.

## Controle, jogos e recuperação

- **Implementado:** carga exclusiva, DualSense virtual, acesso direto, cores,
  vibração, presets de gatilhos e exceções por jogo. Há confirmação física local
  de parte desses recursos em DualSense padrão; os limites estão na validação.
- **A completar:** matriz por jogo/emulador, testes físicos dos demais pesos de
  gatilho, desconexão durante efeitos, recuperação após suspensão/retomada,
  falha de helper e várias unidades conectadas em ordens diferentes.
  A alpha.24 corrige erros e leituras antigas quando a mesma porta é reutilizada
  entre atualizações da tela; aguarda a saída do processo anterior sem bloquear
  GTK. Testes com processos simulados cobrem mensagens tardias e preservam os
  modos e o outro controle. Retomada física e continuidade nos jogos ainda faltam.
  A alpha.25 trata fim de leitura e falta temporária de dados no helper direto,
  encerra seu teste de vibração explicitamente e impede ações pontuais de avançar
  antes da saída do processo antigo. Testes incluem descritores/processos reais
  em arquivos temporários, sem USB. A correção do helper exige atualizar também
  o suporte USB na instalação por usuário.
- **PCSX2:** funciona em Configurações do jogo com mapeamento SDL. Em Minhas
  configurações, falta testar botões e vibração enviada pelo jogo.
- **Touchpad em Configurações do jogo:** a opção por controle impede o cursor do
  Linux de se mover e há uma permissão opcional para a Steam Snap. Falta testar
  dois contatos, outros desktops e mais jogos. O mapeamento de mouse da Steam é
  independente. Veja [touchpad e Steam](linux-support.md#touchpad-e-steam).
- **Cobertura de hardware:** testar Edge físico e firmwares distintos. Avaliar
  Bluetooth como uma extensão própria de transporte, com relatórios e limites
  documentados; o código atual continua exclusivamente USB. Áudio/háptica USB
  nativa completa usa acesso direto, não o proxy HID atual.

## Bancada e dados úteis

- **Implementado:** checklist de botões, analógicos, curso dos gatilhos e até
  dois pontos de toque no blueprint, com coordenadas nos detalhes,
  histórico de bateria observada com até 24 períodos anteriores por controle e porta USB, diagnóstico sem identificadores e laboratório
  que não abre USB. Entradas não são persistidas nem enviadas.
  Roteiro dos analógicos com cinco segundos de repouso, alcance, centro médio,
  faixas observadas e gráficos; interrupções não unem medições de sessões distintas.
- **Próximo:** conferência física dos dois contatos do touchpad e do roteiro de
  analógicos e dos eixos de movimento calibrado. A alpha.20 implementa a
  visualização de giroscópio/acelerômetro com calibração de fábrica somente para leitura;
  dois controles padrão forneceram calibração e relatórios válidos. Explicar o que foi medido
  antes de tirar qualquer conclusão sobre defeitos.
- **Carga:** períodos anteriores já sobrevivem a reconexões, com horários,
  porta USB e variação informada, sem somar intervalos sem dados. Falta validar
  o fluxo em uso físico prolongado. A alpha.22 acrescenta anotações manuais de
  cabo/condições por período, inclusive períodos anteriores. Reconexão durante
  a edição preserva o vínculo com a observação escolhida; as anotações não entram
  nos diagnósticos exportados. Falta revisão de uso prolongado por outra pessoa.
  O app não identifica o cabo nem estima corrente, saúde ou tempo restante.
- **Desempenho:** medir chegada de relatórios e custo da interface; distinguir
  isso de latência do jogo/tela. Adicionar cenários de longa duração sem desgastar
  motores ou manter gatilhos sob carga para provar estabilidade do software.
  Já foi removido o redesenho do blueprint escondido durante o teste dos
  analógicos; a coleta continua e a aba recebe o estado atual ao reaparecer.
  Um benchmark reproduzível mede o custo local com entradas simuladas; não
  representa latência USB nem uma promessa para todas as máquinas.

## Critério de conclusão

Cada capacidade anunciada precisa de um cenário reproduzível, resultado visível
correto e comportamento definido quando o recurso ou a permissão não existe.
Recursos que dependem de sensação física, jogos, drivers ou autorização não ficam
concluídos apenas com mocks. A documentação deve distinguir implementado,
simulado, confirmado no hardware e ainda não testado. A matriz de suporte e a
experiência de instalação/uso precisam sustentar as promessas da versão pública.
