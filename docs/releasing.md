# Pacote de distribuição

O pacote atual é uma versão **alpha em código-fonte**, com instalador por usuário.
Não é um AppImage, Flatpak, `.deb` ou `.rpm` e não inclui as bibliotecas do Linux.
A versão vem de `app_info.py`, compartilhada com a interface e o diagnóstico.
Versões do protocolo USB continuam independentes da versão pública do app.

A alpha.26 também inclui um gerador experimental de `.deb`/`.rpm`, com testes
de transações reais em imagens descartáveis. Esses candidatos de validação ainda
usam metadados fictícios e não são releases públicas. O fluxo e seus limites estão
em [instalação nativa](native-packaging.md); os comandos abaixo continuam se
referindo ao pacote de código-fonte.

## Construir e conferir

```sh
python3 release.py build
python3 release.py verify dist/dualsense-usb-0.6.0-alpha.26.tar.gz
```

São gerados o `.tar.gz` e seu arquivo `.sha256`. O conteúdo é escolhido por
`packaging/files.json`, que separa arquivos de execução e desenvolvimento. O
instalador usa a mesma lista de execução. Arquivos novos precisam ser incluídos
explicitamente; não se exporta a pasta de trabalho inteira nem o índice do Git.

O pacote contém código, testes, três idiomas, ilustrações, prévias públicas,
documentação, GPLv3 e o aviso MIT do blueprint. Não inclui preferências, nomes,
identificadores, fotos pessoais/oficiais, histórico, caches, logs ou o instalador
e removedor privilegiados gerados. Eles são reconstruídos localmente pelo instalador.

`RELEASE.json` registra versão, lista de arquivos, tamanhos e SHA256 de cada
arquivo. A verificação rejeita arquivos faltantes ou extras, hashes divergentes,
links, caminhos fora do pacote e versões inconsistentes. O SHA256 externo verifica
a integridade do arquivo baixado; ele não é uma assinatura digital do autor.

## Reproduzir

A ordem dos arquivos, permissões, usuário/grupo e cabeçalho gzip são normalizados.
O tempo padrão é zero; `SOURCE_DATE_EPOCH` permite fixar um timestamp de release.
Mesmos arquivos, timestamp e ferramentas de compressão geram os mesmos bytes,
independentemente da pasta, permissões ou datas de modificação do checkout.
Bibliotecas de compressão diferentes podem gerar bytes gzip diferentes; o
inventário interno permite comparar o conteúdo mesmo nesse caso.

```sh
SOURCE_DATE_EPOCH=0 python3 release.py build --output /tmp/dualsense-build-a
SOURCE_DATE_EPOCH=0 python3 release.py build --output /tmp/dualsense-build-b
cmp /tmp/dualsense-build-a/dualsense-usb-0.6.0-alpha.26.tar.gz /tmp/dualsense-build-b/dualsense-usb-0.6.0-alpha.26.tar.gz
```

Construir novamente substitui os artefatos locais dessa versão depois de validar
o candidato. Uma versão já publicada deve permanecer imutável; mudanças exigem
uma versão nova. O comando não cria tags, commits, releases nem envia arquivos.

## Testar o que será entregue

```sh
python3 tests/release_smoke.py
python3 tests/release_smoke.py --archive dist/dualsense-usb-0.6.0-alpha.26.tar.gz
dbus-run-session -- python3 tests/release_smoke.py --gui
```

Esse teste constrói duas cópias, compara seus bytes, confere o checksum, extrai
para uma pasta vazia e executa os testes unitários e a instalação limpa usando
somente a cópia extraída. O teste não autoriza hardware nem inicia sessões USB.
Ele também roda na sequência isolada de `tests/isolated_userspace.py` e no CI.
Com `--archive`, verifica exatamente o artefato indicado, incluindo reconstrução
a partir dele; `--sha256` aceita o checksum esperado obtido separadamente.
Na comparação entre distribuições, exige o TAR descomprimido inteiro idêntico,
incluindo conteúdo, ordem, cabeçalhos, permissões e datas. A saída informa à parte
se o gzip também é idêntico: zlib e zlib-ng podem produzir compressões diferentes.
O checksum do download continua sendo o do artefato original e não é substituído
pelo hash da reconstrução. Na construção local, dois builds com as mesmas
ferramentas continuam obrigados a produzir gzip byte a byte idêntico.
Com `--gui`, também testa a interface GTK, efeitos, entradas e três idiomas na
cópia extraída. Exige display; no CI e no rootfs isolado é usado Xvfb.

Para extrair com validação completa, a partir de um checkout confiável:

```sh
python3 release.py extract dist/dualsense-usb-0.6.0-alpha.26.tar.gz --destination /tmp/dualsense-extracted
```

A pasta de destino precisa não existir. O extrator não executa o conteúdo nem
sobrescreve uma instalação. O pacote também pode ser extraído pelo gerenciador
de arquivos depois de conferir seu checksum.

## Instalar o pacote baixado

Na pasta que contém o arquivo e seu checksum:

```sh
sha256sum -c dualsense-usb-0.6.0-alpha.26.tar.gz.sha256
tar -xzf dualsense-usb-0.6.0-alpha.26.tar.gz
cd dualsense-usb-0.6.0-alpha.26
python3 doctor.py --no-session
python3 setup.py
```

Consulte os pacotes necessários no README antes da instalação. O assistente
gráfico precisa de GTK/PyGObject já instalados; `python3 install.py` continua
disponível como alternativa pelo terminal. Para uma
atualização, encerre o app pela bandeja antes de executar o novo instalador.
Fechar a janela apenas a mantém na bandeja. Preferências ficam fora do código e
são preservadas. O instalador recusa uma sessão aberta. A remoção oferece
prévia, mantém dados pessoais e pode retirar o acesso USB com autorização
separada; veja [manutenção](maintenance.md). Acesso administrativo ao USB continua sendo uma etapa explícita
no app; construir e extrair um pacote não concede permissões.

## Antes da publicação

### Conferir o que o Git realmente vai enviar

O pacote usa os arquivos atuais da pasta; um commit usa o índice preparado do
Git. Portanto, um `.tar.gz` correto não prova que o próximo commit esteja completo.
Depois de revisar e preparar os arquivos do projeto para commit, execute:

```sh
python3 tests/git_inventory.py
```

A verificação compara o índice com `packaging/files.json`: arquivos faltantes,
conteúdo preparado diferente da pasta, arquivos extras, caminhos pessoais
conhecidos, links e conflitos. Não modifica o índice, cria commits nem envia nada.
O JSON mostra nomes de arquivos, sem imprimir seu conteúdo. Código de saída 0
indica correspondência; 1 indica diferenças; 2 indica falha ao verificar.
Arquivos locais fora do índice não serão enviados e não causam reprovação.
Um novo arquivo público precisa primeiro entrar no inventário revisado.

O CI repete essa conferência sobre o checkout publicado antes dos demais testes.
Esse teste não examina o histórico de commits, segredos dentro do conteúdo,
licenças, estado do repositório remoto ou funcionamento do app. Essas revisões
continuam separadas. Prepare somente os caminhos revisados do inventário.

### Conferências da versão

1. Revisar a lista de arquivos, licenças, imagens e limites anunciados.
2. Executar testes do código e do pacote extraído em ambiente limpo.
3. Validar autorização administrativa, hardware e desktops da matriz anunciada.
4. Conferir a versão no app, no diagnóstico, no arquivo e no inventário interno.
5. Publicar pacote e checksum no repositório escolhido e preservar os artefatos.

O primeiro pacote local não comprova suporte a toda distribuição ou jogo. A
publicação remota e os testes físicos pendentes continuam no plano de evolução.
