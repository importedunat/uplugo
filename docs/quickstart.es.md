# Uplugo: primeros pasos

[English](../README.md) · [Português](../README.pt-BR.md) · Español

Una app independiente para usar y cargar mandos DualSense por USB en Linux.
Puedes elegir si los efectos los controla el juego o la app. Es una versión alpha
experimental: las pruebas físicas actuales cubren DualSense estándar en el equipo
Ubuntu de desarrollo. Otras distribuciones y el Edge necesitan más pruebas.

La ventana principal reorganiza las fotos y acciones para pantallas más estrechas. Selecciona un mando arriba para abrir sus controles. Ayuda destaca cada función en su lugar. El texto respeta la fuente y la escala de texto de GTK; los temas GTK de alto contraste conservan sus colores de interfaz.

## Instalar

Usa un **cable USB de datos**. Un cable que solo carga no transmite los botones.
Las pruebas aisladas de instalación e interfaz pasan en Ubuntu 24.04, Debian 13
y Fedora 44. Las pruebas físicas siguen limitadas al equipo Ubuntu de desarrollo;
consulta la [matriz de compatibilidad](linux-support.md).

Instala las dependencias de tu distribución:

**Ubuntu o Debian**

```sh
sudo apt install python3 python3-gi gir1.2-gtk-3.0 librsvg2-common libusb-1.0-0 libayatana-appindicator3-1 pkexec udev ca-certificates
```

**Fedora 44 tradicional con DNF (experimental)**

```sh
sudo dnf install python3 python3-gobject gobject-introspection gtk3 librsvg2 libusb1 libayatana-appindicator-gtk3 polkit systemd-udev ca-certificates
```

`gobject-introspection` aporta tipos necesarios para GTK 3 incluso con PyGObject
instalado. Falta validar la autorización del escritorio Fedora, SELinux y USB real;
Silverblue y Kinoite no se han probado.

Después, desde la carpeta del código fuente extraído, ejecuta:

```sh
python3 doctor.py --no-session
python3 setup.py
```

El asistente ofrece **Instalar o actualizar** y **Desinstalar de mi cuenta**, comprueba
los requisitos y conserva nombres, preferencias, fotos e historial. Elige el
idioma del asistente y pulsa **Abrir app** al terminar. GTK y PyGObject deben estar
instalados para abrir esta ventana. La alternativa por terminal es
`python3 install.py`.

Para actualizar, cierra la app desde su menú de bandeja y abre el asistente de la
nueva descarga. Cerrar solo la ventana la mantiene en la bandeja.
**Preferencias → Herramientas y mantenimiento → Instalación y desinstalación** abre el asistente de una copia
instalada; pulsa **Comprobar de nuevo** después de salir de la app. Eliminar el
soporte USB es una opción separada, inicialmente desmarcada, que pide autorización
de administrador. Cancelarla detiene la eliminación antes de borrar archivos de
la app. Las actualizaciones interrumpidas ofrecen **Recuperar instalación** antes
de otros cambios.

Abre **Uplugo** desde el menú de aplicaciones. La app comienza en un idioma
compatible del sistema; usa inglés si no encuentra uno. Puedes elegir **Español**
en la pantalla de bienvenida o cambiarlo en Preferencias. Pulsa **Configurar acceso**.
El escritorio pide autorización de administrador para instalar el servicio USB
restringido. Ejecuta la interfaz con tu usuario normal, sin `sudo`.

Cancelar la autorización conserva tus modos y preferencias. Si falla, abre
**Detalles de la configuración** y vuelve a intentarlo. **Preferencias → Acceso
USB** permite revisarlo después. **¿Qué modo elegir?** explica las opciones sin
cambiarlas. **Explorar con mandos de demostración** abre un laboratorio sin acceso
a mandos reales ni conexión a internet.

Se necesita Python 3.10+, GTK 3, una sesión gráfica con D-Bus, libusb, polkit y udev.
El gestor systemd del usuario es opcional; si está disponible, supervisa la app.
El mando virtual también necesita UHID en el kernel y acceso a dispositivos
concedido por la sesión del escritorio. La instalación no activa el inicio
automático al entrar en tu cuenta.

## Elegir un modo para cada mando

| Modo | Qué hace | Cuándo usarlo |
| --- | --- | --- |
| **Mi configuración** | Los juegos reciben un DualSense virtual. Tu color, preferencia de vibración y resistencia de los gatillos tienen prioridad. | Para personalizar efectos mientras juegas. |
| **Configuración del juego** | Los juegos y Steam reciben el mando físico y controlan sus efectos nativos. | Cuando un juego necesita funciones nativas o no funciona con el mando virtual. |
| **Solo cargar** | El mando queda oculto para los juegos, con los efectos apagados y lecturas de batería disponibles. | Para dejarlo cargando sin enviar órdenes a un juego. |

El modo solo se confirma cuando responde el mando. Cambiar de modo de juego puede
reconectar el dispositivo que ve el juego. Si este no admite reconexiones, elige
el modo antes de abrirlo. Cada mando conserva su propio modo.

**Luces y efectos** permite elegir el color, la preferencia de vibración y la
resistencia de L2/R2. La resistencia cambia el peso al apretar, no la sensibilidad
de entrada. **Probar botones** muestra las entradas en un dibujo del mando.
La prueba no cambia el modo; en un modo de juego, el juego también recibe las entradas.

Usa la identificación por luces para localizar el mando físico antes de cambiar
su nombre. El nombre sigue a su identidad aunque cambies de puerto USB. Elige la
apariencia manualmente: USB no informa del color ni de la edición de la carcasa.

Desliza uno o dos dedos sobre el panel táctil para ver los puntos numerados.
Presiona para probar su clic por separado. Los detalles muestran las coordenadas
brutas. Los puntos desaparecen al soltar o perder la lectura; no se mide presión
ni se diagnostica el estado del hardware. La lectura de dos contactos se probó
con datos simulados; falta la validación física. Una instalación anterior ofrece
actualizar el helper USB antes de abrir la prueba ampliada.

En **Probar botones → Sticks**, pulsa **Medir reposo · 5 s** y suelta ambos
sticks. Después elige **Medir recorrido**, mueve cada uno hasta sus bordes y pulsa
**Ver resultado**. El centro medio y el rango en reposo quedan visibles; los
detalles muestran límites por eje y cantidad de lecturas. Las marcas indican
direcciones que alcanzaron el 80% del eje, no una prueba de salud aprobada.
El juego puede aplicar una zona muerta; esta prueba no cambia la calibración ni
los ajustes del juego. Perder la lectura o salir de la pestaña cancela una
medición en curso. Los resultados terminados permanecen hasta limpiar, repetir
o cerrar. Los datos quedan en memoria, con hasta 30 actualizaciones por segundo.
El flujo se probó con datos simulados; falta la validación física.

## Si un juego no responde

Comprueba que el mando esté en un modo de juego y que el juego tenga sus botones
asignados. En PCSX2, activa **SDL** en **Settings → Controllers** y elige el
DualSense disponible en **Controller Port 1 → Automatic Mapping**. Algunos juegos
con funciones nativas también necesitan Steam Input desactivado para ese juego.

El botón **Modo por juego** permite configurar el cambio automático opcional. Marca juegos que deban usar
temporalmente **Configuración del juego**. Solo cambia los mandos en **Mi configuración**;
los que estén en **Solo cargar** siguen ocultos. Al cerrar el juego vuelve el modo
guardado de la app.

## Batería, cierre y actualizaciones

La batería se informa en pasos aproximados. “Cargando” es el estado recibido del
mando, no una medición de corriente. Las lecturas antiguas se señalan como tales.
La app no aumenta la potencia USB ni mantiene alimentado el puerto con el PC apagado.

Cerrar la ventana mantiene la app en la bandeja. Si tu escritorio no tiene
bandeja, la ventana se minimiza. Volver a abrir el acceso del menú muestra la
misma app. Para detenerla, usa **Salir y liberar los mandos para Steam** en la
bandeja. Sin supervisión de systemd, la app no se reinicia automáticamente si falla.

Para que se abra sola, activa **Preferencias → Abrir al encender la computadora**.
Al iniciar sesión, la app empieza en la bandeja (o minimizada si no hay bandeja) y
mantiene el modo guardado de cada mando. La opción crea una entrada en
`~/.config/autostart`; desactivarla o desinstalar la app la elimina.

Para actualizar, sal de la app y ejecuta `python3 install.py` desde la nueva
carpeta del código. Los nombres y ajustes se conservan fuera del directorio del
programa. Las fotos oficiales se descargan por separado y se guardan localmente;
las ilustraciones incluidas funcionan sin internet. Puedes desactivar las
descargas en Preferencias.

El instalador rechaza la actualización si la app sigue abierta. Para quitarla,
ejecuta `python3 uninstall.py` en la carpeta extraída para ver la vista previa y,
después de salir de la app, `python3 uninstall.py --yes`. Nombres, ajustes, fotos
e historial se conservan para una reinstalación. Añade `--remove-access` para
quitar también el helper USB y sus reglas, con autorización administrativa
separada. Cancelarla mantiene la app instalada. Se conservan archivos modificados.
Los mensajes de mantenimiento están por ahora en portugués. Más detalles:
[guía de actualización y desinstalación](maintenance.md).

Bluetooth, actualización de firmware y audio USB virtual no están implementados.
Para háptica nativa completa basada en audio, usa Configuración del juego; también depende
del juego. El código usa GPL-3.0-only y el dibujo incluye su aviso MIT. Las fotos
conservan sus derechos originales. Proyecto sin afiliación con Sony ni Valve.

Para colaboradores: [verificar el paquete](releasing.md),
[compatibilidad Linux](linux-support.md), [trabajo pendiente](roadmap.md).

## Historial de batería

Abre **Batería y conexión** en el menú del mando. **En esta observación USB**
muestra el puerto, los porcentajes inicial y final y el tiempo entre las lecturas.
Despliega **Comparar observaciones anteriores** para consultar hasta 24 períodos
anteriores. Las reconexiones y las pausas en las lecturas inician otro período;
el tiempo sin datos no se cuenta. Las lecturas se guardan en este equipo. La
variación puede incluir uso y carga: no mide la velocidad del cargador, la
corriente del cable ni la salud de la batería. La app registra el puerto USB,
pero no identifica el cable utilizado.

## Recuperar una actualización interrumpida

Abre la app desde el menú y elige **Recuperar instalación**. Se restaura la versión
anterior o se termina la limpieza si la actualización ya había finalizado. Se
conservan tus nombres, preferencias, fotos e historial. La recuperación no pide
contraseña ni cambia el acceso USB. Al terminar, elige **Abrir app**.

Si la primera instalación se interrumpió antes de crear el acceso del menú,
ejecuta `python3 install.py --recover` desde la carpeta extraída de la descarga.
Si indica que se revirtió la primera instalación, ejecuta `python3 install.py`
de nuevo. Cierra antes la app desde la bandeja. Si algún archivo cambió después
de la interrupción, la recuperación conserva sus copias e informa del conflicto
en lugar de sobrescribirlo. Conserva esas copias hasta resolver el problema.

## El panel táctil mueve el cursor del escritorio

Abre **Panel táctil y cursor** en el menú del mando. Elige **Usar en juegos sin
mover el cursor de Linux** y pulsa **Aplicar en Linux**. Pide autorización del
sistema y cambia solo la regla del panel táctil de ese mando. Se aplica a todas
las cuentas del equipo y permanece al cerrar o desinstalar la app. Para deshacerlo,
elige **Restaurar el comportamiento predeterminado de Linux** y vuelve a aplicar.
Un mando en Solo cargar conserva ese modo; la regla se usa cuando reaparece su
panel táctil.

Steam también puede convertir el panel táctil en ratón por su cuenta. Si aún mueve
el cursor, revisa tanto el diseño del mando para el juego como el del escritorio
en Steam. Configuración del juego no desactiva Steam Input ni añade funciones que el juego
no admite. La regla que muestra Linux no confirma que el juego reciba las entradas;
prueba el clic y los contactos en el juego. Faltan pruebas en escritorios
distintos de GNOME y en la mayoría de los juegos.

## Nombres, modelos y fotos

Abre **Nombre y apariencia** desde el menú del mando o pulsa el nombre de su modelo.
La galería permite buscar y filtrar por categoría; la selección se conserva
aunque quede fuera del filtro. **Guardar** se habilita cuando hay un cambio y
un nombre no vacío. **Cancelar** descarta el borrador de nombre y modelo. Intro
en la búsqueda no guarda el formulario. Si falla la escritura, el borrador se
conserva para volver a intentarlo.

Elige un modelo y abre **Biblioteca de fotos… → Añadir o sustituir foto…** para
importar un PNG, JPEG o WebP. **Añadir a la biblioteca** guarda esa foto para todos
los mandos que usan el mismo modelo. Cerrar o cancelar el formulario de nombre
y modelo no elimina una foto que añadiste expresamente en la biblioteca. Esta
ventana también controla las descargas automáticas. Una imagen inválida no
sustituye una foto existente.

**Fotos oficiales (opcional, desactivado por defecto):** en **Preferencias → Fotos
de los mandos**, activa **Descargar fotos automáticamente** y la app obtiene las
fotos del catálogo desde los servidores de Sony, solo para uso en tu computadora.
No forman parte del proyecto.

## Sensores de movimiento

Abre **Probar botones → Movimiento** para ver velocidad de rotación (°/s),
aceleración (g) y diez segundos de historial local. La calibración de fábrica se
lee sin modificarla; si falta, la lectura se indica como no disponible. Salir
de la pestaña o perder la entrada borra el historial. Incluye la gravedad: en
reposo, la intensidad total suele estar cerca de 1 g. No mide orientación,
latencia ni compatibilidad del juego con apuntado por movimiento; pequeñas
oscilaciones no prueban un defecto.

## Falta el clic del panel táctil en Steam Snap

En **Panel táctil y cursor**, elige **Comprobar acceso de Steam Snap**. Si Steam
está instalado mediante Snap, puedes permitir acceso USB completo a este mando
con autorización del sistema. Guarda tu partida y cierra y abre Steam después
de aplicar. La app no cierra Steam ni cambia el modo del mando. Esta opción no
asigna una acción al panel táctil en el diseño del juego. **Eliminar el permiso
añadido por esta app** deshace esta autorización y conserva los demás permisos.
La configuración afecta a todas las cuentas y permanece tras desinstalar la app.
Su estado comprueba la configuración de Linux, no el funcionamiento en un juego.

## Comparar cables y observaciones de carga

Abre **Batería y conexión → Anotar cable y condiciones**. Puedes registrar el
cable, hub u otras condiciones del período actual o de una observación anterior.
Son notas tuyas; la app no identifica los cables. **Guardar** almacena hasta 160
caracteres localmente. **Cancelar** conserva la nota anterior; guardar el campo
vacío la elimina. Si el mando se reconecta mientras escribes, la nota se queda
en el período original. No pasa a la nueva conexión ni se exporta en diagnósticos.
Los porcentajes son observaciones aproximadas, no medidas de velocidad de carga.
