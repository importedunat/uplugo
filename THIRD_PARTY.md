# Licenças e créditos

O código deste projeto é distribuído sob **GPL-3.0-only**; veja LICENSE.
Copyright (C) 2026 Uplugo contributors.

## Imagens e biblioteca pessoal

O ícone e a ilustração de catálogo foram criados para este projeto e seguem GPL-3.0-only.
Não são usados logotipos oficiais, fontes proprietárias ou recursos da Apple.
`assets/models.json` contém nomes de modelos e cores de referência; não contém
fotos oficiais nem implica licença sobre as marcas e desenhos dos produtos.

As fotos adicionadas pelo usuário ficam em `XDG_DATA_HOME/dualsense-usb/appearance-library`,
fora do código e dos arquivos exportados. Conservam seus direitos originais e não
recebem GPL automaticamente. O app pode baixar fotos em segundo plano, mas só
se a pessoa ativar essa opção em Preferências → Fotos dos controles (vem desligada). Os arquivos
vêm dos endereços fixos de `assets/photo-sources.json`, que registra a origem de cada
foto. Não há varredura de páginas, servidor intermediário ou envio de dados USB.
As fotografias e renders oficiais pertencem à Sony Interactive Entertainment e
respectivos titulares; seus arquivos não acompanham o repositório nem o pacote.

Os [termos do site PlayStation](https://www.playstation.com/en-us/legal/website-terms-of-use/)
distinguem uso pessoal não comercial de redistribuição e publicação. Não foi
obtida autorização para redistribuir suas imagens neste projeto. Antes de incluir
fotos num release, documente uma licença compatível ou autorização do titular.
Baixar separadamente não concede licença de redistribuição, não torna as imagens
GPL e não representa autorização da Sony ao projeto. A disponibilidade dos endereços
externos pode mudar. Uso e publicação das imagens estão sujeitos aos direitos e
termos dos titulares, independentemente da licença do código.

A prévia `docs/preview.png` e a animação `docs/demo.gif` são produzidas com dados
fictícios e ilustrações próprias. O banner `docs/banner.svg` usa a geometria do
blueprint descrita abaixo (MIT, the_al), com texto convertido em contornos da fonte
[Inter](https://github.com/rsms/inter) (SIL Open Font License 1.1).

Uplugo é um projeto independente, sem vínculo com a Sony Interactive Entertainment.
DualSense e PlayStation são marcas da Sony Interactive Entertainment; os nomes
aparecem apenas para indicar compatibilidade.
`preview.py --local-images` usa fotos pessoais e deve gerar arquivos fora do repositório;
o resultado não deve ser publicado sem os direitos correspondentes.

## Protocolo e dependências

### Geometria do blueprint

`assets/dualsense-blueprint.svg` vem de
[dualshock-tools/dualshock-tools.github.io](https://github.com/dualshock-tools/dualshock-tools.github.io/blob/33a9c2411cc96d77fab84e481a67052dc5c73ce7/assets/dualsense-controller.svg),
revisão `33a9c2411cc96d77fab84e481a67052dc5c73ce7`.
Copyright (c) 2024 the_al. A [licença MIT da mesma revisão](https://github.com/dualshock-tools/dualshock-tools.github.io/blob/33a9c2411cc96d77fab84e481a67052dc5c73ce7/LICENSE.txt) está integralmente em
`assets/dualsense-blueprint.LICENSE.txt` e acompanha a instalação.
A geometria original é preservada no arquivo; o app extrai suas formas e aplica
cores, símbolos, legendas e movimento no painel de teste. Essa base MIT conserva
seu aviso de copyright; o código de integração segue GPL-3.0-only.
O blueprint é incluído no pacote e funciona sem baixar imagens ou acessar a rede.

### Protocolo USB

A descrição dos relatórios e o empacotamento de zonas dos gatilhos usam como
referência o [dualsensectl](https://github.com/nowrep/dualsensectl/blob/main/main.c),
GPL-2.0-or-later, copyright Sony Interactive Entertainment (2020) e colaboradores
do dualsensectl. A opção de versão posterior permite a distribuição sob GPLv3.
A interface UHID segue o ABI público do kernel Linux. O descritor HID é lido do
próprio controle, sem incorporar um descritor de terceiros.

Os offsets dos sensores, relatório de calibração 0x05 e conversão de unidades
usam como referência o driver Linux
[hid-playstation.c](https://kernel.googlesource.com/pub/scm/linux/kernel/git/stable/linux-stable/+/master/drivers/hid/hid-playstation.c),
GPL-2.0-or-later, copyright Sony Interactive Entertainment e colaboradores.
A leitura não modifica a calibração do controle. O código de integração deste
projeto é distribuído sob GPL-3.0-only, conforme a opção de versão posterior.

Python, GTK/PyGObject, libusb, AppIndicator, systemd e polkit são dependências do
sistema e conservam suas licenças; seus binários não são incluídos neste repositório.

DualSense, PlayStation e Steam são marcas dos respectivos titulares. Projeto
independente, sem afiliação à Sony, Valve ou Apple.
