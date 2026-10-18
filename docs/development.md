# Laboratório, testes e uso dos dados

## Desenvolvimento sem hardware

Execute `python3 development.py` ou abra **Preferências → Desenvolvimento e
diagnóstico → Abrir laboratório sem USB**. A faixa no topo identifica os dados
simulados. O laboratório usa os widgets reais, mas não inicia helpers, não abre
USB, não baixa fotos e não grava as preferências pessoais.

Cenários: dois controles, nenhum controle, desconexão, leitura antiga, falha de
conexão e acesso não configurado. Trocas de modo têm uma confirmação simulada;
a troca de cenário cancela a transição pendente. Cores/efeitos são rascunhos em
memória. O painel de botões recebe uma sequência automática fictícia.

Para regressões:

```sh
python3 -m unittest discover -v
python3 tests/gui_smoke.py
python3 tests/accessibility_smoke.py
python3 tests/display_smoke.py
python3 tests/startup_smoke.py
dbus-run-session -- xvfb-run -a -s "-screen 0 1280x1024x24" python3 tests/setup_smoke.py
dbus-run-session -- xvfb-run -a -s "-screen 0 1280x1024x24" python3 tests/readonly_smoke.py
dbus-run-session -- xvfb-run -a -s "-screen 0 1280x1024x24" python3 tests/deployment_smoke.py
dbus-run-session -- python3 tests/session_smoke.py
python3 tests/photos_smoke.py
python3 tests/effects_smoke.py
python3 tests/profiles_smoke.py
python3 tests/language_smoke.py
python3 tests/input_smoke.py
python3 tests/diagnostic_smoke.py
python3 tests/input_layout_smoke.py
python3 tests/analog_smoke.py
python3 tests/steam_access_smoke.py
python3 tests/motion_smoke.py
python3 tests/stress.py
python3 tests/clean_install.py
python3 tests/release_smoke.py
```

`tests/accessibility_smoke.py` usa eventos de teclado e a árvore ATK local para
testar contexto por controle, confirmação/cancelamento, foco, campos de efeitos
e seleção de cores. Não abre USB nem comprova integração com um leitor de tela.
Execute em Xvfb privado; `--output /tmp/dualsense-accessibility` salva imagens do
editor com dados simulados. `tests/effects_smoke.py` também exercita o diálogo
real em três idiomas, com gravação temporária isolada e transporte simulado.
Repita esses dois testes com `GDK_SCALE=2` para verificar a escala ampliada.

`tests/display_smoke.py` verifica a janela principal em diferentes larguras,
três idiomas, Adwaita/HighContrast, fontes de 10/16 pontos e DPI 96/144. Inclui
foco após redimensionar, rolagem até o segundo controle, preferências, estados
de configuração e ausência de comandos ao cancelar. Falhas em callbacks GTK e
recalcular o layout continuamente reprovam o teste. `--output` salva imagens
com dados simulados. O runner limpa `GTK_THEME` e `GDK_DPI_SCALE` herdados para
evitar que uma preferência do computador interfira nesse teste controlado.

O benchmark abaixo, dentro da imagem de testes isolada, mede 120 atualizações
fictícias por aba da bancada:

```sh
dbus-run-session -- xvfb-run -a -s "-screen 0 1280x1024x24" python3 tests/render_benchmark.py
```

Informa média, percentil 95
e maior tempo local de atualização; não há limite de tempo usado como teste de
aprovação. Os números dependem da máquina, carga e bibliotecas. Não são latência
USB nem latência de jogo. Só a aba visível é desenhada; a aba escondida continua
acumulando botões observados e recebe o estado mais recente quando reaparece.

O estresse usa semente fixa: 100 mil relatórios, 5 mil atualizações da tela e 240
mudanças de cenário. Ele verifica limite de frequência, tamanho dos dados,
preservação de widgets/foco e cancelamento de transições. Não é um teste de
latência USB, resistência física ou autonomia da bateria. Em CI, use Xvfb e
D-Bus de sessão privado, como no workflow fornecido.

`session_smoke.py` usa processos reais e dispositivos simulados. Verifica cinco
aberturas simultâneas, fechar para a bandeja, reativar sem reconstruir a janela,
notificação de prontidão usada pelo systemd, encerramento e reabertura. Também
rejeita inicialização sem D-Bus, antes de abrir hardware. Não execute esse teste
no barramento de sessão real; ele exige `dbus-run-session`.

`tests/isolated_userspace.py` reproduz a sequência completa em um rootfs já
preparado, sem USB nem dados do host; detalhes em [compatibilidade Linux](linux-support.md).

`tests/appearance_smoke.py` abre os diálogos reais de nome/modelo e fotos em
três idiomas. Verifica rascunhos, teclado, filtros, janelas de 480/640/830 pixels,
fonte grande, alto contraste, cancelamento, erro de gravação e nova tentativa.
Usa identidades e imagens sintéticas, preserva alterações concorrentes em outras
preferências e não envia comandos USB. Também verifica que uma importação
explícita pertence à biblioteca, enquanto Cancelar preserva nome/modelo.
Execute com `GDK_SCALE=2` no Xvfb para verificar 200%; o tamanho do monitor
limita as dimensões lógicas. Isso não substitui validação humana com Orca.

`tests/setup_smoke.py` testa o assistente de instalação em três idiomas, com
janela pequena, fonte ampliada e alto contraste. Exercita bloqueios, erro e nova
tentativa, progresso sem fechar no meio da operação e abertura solicitada. Em
pastas temporárias, instala, atualiza e remove uma cópia real, preservando dados
e arquivos modificados; a autorização administrativa cancelada é simulada.
`--output` salva prévias sintéticas. O teste não inicia o app nem toca em USB.

`tests/setup_lifecycle.py` verifica que um processo sintético iniciado pelo
lançador do assistente continua vivo após o processo pai encerrar. O modo direto
está incluído na suíte. A opção `--systemd`, executada separadamente em uma sessão
com gerenciador systemd de usuário, cria apenas serviço e escopo temporários de
teste, sem GTK ou hardware. Confere a separação dos grupos de processos e limpa
esses recursos; não inicia, encerra nem modifica o serviço do app instalado.

## Arquivos de distribuição

`tests/readonly_smoke.py` abre a janela real a partir de uma cópia do programa
sem permissão de escrita. Uma autorização privada simulada inspeciona o script
temporário e permite testar cancelamento, falha, resultado divergente e sucesso
verificado sem executar código privilegiado. Confere limpeza dos temporários,
integridade da árvore, preservação de dados, preparação responsiva e a distinção
entre repetir leituras de bateria e identificar o controle apenas uma vez.
Um PTY privado também verifica entrada/saída da autorização simulada pela CLI,
sem agente administrativo real nem senha.

`tests/native_access_smoke.py` exercita GTK e concessões em arquivos privados:
confirmação assíncrona, cancelamento, sucesso sem autorização recusado, repetição
sem reiniciar streams e revogação por conta em três idiomas. A decisão do polkit
é simulada. `tests/test_native_access.py` cobre duas contas, concorrência,
renomeação, caminhos/permissões inesperados, umask restritiva, rollback e SIGKILL.

Para executar o administrador e o helper nativos gerados nos caminhos reais,
use um rootfs de teste já preparado e rode **como usuário comum**:

```sh
python3 tests/native_admin_namespace.py /caminho/do/rootfs
```

Esse runner usa bubblewrap com contas e destinos administrativos privados,
sem rede, barramento de sistema ou USB do host. UID 0 existe apenas dentro do
namespace e `PKEXEC_UID` é sintético; não há autenticação polkit real. O teste
recusa executar como root no host e não modifica o rootfs. Ele é separado da
suíte comum, pois exige permissão para criar namespaces de usuário.
Os contratos e limites estão em [instalação nativa](native-packaging.md).

`native_package.py` gera `.deb`/`.rpm` experimentais usando `dpkg-deb`/`rpmbuild`.
`tests/test_native_lifecycle.py` verifica estado persistente, sessões concorrentes,
versão carregada, reparação, arquivos inesperados e concessões preservadas.
Para testar transações reais em uma cópia descartável da imagem preparada:

```sh
python3 tests/native_package_namespace.py /caminho/rootfs deb --output /tmp/dualsense-deb-test
python3 tests/native_package_namespace.py /caminho/rootfs-com-rpm-build rpm --output /tmp/dualsense-rpm-test
```

Execute como usuário comum. A imagem deve ter dependências e ferramentas já
configuradas; o teste não tem rede. Ele copia o rootfs, isola dispositivos, usa
contas fictícias e registra as correções de metadados herdados da extração OCI.
Os pacotes gerados usam `Local validation only <test@example.invalid>` e ficam
com o relatório em `--output`. Não use essa identidade em uma publicação.
Não há autorização real, login gráfico, controle físico ou migração de `$HOME`.

`tests/native_startup_smoke.py` exercita o aviso de abertura sem arquivos visuais
do app, em três idiomas, fontes grandes e escalas 100%/200%. Um subprocesso
substitui o programa interrompido enquanto o aviso está aberto e aciona o botão:
o novo interpretador precisa carregar o arquivo reparado. Ausência de display
também é verificada. `tests/test_startup_notice.py` cobre preferências danificadas,
FIFO, limite de leitura, ausência do módulo de bloqueio e preservação dos
argumentos do diagnóstico. As transações nativas removem temporariamente arquivos
do programa somente na cópia descartável e verificam a falha do lançador instalado.
O processo ativo mantém a sessão da implementação instalada; botões e rumble não
são simulados por esse teste de manutenção.

`packaging/files.json` é a lista revisada de arquivos do pacote e da instalação.
Ao criar um módulo ou recurso, adicione-o ao grupo correto: `runtime` para o que
o app instalado precisa e `development` para ferramentas e testes. Não adicione
dados pessoais nem fotos oficiais. O build recusa módulos Python novos sem
revisão da lista e não copia diretórios arbitrários para a instalação.

`app_info.py` define a versão pública usada pela interface, diagnóstico e pacote.
As versões do protocolo/helper não mudam junto automaticamente. Gere e valide
o pacote conforme [distribuição](releasing.md); teste a cópia extraída, além do
checkout de desenvolvimento. O teste não publica nada no GitHub.

## Traduções

As traduções ficam em `locales/en.json` e `locales/es.json`, com texto original
em português como chave. Marque textos da interface com `i18n._`; não traduza
nomes fornecidos pelo usuário, títulos de jogos nem valores de protocolo. Use
placeholders em mensagens dinâmicas. Os testes conferem cobertura das mensagens
marcadas, igualdade dos placeholders e troca de idioma sem comandos USB. Não
adicione dependências de traduções ao helper privilegiado.

## Dados já aproveitados

| Dados | Uso implementado | Limite |
| --- | --- | --- |
| Porcentagem e estado de bateria | Histórico de mudanças, atualização ao vivo, aviso de estagnação | Passos aproximados de 10%; não mede corrente ou saúde da célula |
| Botões e direcional | Estado pressionado e checklist da sessão | Uma pressão observada comprova resposta naquele momento, não vida útil |
| Analógicos | Valores por eixo de −100% a +100%; roteiro de repouso e alcance, média, mínimos/máximos e traçado recente | Até 30 retratos por segundo; sem diagnóstico automático de drift nem gravação de calibração |
| L2/R2 | Curso recebido de 0% a 100% | Posição do gatilho não mede força/resistência física |
| Touchpad | Até dois contatos no desenho e coordenadas nos detalhes; clique separado | Não mede pressão, não diagnostica defeitos; conferência física pendente |
| Contadores do broker | Pacotes, saídas e relatórios rejeitados no diagnóstico | Não são FPS do jogo nem uma medida ponta a ponta de latência |
| Conexão e identidade | Nome persistente e proteção contra atuar no controle errado | IDs não entram na exportação de diagnóstico |

O teste recebe entradas enquanto está aberto, com até 30 atualizações por segundo.
Pressões breves entre atualizações entram no checklist. Não existe registro de
jogadas, arquivo de botões ou envio de dados. Só o histórico de bateria já usado
pelo app continua persistido localmente.

## Medição guiada dos analógicos

A aba **Analógicos** separa cinco segundos de repouso de uma etapa de alcance
concluída pela pessoa. O contador começa na primeira amostra nova após a ação,
usa o relógio monotônico de chegada e não soma intervalos desconectados. A média
é acompanhada dos mínimos/máximos: um movimento simétrico também pode ter média
próxima de zero. Uma marca de direção significa apenas que o eixo atingiu 80%.

Os valores USB de 0 a 255 são exibidos como `(valor − 127,5) / 127,5 × 100`.
127 e 128 aparecem aproximadamente como −0,4% e +0,4%; isso é uma convenção de
exibição, não um limite aceitável de defeito. A amostragem observa os retratos
que chegam ao painel, até 30 Hz, e pode perder extremos entre eles. O gráfico
guarda os últimos 120 pontos por analógico; as estatísticas cobrem a etapa toda.
Não mede circularidade mecânica, força, latência ou saúde do potenciômetro.

O caminho do jogo pode aplicar uma zona morta, como permite a configuração de
[deadzones Linux no SDL](https://wiki.libsdl.org/SDL3/SDL_HINT_JOYSTICK_LINUX_DEADZONES).
O painel não altera esse caminho. O laboratório usa leituras centrais fictícias
durante o repouso e movimento simulado no alcance. O teste GTK exercita as etapas,
perda de leitura, reconexão, troca de aba e três idiomas; a comparação com uma
pessoa movimentando o controle físico continua pendente.

## Próximos experimentos, ainda não implementados

- **Touchpad:** conferir dois contatos no hardware; avaliar um percurso temporário
  para testar alcance. O painel atual não guarda rastros nem cria gestos de sistema.
- **Movimento:** visualização de giroscópio/acelerômetro usando a calibração
  fornecida pelo dispositivo. Não inferir posição absoluta a partir desses sensores.
- **Sessões de carga:** comparar aumentos observados com o mesmo cabo/porta e
  separar sessões após desconexão. Sem inventar mA, watts, tensão ou capacidade útil.
- **Latência:** medir intervalo de chegada dos relatórios no app; identificar
  claramente que isso não inclui renderização, jogo, tela ou ação física inicial.
- **Perfis:** regras explícitas por jogo; evitar adivinhar capacidades apenas
  pelo nome do executável ou pela foto escolhida.

Antes de cada experimento: definir qual dado existe, qual conclusão ele permite,
o cenário de teste reproduzível e o comportamento quando a leitura some.
O formato USB é conferido no [driver hid-playstation do Linux](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c).

## Limites de distribuição

Instalações isoladas verificam bibliotecas, arquivos e interface. Polkit, udev,
UHID, bandeja e permissões precisam de uma sessão real, e compatibilidade de jogos
precisa de testes com hardware. A matriz e o plano de empacotamento estão em
[compatibilidade Linux](linux-support.md). Não anunciar suporte universal a Linux.

## Recuperação das sessões USB

`tests/stream_recovery_smoke.py` passa pela atualização real da janela com USB e
processos simulados. Exercita reconexão na mesma porta sem uma enumeração vazia,
espera de encerramento sem bloquear GTK, serviço lento, pacotes e erros atrasados,
troca de modo, falha persistente sem repetir autorização, desaparecimento e
preservação do outro controle e das preferências. A abertura de processos reais
é substituída no teste; nenhuma regra ou interface USB da máquina é acessada.

```sh
dbus-run-session -- xvfb-run -a python3 tests/stream_recovery_smoke.py
```

O cenário integra as suítes de userspace e do pacote extraído. Ele não simula
o kernel durante suspensão nem comprova retomada física ou continuidade de um
jogo; esses casos precisam de sessão real e confirmação separada.

`tests/test_input_transport.py` exercita os loops do helper gerado. Além de mocks,
usa processos filhos e descritores reais de arquivos temporários para dados vazios,
um relatório seguido de fim de leitura e comando de parada simultâneo à entrada.
O stdin permanece aberto nesses testes para não esconder um loop de leitura com
um encerramento acidental do comando. Os descritores precisam estar fechados ao
terminar. Nenhum processo recebe privilégios reais ou abre HID; a verificação de
UID é simulada. Outros cenários cobrem `BlockingIOError`, prazo de vibração sem
novos relatórios e liberação dos efeitos. Os valores de saída são inspecionados,
sem acionar motores físicos. Referência: [API hidraw do kernel](https://docs.kernel.org/hid/hidraw.html).

O teste de recuperação também cobre ações pontuais esperando o processo antigo,
troca de conexão antes/durante o comando, durante a pausa de uma nova leitura e
antes de aplicar o resultado na tela. A identidade do cartão é conferida antes
de iniciar a ação.

## Histórico de bateria

Em **Bateria e conexão**, a observação atual mostra início/fim, porta e variação
em pontos percentuais. Abra **Comparar observações anteriores** para os últimos
24 períodos. Reconexões, mais de 15 segundos sem relatório e relógio regressivo
separam as observações; tempo sem dados não vira tempo de carga. Alterar o modo
sem interromper os relatórios mantém a observação, que pode incluir uso e carga.

O laboratório permite abrir essa mesma tela com dados simulados, sem criar
histórico pessoal. Para renderizar uma prévia em Xvfb:

```sh
xvfb-run -a -s '-screen 0 1280x1024x24' python3 preview.py --scenario battery --native --output /tmp/battery.png
```

`tests/test_charge_watch.py` cobre migração, limites, separação dos períodos,
retomada de carga e falha de escrita. `tests/battery_smoke.py` verifica o painel
nos três idiomas, atualização sem perder foco, leitura antiga e rolagem com 24
observações. Ambos usam somente dados sintéticos.

As anotações de cabo/condições têm rascunho, cancelamento, remoção por campo vazio
e nova tentativa após falha de escrita. Os testes verificam salvar após reconexão,
períodos com horários iguais, isolamento entre controles e descarte pelo limite.
O teste GTK cobre fontes 10/18 e ações acessíveis; `--preview /tmp/battery-notes`
grava imagens fictícias da edição. Não há alteração de modo ou abertura USB.

## Instalação interrompida

`tests/test_install_transaction.py` executa trocas reais de diretórios temporários
e encerra filhos com SIGKILL nos marcos de preparação, aplicação, commit,
restauração e limpeza. O hook `checkpoint()` é substituído somente no processo do
teste; não há variável de ambiente que provoque uma falha no instalador do usuário.
O caso com configuração em `/dev/shm` só roda quando esse diretório oferece um
filesystem gravável diferente do temporário de dados; caso contrário é marcado
como indisponível, sem simular suporte. `tests/clean_install.py` também interrompe
o instalador completo e executa `--recover` a partir da cópia instalada.

`tests/recovery_smoke.py` usa resultados fictícios para validar o diálogo em três
idiomas sem manutenção real. Para uma imagem da interface:

```sh
xvfb-run -a -s '-screen 0 1280x1024x24' python3 preview.py --scenario recovery --native --output /tmp/recovery.png
```

Também há `recovery-failed` e `recovery-complete`. Esses testes não substituem
queda de energia de VM/hardware. Atualizações são sempre testadas em diretórios
XDG temporários; nunca interrompa o instalador de uma sessão pessoal para QA.

### Perfil nativo em desenvolvimento

O teste `deployment_smoke.py` cria uma cópia somente leitura e redireciona apenas
as constantes de pasta de programa e de sysfs para locais privados. Abre a janela
real em outro processo, valida o proprietário pelo D-Bus, confere o assistente
em três idiomas e preserva arquivos pessoais/conflitos. Não autoriza acesso USB.
`--preview DIRETÓRIO` salva a prévia sintética em cada idioma.

A opção `--installed` é para um namespace descartável: monte o runtime completo
com `system-package.json` em `/usr/share/dualsense-usb`, somente leitura, mantenha
`/sys/bus/usb/devices` vazio e use HOME/XDG/D-Bus/Xvfb privados. Assim os caminhos
nativos reais são exercitados sem substituir constantes. Não é um teste do
gerenciador de pacotes, de polkit/udev/SELinux ou de hardware.

## Sensores de movimento · alpha.20

`motion_state.py` lê uma vez por sessão de monitoramento o relatório de fábrica
0x05 e converte os dados USB em °/s e g, seguindo a escala do driver Linux
hid-playstation. A leitura usa apenas GET_REPORT; não grava calibração nem
altera os pacotes encaminhados aos jogos. Calibração ausente ou inválida mantém
as unidades indisponíveis. O helper incorpora esse decodificador e anuncia
INPUT_MONITOR_VERSION=3; sua atualização requer a autorização USB habitual.

`motion_trace.py` limita o histórico a dez segundos/301 amostras, rejeita dados
inválidos e limpa períodos interrompidos, reinício do relógio ou sensor parado.
A interface só desenha enquanto a aba está visível e oferece os três idiomas.
`tests/test_motion.py` cobre escala, denominadores inválidos, limite do histórico,
wrap do relógio, pausa/retomada e ausência de dados. `motion_smoke.py` exercita
GTK, fontes 10/18, escala 100%/200%, alto contraste e saída da aba. O laboratório
produz movimento explicitamente fictício; jamais substitui falhas de USB por dados
simulados. O transporte mantém carga exclusiva sem criar controle virtual.

## Steam Snap

`tests/test_steam_access.py` cobre seleção por identidade, USB versus Bluetooth,
regras/arquivos inesperados, ausência de Snap, remoção independente, lock,
rollback, troca do alias hidraw, pedido privado e resposta divergente.
`steam_access_smoke.py` usa GTK nos três idiomas e um backend fictício, sem abrir
Steam nem USB. Confira também **Conferir acesso da Steam Snap** no diálogo real
de touchpad. O estado é configuração observada, não confirmação de entrada no jogo.

Para executar os programas administrativos gerados em namespace descartável:

```sh
python3 tests/native_admin_namespace.py /caminho/rootfs --steam-access
```

Esse teste substitui Snap e udev por fixtures privadas e executa instalação e
remoção da regra, falha/rollback, permissão externa e dois atores administrativos.
Não execute a fixture diretamente no host. A seleção real do udev é uma validação
separada; não substitui ensaio de autorização, cgroups e Steam num login real.
