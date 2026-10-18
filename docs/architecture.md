# Arquitetura

window.py coordena sessões; ui.py contém widgets persistentes; presentation.py
calcula estados e bloqueios. Atualizações não recriam as linhas dos controles. Workers se
comunicam com GTK pelo GLib.

```text
DualSense físico → libusb exclusivo → helper
                                      ├─ Só carregar: bateria, sem entrada virtual
                                      └─ Minhas configurações: UHID → jogos/Steam
                                               ↑ saída filtrada
Configurações do jogo: DualSense físico → hid-playstation → jogos/Steam
```

O helper combina dualsense.py, input_state.py, usb_charge.py e broker.py. Sua cópia instalada em
`/usr/local/libexec/dualsense-usb-helper` pertence ao root. O polkit autoriza esse
executável fixo para a sessão local ativa do instalador. Ele valida argumentos,
conexão e IDs USB Sony e não importa módulos da pasta editável pelo usuário.

`touchpad_policy.py` descobre somente nós de touchpad Sony USB com identidade
permanente e produz uma regra `LIBINPUT_IGNORE_DEVICE` por controle. Ela conserva
o dispositivo e seus relatórios para consumidores que não usam libinput.
`touchpad_ui.py` separa rascunho, política salva e propriedades do udev; não afirma
conhecer o estado interno do compositor ou da Steam. A escolha vale para todas as
contas do computador e permanece até restauração explícita, inclusive sem o app.

`touchpad_admin.py` é uma ação administrativa separada do helper de entrada.
A versão nativa é instalada em `/usr/libexec/dualsense-usb-touchpad` com política
própria que exige `auth_admin`; a instalação por usuário gera um pedido Python
autocontido em pasta temporária privada. Ambos aceitam somente `game`/`system`
e identidade canônica. Não há argumento de destino, comando ou caminho sysfs.
A regra fica em `/etc/udev/rules.d/99-dualsense-usb-touchpad-<identidade>.rules`;
arquivos personalizados, links, permissões inadequadas e hardlinks são recusados.
Um bloqueio global serializa mudanças, que usam substituição atômica e fsync.

Após recarregar regras, o administrador solicita eventos udev remove/add apenas
para o caminho completo do nó de toque validado, com filtro de subsistema/nome.
O caminho completo evita redirecionamento quando um número `eventN` é reutilizado.
Nenhum driver USB é desconectado. Falha tenta adicionar o nó novamente e restaurar
a regra anterior; a interface permite reaplicar após interrupção. Sem nó presente,
a regra é salva para a próxima conexão, sem sair de Só carregar. A sequência tem
testes com udev simulado; seleção da regra usa udev real em namespace. Aplicação
no compositor e preservação da função no jogo ainda exigem validação física.

`access_request.py` monta a solicitação administrativa em um diretório temporário
privado (`0700`, script `0600`). A pasta permanece até `pkexec` terminar e é removida
mesmo após cancelamento ou falha. O script é autossuficiente e mantém destinos
fixos; não recebe um diretório privilegiado arbitrário pela linha de comando.
`build_helper.py` gera seu conteúdo em memória. A escrita de scripts dentro da
árvore do programa permanece apenas na preparação de uma instalação por usuário,
antes de ela ser ativada. A interface em execução não precisa dessa permissão.
O GTK faz a preparação em worker e só reinicia sessões após confirmar o conteúdo
do helper instalado. Instalação e remoção via terminal usam a mesma solicitação.

`access_request.HelperRevision` compara o conteúdo instalado com o helper gerado
para o perfil manual/nativo em uma thread de leitura. A fonte esperada fica em
cache durante a sessão; dev/inode/tamanho/mtime/ctime evitam reler um arquivo
inalterado. As sondagens são agrupadas e espaçadas em cinco segundos. Ausência,
erro de leitura ou fonte indisponível não são anunciados como correspondência.
O aviso de diferença é separado da compatibilidade de protocolo e da autorização:
não inicia instaladores, não interrompe sessões nem impede os modos existentes.
O caminho nativo encaminha ao assistente e ao gerenciador de pacotes.
O caminho gráfico captura os diagnósticos e usa o agente de autorização do
desktop; o caminho de manutenção por CLI preserva os três fluxos do terminal.

`migration.py` transfere a conta para uma instalação nativa já existente, sem
executar código da versão antiga. A prévia vincula identidades dos arquivos,
dados a importar e registros pendentes à operação. Um bloqueio exclusivo impede
concorrência com os pontos de entrada atuais; também são verificados processos
legados e o serviço do usuário. `renameat2(RENAME_NOREPLACE)` arquiva cada objeto
inteiro no mesmo sistema de arquivos, sem substituir uma cópia anterior. Um
registro sincronizado acompanha interrupções; a retomada reconhece o objeto no
destino por dispositivo/inode/tipo/dono. Importações usam hash e nunca substituem
dados atuais. O histórico só é concluído após conferir os arquivos e recarregar
o gerenciador de usuário, quando disponível. A limpeza do suporte USB manual é
opcional, explícita e usa o administrador antigo, separado do pacote nativo.

O broker usa o descritor real e encaminha entrada sem remapeamento. Responde às
leituras conhecidas de calibração, identidade e firmware. SET_REPORT de feature,
gravação de calibração/NVS e firmware não são permitidos. UHID não virtualiza áudio.
Entre carga e proxy, criar/destruir o UHID mantém a mesma sessão libusb. Passar
para direto destrói o virtual antes de reanexar o driver físico. Encerrar ou uma
falha do helper pode liberar o dispositivo; não há isolamento após encerrar o
serviço. Quando disponível, o systemd tenta reiniciar a interface quando ela falha.

`session.py` usa `Gtk.Application` e o D-Bus da sessão para manter uma única
instância. Somente a instância primária constrói `Window` e inicia os helpers.
Outras aberturas ativam a mesma janela, inclusive quando está oculta. Sem D-Bus,
a abertura falha antes de criar uma sessão USB; não usa o fallback não exclusivo
do GApplication. Fechar para a bandeja mantém a janela registrada. Sair encerra
downloads e helpers uma única vez, tanto no loop GTK dos testes quanto no app.

`launch.py` primeiro ativa uma instância existente. Se não houver, prefere o
serviço systemd quando o gerenciador está disponível; caso contrário, executa a
mesma aplicação diretamente. Falha ao iniciar um serviço existente não dispara
uma segunda cópia independente. Instalações antigas ainda abertas são reveladas
pelo sinal já usado pelo serviço, sem uma atualização forçar a reconexão USB.
Sem systemd, não há supervisão/reinício automático em caso de falha.

As sessões de controle guardam a conexão USB que as originou, além da porta.
Uma reconexão na mesma porta entre duas atualizações também invalida mensagens,
erros e leituras da sessão anterior. O processo antigo recebe um pedido de saída;
enquanto ele continua vivo, não se inicia outro dono daquela porta. A interface
consulta o encerramento sem esperar no loop GTK; ao sair do app, preserva a espera
limitada de até três segundos por processo. Saídas tardias de processos anteriores
não alteram a sessão substituta. Uma falha inesperada na mesma conexão permanece
visível até uma nova tentativa explícita ou uma conexão nova, evitando repetições
automáticas de autorização. Os modos salvos e os outros controles são preservados.
As ações pontuais de leitura/identificação aguardam esse encerramento no worker,
com limite de três segundos. Conferem a conexão antes e depois do comando e
antes de aplicar seu resultado na janela; um resultado antigo não é registrado
como leitura de outro controle que ocupou a porta. Tentativas de leitura não são
repetidas após detectar uma troca de conexão.

No helper direto, `read()` sem bytes encerra a sessão, e `BlockingIOError` permite
continuar sem reaproveitar o pacote anterior. O encerramento por comando ganha
prioridade sobre uma entrada pronta no mesmo ciclo. A consulta pontual de bateria
também termina ao receber dados vazios. O prazo do teste de vibração é processado
mesmo quando não chegou uma leitura: ao vencer, envia motores em zero; `release`
também encerra o teste antes de devolver os efeitos ao jogo. Isso não altera o
formato dos relatórios nem a calibração do controle.

`charge_watch.py` mantém a observação atual e até 24 resumos anteriores por
identidade, no estado local do usuário. Uma nova conexão, intervalo de mais de
15 segundos ou regressão do relógio separa os períodos. O resumo termina na
última leitura, não no instante em que se abre a tela. A variação é entre a
primeira e a última porcentagem informada; pode incluir uso e carga. Não estima
corrente, velocidade, saúde nem tempo restante. O aviso de estagnação usa apenas
o trecho contínuo em que o controle informa `Charging`. A porta é registrada;
o cabo não tem identidade disponível. `charge_view.py` apresenta esses dados
sem abrir USB nem mudar modos. Históricos antigos são migrados em memória e
salvos na próxima observação; a escrita usa substituição atômica e arquivo 0600.
O diagnóstico exportado continua sem histórico detalhado, portas ou identidades.
Anotações manuais de até 160 caracteres ficam no mesmo arquivo privado. Cada
período tem um identificador aleatório persistente, independente de porta/relógio.
Salvar um editor aberto antes da reconexão altera somente seu período original;
um período descartado pelo limite não recebe a anotação em outro lugar. Falha
de escrita restaura a nota anterior em memória sem descartar leituras recentes.
Uma nova observação começa sem nota. O diagnóstico também omite essas anotações.

game_profiles.py confirma processos em
mais de uma leitura para evitar oscilações. install.py gera o atalho e a unidade
systemd para o usuário atual, sem conta ou caminho pessoal fixo no código.
Ele copia o código e os recursos para o diretório XDG de dados do usuário;
o atalho e o serviço não dependem da pasta de download. As configurações ficam
separadas e são preservadas nas atualizações.

`maintenance.py` mantém um bloqueio compartilhado enquanto a instância primária
está aberta e exclusivo durante instalação/remoção. A verificação de processos
também reconhece a entrada instalada de versões antigas, sem o bloqueio. Um
registro local de hashes permite remover apenas arquivos instalados inalterados;
dados pessoais e arquivos desconhecidos não entram na remoção. O programa precisa
estar encerrado para manutenção.

`setup.py`, `setup_ui.py` e `setup_state.py` apresentam os mesmos comandos de
instalação, recuperação e remoção em uma janela GTK. A consulta inicial não
escreve dados; a execução verifica as condições novamente e delega ao comando
que possui o bloqueio exclusivo. Workers retornam resultados via `GLib.idle_add`.
A autorização administrativa continua sendo uma opção explícita do removedor.
Quando iniciado pelas Preferências, o assistente usa um escopo systemd separado
se houver gerenciador de usuário, ou um processo independente no modo direto.
Assim, encerrar o app principal para manutenção não encerra a janela junto.

`install_transaction.py` prepara uma árvore completa, gera os scripts de acesso
nessa cópia, registra hashes e sincroniza os arquivos antes de tocar na versão
ativa. Um journal privado percorre `building`, `prepared` e `committed`. A troca
de diretórios usa `renameat2(RENAME_EXCHANGE)`; a primeira instalação usa rename
para um destino ausente. Não há fallback para sobrescrita arquivo por arquivo.
O marcador de geração também entra no registro da instalação e na remoção.

O ícone, o atalho, a unidade e o recibo usam temporários no próprio diretório de
destino, permitindo XDG de dados/configuração em filesystems distintos. Cópias
anteriores ficam na pasta privada da transação. Conteúdo e diretórios recebem
`fsync` antes dos marcos do journal. O protocolo segue as garantias documentadas
de [rename](https://man7.org/linux/man-pages/man2/rename.2.html) e
[fsync](https://man7.org/linux/man-pages/man2/fsync.2.html), mas não pressupõe que
hardware ou todo filesystem ofereça a mesma durabilidade após falta de energia.

Uma recuperação incompleta restaura a árvore anterior e seus arquivos externos;
um commit concluído somente termina a limpeza. A própria restauração/limpeza
pode ser retomada. Mudanças externas ou cópias inválidas interrompem a recuperação
antes de sobrescrever conteúdo não reconhecido. Pastas desconhecidas nunca são
escolhidas a partir de caminhos arbitrários no journal. Preferências dos controles, fotos,
histórico e arquivos administrativos ficam fora da transação.

A abertura pelo menu encaminha uma instalação pendente para `recovery_ui.py`;
a sessão direta também é bloqueada antes de construir `Window` ou abrir USB.
A recuperação usa outro processo e um bloqueio exclusivo. Ao abrir depois dela,
um interpretador novo evita misturar módulos da versão interrompida com os da
versão restaurada. O diálogo distingue progresso, falha, sucesso e desfazer uma
primeira instalação, em três idiomas. Cancelar o diálogo não muda a instalação.

`access_admin.py` é incorporado em scripts administrativos independentes. Ele
usa destinos fixos, verifica proprietários e links, serializa operações, registra
a conta autorizada e restaura os arquivos anteriores se uma operação falhar.
Remover recusa sessões USB ativas, arquivos personalizados ou outra conta. Essa
restauração foi testada com falhas simuladas de I/O/udev, não com perda de energia.
Os scripts exigem autorização polkit; não herdam a permissão diária do helper.
Cancelar a remoção administrativa mantém os arquivos do app.

access_guard.py observa descritores abertos por outros processos da mesma sessão
de usuário a cada dois segundos. Associa nós USB, hidraw e input à identidade do
controle, inclusive no dispositivo virtual. A detecção solicita Só carregar pelo
mesmo fluxo de confirmação da interface. Não intercepta tentativas recusadas ou
acessos que terminam entre consultas. Jogar pode suspender a detecção por controle
até a próxima escolha de Só carregar; perfis automáticos não criam essa exceção.

No proxy, preferências de cor, vibração e resistência filtram apenas os campos
correspondentes do relatório de saída. O broker guarda o último comando de
gatilho do jogo para restaurá-lo ao escolher Deixar o jogo controlar. Só carregar
desliga os efeitos; os presets não escrevem firmware nem calibração.

## Teste de entradas e laboratório

input_state.py decodifica somente relatórios USB de 64 bytes com ID 1. O helper
aceita uma assinatura `monitor: true`, com duração de três segundos, renovada
pela janela do teste. Envia no máximo 30 retratos por segundo e acumula pressões
breves entre eles para o checklist. `monitor: false` encerra a assinatura. Não
altera saída HID, configurações ou modo e não cria UHID durante a carga.

A versão 2 do monitor inclui os dois contatos do touchpad nos bytes USB 33–40,
conforme `dualsense_input_report` e `dualsense_touch_point` do
[driver hid-playstation do Linux](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c).
O bit de contato inativo descarta também suas coordenadas antigas. Valores
ativos fora de 0–1919 / 0–1079 são sinalizados, não aproximados para uma borda.
O payload transmite apenas contatos ativos válidos e a quantidade de pontos
inválidos; o clique segue independente. Não há rastros nem histórico de toques.
Os marcadores projetam os valores na forma do touchpad; as coordenadas brutas
ficam nos detalhes. O desenho é uma referência visual, não uma planta em escala.

A interface oferece atualizar o serviço quando encontra o monitor antigo,
antes de abrir a assinatura. Cancelar essa atualização mantém os modos salvos.

A interface associa as amostras ao processo, à conexão física e à identidade.
Descarta amostras tardias após fechar o painel ou trocar de conexão. Depois de
500 ms sem entrada, limpa os valores ativos, incluindo os pontos e coordenadas
de toque. A exportação de diagnóstico não recebe esses dados. Não há gravação
ou telemetria de uso.

input_view.py renderiza apenas a aba visível da bancada. Enquanto o blueprint
está escondido, mantém o último estado e acumula os botões observados; ao voltar,
desenha esse estado, ou limpa valores ativos se houve perda de leitura.
development.py usa os mesmos widgets com
modelos fictícios, sem importar a coordenação USB de window.py. Os cenários
cancelam transições pendentes ao reiniciar. diagnostics.py seleciona campos
compartilháveis; ele não serializa configurações ou payloads brutos do serviço.

`analog_test.py` mantém a medição guiada em memória, sem dependência de GTK ou
USB. O usuário inicia repouso, depois alcance e conclusão explicitamente.
`analog_view.py` apresenta o roteiro na segunda aba da bancada. A janela repassa
o instante monotônico de chegada da amostra, evitando contar o mesmo retrato ou
usar o tempo de renderização como duração observada. Repouso usa cinco segundos
de amostras contínuas, a partir da primeira nova leitura.

Intervalos de 500 ms, dados inválidos, relógio regressivo ou saída da aba
interrompem medições incompletas e limpam seus acumuladores. Reconectar não
reinicia a coleta. Resultados concluídos permanecem históricos até limpar,
repetir ou fechar. Média, mínimos e máximos são acumulados por eixo; cada
analógico guarda no máximo 120 pontos recentes para o traçado. O modelo recebe
os retratos do monitor, não todos os pacotes USB, e não escreve calibração,
preferências, arquivos nem dados de diagnóstico. O fluxo não adiciona comandos
ao helper nem altera a versão do protocolo.

## Prevenção de erros

- Separar escolha solicitada e confirmação recebida.
- Explicar a consequência antes de aplicar; validar novamente a identidade.
- Bloquear nova troca enquanto há outra pendente no mesmo controle.
- Exigir proxy confirmado e leitura recente para efeitos e testes de vibração.
- Renomear e consultar detalhes sem interromper a carga.
- Não animar leitura antiga nem retirar Só carregar por um perfil de jogo.
- Separar dados pessoais do checkout e usar gravação atômica de preferências.

## Referências

- [UHID](https://docs.kernel.org/hid/uhid.html)
- [hid-playstation](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c)
- [dualsensectl](https://github.com/nowrep/dualsensectl)
- [XDG](https://specifications.freedesktop.org/basedir/latest/)
- [GTK 3](https://docs.gtk.org/gtk3/)
- [Instância única e ciclo de vida do GApplication](https://docs.gtk.org/gio/class.Application.html)

## Propriedade da instalação

`deployment.py` mantém o código independente dos dados XDG. O perfil por usuário
conserva a instalação atual; o perfil nativo exige a localização fixa e um marcador
válido da mesma versão. `launch.py` nunca executa o instalador por usuário no
perfil nativo. `session.py` confere a pasta do proprietário existente pelo PID
D-Bus antes de ativá-lo. O assistente e os comandos de manutenção recusam tratar
arquivos do pacote como uma cópia removível por usuário. Um helper nativo ausente
não seleciona o helper manual nem o executável Python da pasta pessoal.

`native_grant.py` e `native_access.py` são incorporados no helper/administrador
nativos autocontidos. A autorização explícita gera uma regra apenas para a conta
solicitante, sem substituir arquivos do pacote. O helper confere UID e nome e
mantém o bloqueio compartilhado da conta enquanto controla o USB. Revogar exige
que essas sessões terminem; outras contas e arquivos personalizados são
preservados. A concessão existente é substituída atomicamente e há restauração
em falhas ordinárias. O helper manual e seus scripts gerados permanecem iguais.

`native_status.py` consulta pkcheck em segundo plano, sem solicitar senha. A
presença do helper não equivale à autorização da conta. Após configurar, a
interface confirma a decisão e preserva streams nativos já abertos. O assistente
permite revogar a concessão com o app encerrado. Autenticação real, migração e integração com o atualizador numa sessão gráfica
ainda precisam de validação antes de
distribuir releases nativas para uso real.
Os caminhos e as condições de validação estão em [instalação nativa](native-packaging.md).

`native_package.py` produz o layout nativo e os scripts autocontidos dos
gerenciadores. A cópia nativa dos pontos de entrada adquire uma sessão em
`native_lifecycle.py` antes de importar o restante do app. Os helpers incorporam
a mesma proteção. O estado de manutenção persiste entre scripts do gerenciador;
somente a conferência dos arquivos necessários marca a versão como pronta.
Uma sessão ativa impede adquirir o bloqueio exclusivo para manutenção. A versão
embutida no ponto de entrada também impede executar código carregado antes da
troca. A remoção revoga concessões canônicas antes de apagar o programa, preserva
arquivos locais desconhecidos e mantém os dados pessoais. O fluxo manual conserva
seu próprio bloqueio e seus scripts; não é convertido silenciosamente.

`startup_notice.py` contém somente biblioteca padrão e importação tardia de GTK.
Seu texto é embutido no lançador nativo e no caminho de falha dos pontos de
entrada, antes das importações do programa. Isso permite explicar inclusive a
ausência do módulo de bloqueio ou do próprio `launch.py`. Preferências são lidas
com tamanho limitado, sem bloquear em FIFO; erro de preferência usa o idioma da
sessão. Detalhes são texto simples. O botão de repetição usa `execv`, após destruir
a janela, para não reutilizar módulos antigos. Serviços/CLI/root não mostram
diálogos; recusa de manutenção retorna 78, excluído do reinício da unidade nativa.

## Leitura de movimento

A capacidade de monitoramento v3 acrescenta calibração de fábrica somente para
leitura e sensores aos snapshots já limitados a 30 Hz. O caminho direto usa
HIDIOCGFEATURE 0x05; a carga exclusiva usa GET_REPORT 0x0305 com 41 bytes. A leitura
é armazenada apenas pela sessão do monitor e não se repete a cada renovação.
O encaminhamento de relatórios do controle virtual e os modos de carga/efeitos
não usam os gráficos. A tela conserva até dez segundos localmente e limpa-os ao
sair, sem persistir entradas ou incluí-las no diagnóstico exportado.

## Acesso opcional da Steam Snap

`steam_access.py` consulta conexão, identidade e marcas atuais (Q:) do udev.
`steam_access_admin.py` reutiliza transação protegida/lock da configuração de
ponteiro e aceita apenas identidade normalizada e allow/system. O administrador
não aceita caminhos, comandos ou IDs de Snap fornecidos pelo chamador.
O único alvo é snap_steam_steam em hidraw USB de um DualSense padrão/Edge selecionado.

A instalação manual gera um programa temporário privado; o pacote nativo fornece
um executável fixo, ligado a uma ação polkit auth_admin e ao bloqueio de manutenção.
A interface separa rascunho, autorização, resultado salvo e marca observada. Uma
marca presente sem regra própria é apresentada como externa e preservada.
Nenhuma mudança de acesso é feita ao abrir o diálogo, nem a Steam é encerrada.
