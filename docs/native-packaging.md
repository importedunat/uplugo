# Instalação nativa: implementação em andamento

O resultado desejado é instalar, atualizar e remover o aplicativo com o
gerenciador da distribuição, que também resolve as dependências. Um `.deb` ou
`.rpm` não deve ser apenas um atalho para criar uma segunda instalação escondida
na conta. A alpha.16 gera `.deb` e `.rpm` experimentais e já teve transações reais
testadas em imagens descartáveis. Os artefatos de teste usam identificação de
manutenção fictícia e não são releases públicas. O pacote de código-fonte e seu
instalador por usuário continuam sendo a forma atual de distribuição.

## Fundação concluída

O fluxo **Configurar acesso** agora funciona com os arquivos do programa somente
para leitura. `build_helper.py` oferece geração em memória; `access_request.py`
prepara o script administrativo em uma pasta temporária privada, mantém essa
pasta até o processo terminar e a remove em sucesso, cancelamento ou erro.
A interface prepara e executa a solicitação fora do loop GTK. `install.py
--access` e a remoção administrativa usam o mesmo mecanismo.

O helper e os scripts administrativos **manuais** gerados continuam idênticos aos
da alpha.12. Os destinos administrativos desse fluxo são os da instalação manual,
incluindo `/usr/local/libexec/dualsense-usb-helper`. Esta mudança não transforma
esses arquivos em arquivos pertencentes a um gerenciador de pacotes.

## Perfil do sistema implementado na alpha.14

`deployment.py` distingue o programa por usuário do programa em
`/usr/share/dualsense-usb`. O gerador de pacotes cria nessa pasta
`system-package.json`, com `format: 1`, `manager: "deb"` ou `"rpm"` e a versão
exata do código. Esse marcador não concede privilégios e não entra no pacote de
código-fonte ou na instalação por usuário. Marcador inválido, deslocado, apontado
por link ou de outra versão impede a seleção silenciosa do instalador manual.

O lançador abre os arquivos do pacote. Com systemd, espera a unidade
`/usr/lib/systemd/user/dualsense-usb-system.service`; verifica a origem da unidade
e recusa substituições locais ou drop-ins antes de iniciar. Sem systemd, abre o
mesmo `window.py` do sistema. Ao reutilizar uma janela existente, verifica o PID
pelo D-Bus e a pasta do programa; uma versão antiga não é ativada silenciosamente.
O assistente informa **Instalado pelo sistema**, oferece abrir/verificar e orienta
atualização/remoção pelo gerenciador, sem oferecer uma cópia por usuário.

A instalação do sistema seleciona exclusivamente
`/usr/libexec/dualsense-usb-helper`. A configuração nativa chama o contrato fixo
`pkexec /usr/libexec/dualsense-usb-access install|remove`. O administrador de
concessões foi implementado na alpha.15 e integrado ao gerador na alpha.16. Se estiver ausente,
o app informa pacote incompleto, sem gerar o instalador manual ou substituir
arquivos pertencentes ao pacote. O fluxo manual existente não mudou de destino.

Atalhos, unidades, registro, árvore de programa e recuperação pendente da conta
são detectados antes de abrir a versão do sistema. O assistente mostra os caminhos
e pede resolver a instalação anterior, sem remover nada automaticamente.
Fotos, nomes e histórico sozinhos não bloqueiam abertura. O instalador manual
recusa criar uma cópia sobre uma instalação do sistema; recuperar e remover
explicitamente uma instalação antiga continua possível pela sua própria cópia
ou pelo pacote de código-fonte. A migração guiada ainda não está concluída.

## Acesso por conta implementado na alpha.15

`build_helper.native_payloads()` gera em memória quatro arquivos administrativos.
O gerenciador é dono deles; configurar acesso não os reescreve:

| Caminho | Função | Modo |
| --- | --- | --- |
| `/usr/libexec/dualsense-usb-helper` | Operações USB com verificação da concessão da conta | `0755` |
| `/usr/libexec/dualsense-usb-access` | Conceder ou revogar o acesso da conta solicitante | `0755` |
| `/usr/share/polkit-1/actions/org.local.dualsense.usb.native.policy` | Duas ações e mensagens em três idiomas | `0644` |
| `/usr/lib/udev/rules.d/70-dualsense-usb-native.rules` | Regras de dispositivos já usadas no suporte manual | `0644` |

Os executáveis são autocontidos, usam `/usr/bin/python3 -I` e não importam código
da pasta pessoal. O administrador aceita somente `install` ou `remove`. Identifica
a conta por `PKEXEC_UID` fornecido pelo pkexec e pela base de usuários do sistema;
não aceita nome, UID ou pasta escolhidos nos argumentos. Antes de conceder,
confere conteúdo, proprietário, permissões e caminhos dos outros três arquivos.
Revogar continua possível se um arquivo do pacote estiver faltando.

A ação `native.manage` exige autenticação administrativa na sessão local ativa.
A ação `native.control` é recusada por padrão. Depois da autorização explícita,
o administrador grava somente a concessão daquela conta em
`/etc/polkit-1/rules.d/49-dualsense-usb-native-<UID>.rules`, com modo `0644`.
A regra libera apenas o controle USB, para o nome daquela conta em sessão local
ativa. O helper também confere UID e nome na concessão antes de abrir o USB:
renomear uma conta exige configurá-la novamente. O pacote não inclui uma regra
que autorize todos os usuários. Essa configuração local segue a distinção entre
ações fornecidas pelo programa e regras escolhidas pelo administrador no
[manual do polkit](https://polkit.pages.freedesktop.org/polkit/polkit.8.html).

Cada conta tem seu próprio bloqueio em
`/var/lib/dualsense-usb/native-access/<UID>.lock`, protegido com `0600`.
Sessões USB mantêm um bloqueio compartilhado; uma alteração exige bloqueio
exclusivo. Assim, não se revoga uma concessão enquanto os helpers daquela conta
estão ativos. Outra conta continua podendo configurar seu próprio acesso.
Configurar novamente uma concessão já válida preserva as sessões, sem reiniciar
controles. O bloqueio permanece após revogar para evitar trocar o arquivo usado
por processos concorrentes.

A gravação usa arquivo temporário, sincronização e substituição atômica. Erros
ordinários tentam restaurar a concessão anterior. Arquivos personalizados ou de
outra conta, links, permissões inseguras e caminhos inesperados são recusados e
preservados. Um encerramento forçado pode deixar um temporário sem extensão
`.rules`; ele não autoriza acesso e não é varrido junto com arquivos desconhecidos.
Uma nova tentativa usa a concessão completa anterior ou a nova.

`native_status.py` consulta `/usr/bin/pkcheck` sem interação, com PID, início do
processo e UID, fora do loop GTK. Ter um helper instalado não basta para mostrar
acesso autorizado. Depois de configurar, a interface aguarda brevemente a
releitura das regras e confirma o resultado. O assistente do perfil nativo oferece
**Revogar acesso USB desta conta**, explica o que fica preservado e pede encerrar
o app antes da revogação. Esse fluxo está traduzido para inglês e espanhol.
O pacote nativo precisará fornecer `pkcheck`, além de pkexec e do serviço polkit.

O helper nativo tem uma verificação de concessão adicional; seu núcleo de
protocolo USB permanece o mesmo. A instalação manual continua usando seu próprio
helper e administrador, com a limitação existente de uma conta proprietária.

## Pacotes experimentais e ciclo de vida · alpha.18

`native_package.py` constrói os dois formatos sem instalar nada. Copia somente o
inventário de execução, acrescenta o marcador, os quatro arquivos administrativos,
`/usr/bin/dualsense-usb`, entrada de menu, ícone, unidade de usuário e configuração
para carregar UHID. A conta mantém dados nos diretórios XDG; nenhuma cópia do
programa é criada em `$HOME`. O menu também oferece **Gerenciar instalação**.
O comando aceita `--setup`, `--doctor` e `--version`.

O lançador é um programa Python autocontido. Se a instalação estiver em manutenção
ou incompleta, mostra uma janela em português, inglês ou espanhol, com orientação,
detalhes técnicos e **Tentar abrir novamente**. O aviso e suas traduções estão
embutidos no lançador e nos pontos de entrada; não dependem dos arquivos visuais
que podem estar sendo substituídos. O idioma salvo tem prioridade sobre o idioma
da sessão. Repetir a abertura executa um interpretador novo, que lê a versão
reparada do disco; o aviso não repara arquivos nem solicita autorização.

Sem GTK ou sessão gráfica disponível, o motivo continua na saída de erro. Comandos
de diagnóstico e processos de serviço não abrem janelas. A recusa de manutenção
retorna código 78; a unidade nativa não reinicia automaticamente nessa condição.
Falhas posteriores ao bloqueio, como erro ao iniciar o serviço, também são
mostradas pelo lançador. Nesse caso, feche o aviso antes de reparar a instalação.

O `.deb` declara dependências e pré-dependência de Python 3.10+. O RPM é `noarch`
e declara dependências dos scripts de manutenção. Os dois exigem polkit/pkexec,
GTK/PyGObject, libusb, udev, kmod e certificados. A bandeja é recomendada, mantendo
o fallback da interface. Ao escolher o modo pelo app, o helper nativo autorizado
tenta carregar apenas o módulo `uhid` se o dispositivo estiver ausente; isso
ainda precisa de teste em uma sessão física limpa. A configuração do pacote
não reivindica controles nem reinicia jogos.

`native_lifecycle.py` mantém um bloqueio compartilhado durante a execução dos
pontos de entrada e dos helpers nativos. A manutenção exige acesso exclusivo.
O estado persistente em `/var/lib/dualsense-usb/package-state.json` impede novas
aberturas entre scripts separados do gerenciador, inclusive após interrupção.
Os caminhos, modos e conteúdos dos arquivos necessários são conferidos antes de
marcar a instalação como pronta. Um executável antigo já carregado também precisa
corresponder à versão pronta. O bloqueio `package.lock` é de root e legível para
as contas abrirem sessões; somente o administrador pode escrever o estado.

Uma sessão ativa faz atualização/remoção falhar com instrução para encerrar o app
pela bandeja, sem matar processos. Uma configuração incompleta continua bloqueada
até reparar pelo gerenciador. A remoção revoga concessões canônicas antes de apagar
o programa, preserva regras personalizadas e arquivos desconhecidos, e não visita
pastas pessoais. No Debian, a limpeza final funciona mesmo se Python já tiver
sido removido; os registros administrativos são mantidos nesse caso. Atualizar
preserva as concessões; remover e reinstalar exige configurá-las novamente.

O Fedora pode omitir referências duplicadas em `/usr/share/doc` com `nodocs`.
Licenças e recursos necessários continuam na árvore de execução e são conferidos.
A deduplicação por hardlinks do RPM é desativada para preservar a verificação de
arquivos administrativos. Nenhuma regra que autorize contas acompanha o pacote.

Para construir localmente, com `dpkg-deb` ou `rpmbuild` já instalado:

```sh
python3 native_package.py deb --maintainer 'Seu nome <seu-email@dominio>'
python3 native_package.py rpm --maintainer 'Seu nome <seu-email@dominio>'
```

São gerados o pacote e seu SHA256 em `dist/native/`. `--revision` altera a revisão
do pacote sem alterar a versão do app. A identidade de manutenção deve ser real
antes de publicar. Reprodutibilidade byte a byte dos pacotes nativos ainda não é
prometida; o pacote de código-fonte mantém sua verificação reproduzível.

## Próximas etapas necessárias

1. **Validar a experiência de manutenção numa sessão real.** Layout, arquivos
   administrativos, dependências, menu, unidade e ciclo de vida já têm geração
   e transações reais testadas. O aviso de abertura agora é gráfico, traduzido
   e independente dos arquivos visuais; falta conferir a interação com o
   atualizador da distribuição, o serviço de usuário e os diferentes desktops.
2. **Integrar a autorização nativa.** O administrador, política, verificação do
   helper e concessões por conta estão implementados e testados em isolamento.
   Falta validar pkexec/polkit em uma sessão local
   real, incluindo duas contas, recarga de regras e recusa de sessão inativa/remota.
   A limpeza opcional do suporte manual já usa o removedor com verificação de
   propriedade; a autorização gráfica real ainda precisa ser validada.
3. **Validar a migração em uma sessão real.** O assistente nativo já arquiva a
   instalação por usuário, inclusive sem registro, com prévia e retomada após
   interrupção. Preserva dados atuais e importa dados que ficaram na pasta antiga
   somente quando não há destino. Testes cobrem arquivos modificados, unidades,
   personalizações, links de ativação, discos separados e SIGKILL. O gerenciador
   do sistema não modifica pastas pessoais: a migração ocorre por ação da conta.
   Ainda falta validar a descoberta pelo menu e o serviço numa sessão de desktop
   real. Veja [o roteiro de migração](maintenance.md).
4. **Ampliar os testes de atualização e remoção.** A recusa com processo ativo,
   bloqueio persistente, reparação, preservação de arquivos e revogação foram
   testados. Falta exercitar interrupção do gerenciador/queda de energia em VM,
   uma janela GTK instalada em sessão de usuário real e atualização de dependências
   junto com o app. Os testes não encerram processos da instalação em uso.
5. **Preparar a publicação.** Definir autoria, contato de manutenção e URL pública,
   revisar convenções/lint de cada distribuição, testar download/instalação com
   outra pessoa e completar autorização gráfica, udev/SELinux e USB. Não anunciar
   suporte universal a partir das transações isoladas.

## Evidência e limites

Na alpha.19, o pacote também instala o administrador de touchpad e uma política
polkit própria em `org.local.dualsense.usb.touchpad.policy`. Ela exige autorização
administrativa e não usa a concessão de acesso USB sem senha. A configuração é
local ao computador e persiste após a remoção do pacote até restauração explícita.
O programa protegido pelo bloqueio do pacote só altera a regra canônica do controle
selecionado. O helper USB não ganhou comandos administrativos novos.

`tests/native_admin_namespace.py ROOTFS --touchpad` executa os programas gerados
manual/nativo de verdade, com contas sintéticas, sysfs de fixture e um substituto
privado de udevadm. Verifica salvar/restaurar, escopo de um controle, falha após
remove, adição de recuperação, argumentos inválidos e integridade dos arquivos
do pacote. A simulação do udev não comprova efeito no compositor, Steam ou jogo.

Na alpha.18, `tests/test_migration.py` exercita arquivos reais em pastas privadas,
recusa de prévia alterada, bloqueios, links/objetos inesperados, importação sem
sobrescrita e retomada após SIGKILL. `tests/migration_smoke.py` usa GTK real nos
três idiomas, incluindo uma falha após mover arquivos, retomada e preservação de
nomes, modos e fotos. O teste mantém a janela responsiva e a instalação nativa
intacta. A limpeza administrativa antiga é simulada no teste gráfico; os testes
unitários verificam o pedido temporário real sem executá-lo como administrador.
Isso não comprova queda de energia, autorização polkit ou migração física.

`tests/readonly_smoke.py` copia o programa para arquivos `0444` e diretórios
`0555`, abre a janela real com essa cópia e usa um subprocesso privado no lugar
de `pkexec`. Ele lê e valida o script temporário sem executá-lo como administrador.
Confere cancelamento, falha, sucesso sem resultado válido, nova tentativa,
verificação do helper, limpeza dos temporários e preservação das preferências.
Uma preparação deliberadamente pausada verifica que GTK continua respondendo.
Uma autorização simulada em PTY privado verifica que os comandos de manutenção
preservam entrada e saída interativas no terminal; ela não usa uma senha real.

Esse teste passou em Ubuntu 24.04, Debian 13 e Fedora 44 isolados. Os testes de fontes
somente leitura são uma condição necessária; não comprovam um pacote nativo,
permissões de uma conta limpa ou funcionamento universal em Linux.

`tests/deployment_smoke.py` exercita o assistente em três idiomas e abre o
`window.py` real por subprocesso, em um barramento D-Bus privado. Confere a
pasta do processo, reutilização da instância, recusa de outra instalação,
preservação dos conflitos e dos dados, ausência de cópia/atalho/serviço por usuário
e integridade da árvore somente leitura. Por padrão, apenas as constantes da
pasta do sistema e do USB são redirecionadas numa cópia privada. A opção
`--installed` testa uma árvore montada em `/usr/share/dualsense-usb`, sem essas
substituições; exige namespace descartável com sysfs USB vazio. Não usar essa
opção contra a instalação em uso. Os testes de comandos systemd são simulados;
não comprovam integração com um gerenciador de usuário real.

Na alpha.15, `tests/native_access_smoke.py` usa GTK real, concessões em pastas
privadas e autorização simulada. Confere cancelamento, resposta de sucesso sem
acesso válido, confirmação responsiva, ausência de reinício dos helpers e
revogação isolada nos três idiomas. `tests/test_native_access.py` cobre duas
contas, concorrência, troca de nome, arquivos inesperados, umask restritiva,
falhas de sincronização/restauração e SIGKILL antes/depois da substituição.

`tests/native_admin_namespace.py ROOTFS` executa os programas gerados nos seus
caminhos fixos em um namespace descartável. O processo é UID 0 **apenas dentro
do namespace**, mapeado para o usuário comum no host. Usa base de contas privada,
`PKEXEC_UID` sintético, sistema de arquivos privado nos destinos administrativos,
sysfs vazio e nenhum barramento de sistema ou dispositivo do host. Os programas
realmente criam/revogam concessões e recusam acesso sem concessão; não passam por
autenticação real. Os ancestrais dos destinos são criados com permissões privadas
adequadas, sem alterar metadados das imagens extraídas sem privilégios.

Esses testes passaram em Ubuntu 24.04, Debian 13 e Fedora 44. Não comprovam uma
decisão real do polkit, sessão gráfica limpa, SELinux, USB ou transação `.deb`/`.rpm`.

Na alpha.16, `tests/native_package_namespace.py` copia a imagem preparada para
uma árvore descartável e executa APT/dpkg ou DNF/RPM de verdade. Usa rede, sysfs e
dispositivos isolados; somente o UID 0 do namespace é mapeado para o usuário comum
do host. O APT usa esse UID na fixture porque `_apt` não está mapeado. Ancestrais
com permissões de escrita herdadas da extração OCI são corrigidos somente na cópia
descartável, com registro dos caminhos. As dependências da imagem são preparadas
antes, pelo seu próprio gerenciador.

Foram verificados colisão com arquivo não gerenciado, menu/unidade, diagnóstico,
instalação, atualização, recusa com processo real mantendo a sessão do pacote,
reinstalação após estado interrompido, duas concessões e remoção preservando dados,
atalho antigo, regra personalizada e arquivo desconhecido. Debian/Ubuntu também
testam erro após desempacotar, reparação na configuração e purge sem Python.
O processo ativo usa a implementação instalada do bloqueio; não abre GTK nem USB.
Isso não substitui teste de uma sessão gráfica de usuário nem da migração nessa sessão.

Referências para o empacotamento: [arquivos e scripts na política Debian](https://www.debian.org/doc/debian-policy/ch-files.html)
e [hierarquia de diretórios Debian](https://www.debian.org/doc/debian-policy/ch-opersys.html#file-system-hierarchy).
Os caminhos finais e os scripts do gerenciador devem ser validados também nas
diretrizes Fedora antes da geração dos pacotes.
