# Compatibilidade Linux

O Uplugo depende de partes do sistema que variam entre distribuições: kernel
(driver `hid-playstation` e UHID), polkit, udev, D-Bus e o ambiente gráfico.
O systemd de usuário supervisiona o app quando existe, mas não é obrigatório.

## Onde já foi testado

| Ambiente | Interface e instalação | Controle real |
| --- | --- | --- |
| Ubuntu 26.04, GNOME | Instalação por usuário e testes gráficos | DualSense padrão: carga, controle virtual, cores e vibração |
| Ubuntu 24.04 (container limpo e CI) | Suíte completa sem hardware | Não testado |
| Debian 13 (container limpo) | Suíte completa sem hardware | Não testado |
| Fedora 44 (container limpo) | Suíte completa sem hardware, incluindo escala 200% | Não testado |
| Ubuntu 22.04 | CI configurado | Não testado |
| Arch, Silverblue, Kinoite, KDE e outros | Não testado | Não testado |

Os testes sem hardware cobrem instalação, atualização, remoção, os três idiomas,
alto contraste e a interface inteira com dados simulados. Eles não substituem
um login gráfico real nem polkit e udev ativos.

No Fedora, instale `gobject-introspection` explicitamente: sem ele faltam tipos
que o GTK 3 usa, mesmo com PyGObject instalado.

`python3 doctor.py` confere as dependências sem mostrar identificadores dos
controles. Sem bandeja no desktop, a janela é minimizada e Preferências oferece
Encerrar. Sem UHID, o controle virtual não funciona, mas carga e acesso direto sim.

## Sessões com e sem systemd

Com ou sem systemd de usuário, o menu abre a mesma instância registrada no D-Bus,
e abrir várias vezes não cria cópias disputando o controle. Sem systemd, uma
falha do app não reinicia sozinha. Distribuições sem systemd (OpenRC, runit,
elogind) ainda não foram testadas.

## Rodar os testes em containers

```sh
docker build -f packaging/testing/Dockerfile.debian13 -t uplugo-debian-test packaging/testing
docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,exec,mode=1777 --tmpfs /run:rw,mode=1777 \
  --mount type=bind,src="$PWD",dst=/src,readonly uplugo-debian-test
```

Para Fedora, use `packaging/testing/Dockerfile.fedora44`. Os containers rodam
como usuário comum, sem rede e sem USB. Para um rootfs com bubblewrap, sem Docker:

```sh
python3 tests/isolated_userspace.py /caminho/para/rootfs --report resultado.json
```

Os dois caminhos chamam `tests/run_userspace.py`, o mesmo usado pelo CI.

## Touchpad e Steam

O driver do Linux expõe o touchpad do DualSense como um dispositivo separado, que
o desktop pode usar como mouse. Em **⋮ → Touchpad e cursor**, o app pode criar uma
regra só para aquele controle (`LIBINPUT_IGNORE_DEVICE`), e o cursor do Linux
para de se mover. A regra pede autorização e pode ser desfeita na mesma tela.

A Steam tem os próprios mapeamentos de touchpad para mouse, independentes dessa
regra. **Configurações do jogo** não desativa o Steam Input.

Na Steam instalada por Snap, o confinamento pode impedir o acesso completo ao
controle (hidraw), e o clique do touchpad não chega ao jogo. Em **Touchpad e
cursor → Conferir acesso da Steam Snap**, o app pode liberar só o controle
escolhido. A permissão vale para todas as contas do computador e continua após
a desinstalação. Para removê-la, use a mesma tela. Depois de conceder ou remover,
reabra a Steam.

Referências: [dispositivos ignorados no libinput](https://wayland.freedesktop.org/libinput/doc/latest/ignoring-devices.html),
[modos de entrada da Steam](https://partner.steamgames.com/doc/features/steam_controller/input_source_modes).

## Próximos passos de distribuição

1. Testar em máquinas reais Ubuntu, Debian e Fedora, com GNOME e KDE, Wayland e X11.
2. Estabilizar os pacotes `.deb` e `.rpm` experimentais (veja [pacotes nativos](native-packaging.md)).
3. Avaliar Flatpak para a interface, com o acesso ao hardware num serviço do
   sistema. O app atual usa pkexec, sysfs, libusb e UHID e não funciona como Flatpak.

Referências: [UHID no kernel](https://docs.kernel.org/hid/uhid.html),
[permissões Flatpak](https://docs.flatpak.org/en/latest/sandbox-permissions.html).
