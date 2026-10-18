# Uplugo: quick start

[English overview](../README.md) · [Português](../README.pt-BR.md) · English quick start · [Español](quickstart.es.md)

An independent Linux app for using and charging DualSense controllers over USB.
You choose whether games or the app control the effects. This is an experimental
alpha: physical testing currently covers standard DualSense controllers on the
development Ubuntu machine. Other distributions and the Edge need further testing.

The main window rearranges controller photos and actions to fit narrower screens. Select a controller at the top to open its controls. Help highlights each function in place. Text follows GTK font and text scaling settings; GTK high-contrast themes keep their own interface colors.

## Install

Use a USB **data cable**. A charging-only cable cannot carry controller inputs.
Userspace installation and GUI tests pass on Ubuntu 24.04, Debian 13 and Fedora 44.
Physical testing covers the development Ubuntu session only; see the
[support matrix](linux-support.md).

Install the dependencies for your distribution:

**Ubuntu or Debian**

```sh
sudo apt install python3 python3-gi gir1.2-gtk-3.0 librsvg2-common libusb-1.0-0 libayatana-appindicator3-1 pkexec udev ca-certificates
```

**Traditional Fedora 44 with DNF (experimental)**

```sh
sudo dnf install python3 python3-gobject gobject-introspection gtk3 librsvg2 libusb1 libayatana-appindicator-gtk3 polkit systemd-udev ca-certificates
```

`gobject-introspection` supplies types required by GTK 3 even when PyGObject is
installed. Fedora desktop authorization, SELinux integration and real USB remain
unverified; Silverblue and Kinoite have not been tested.

Then, in the extracted source folder, run:

```sh
python3 doctor.py --no-session
python3 setup.py
```

The assistant offers **Install or update** and **Uninstall for my account**, checks
requirements and preserves names, preferences, photos and history. Select your
language in the assistant and choose **Open app** after installation. GTK and
PyGObject must already be installed to open the assistant. The command-line
alternative is `python3 install.py`.

For updates, exit the app through its tray menu first and open the assistant from
the new download. Closing the app window only hides it. **Preferences → Tools and maintenance → Install and uninstall** opens the assistant from an installed copy; choose **Check again**
after exiting the app. Removing USB support is a separate, initially unchecked
option requiring administrator authorization. Cancelling that authorization
stops removal before deleting app files. Interrupted updates offer **Recover
installation** before other changes.

Open **Uplugo** from the applications menu. The app starts in a supported
system language, with English as the fallback. You can select **English** on the
welcome screen, or change the language in Preferences. Select **Set up access**. The desktop
asks for administrator authorization to install the restricted USB helper.
Run the interface as your normal user, not with `sudo`.

Cancelling authorization keeps your modes and preferences. If setup fails,
expand **Setup details** and try again. **Preferences → USB access** lets you
review setup later. **Which mode should I use?** explains the choices without
changing anything. **Explore with demo controllers** opens an offline lab that
does not access real controllers.

Python 3.10+, GTK 3, a graphical D-Bus session, libusb, polkit and udev are required.
A user systemd manager is optional; when available it supervises the app.
The virtual controller also needs kernel UHID support and device access granted
by the desktop session. Installing the app does not enable automatic login startup.

## Choose a mode for each controller

| Mode | What you get | Choose it when… |
| --- | --- | --- |
| **My settings** | Games see a virtual DualSense. Your saved light color, rumble preference and trigger resistance take priority. | You want to customize effects while playing. |
| **Game settings** | Games and Steam receive the physical controller and control its native effects. | A game needs native DualSense features or does not work with the virtual device. |
| **Charge only** | The controller stays hidden from games; effects are off and battery reports remain available. | You want to leave it charging without controlling a game. |

The selected mode is confirmed only after the controller responds. Switching a
play mode can reconnect the device seen by games. Select the mode before starting
a game if it does not handle reconnecting. Each controller keeps its own mode.

**Lights and effects** changes the light color, rumble preference and L2/R2
resistance. Resistance changes how heavy a trigger feels, not its input
sensitivity. **Test buttons** shows live inputs on a controller blueprint.
The test does not change the mode; in a play mode, the game also receives inputs.

Slide one or two fingers on the touchpad to see numbered contacts. Press down
to test its click separately. **Test details** shows the raw coordinates.
Contacts clear when lifted or when input is stale; this is not a pressure or
hardware-health test. Two-contact decoding has synthetic coverage; physical
validation is still pending. An older installation offers a USB helper update
before opening the enhanced test.

In **Test buttons → Sticks**, choose **Measure rest · 5 s** and release both sticks.
Then select **Measure range**, move each stick around its edges and select
**View result**. The average center and rest range stay visible; expand the
measurements for axis limits and sample counts. Checkmarks mean a direction
reached 80% of its axis, not that the controller passed a health test. Games can
apply a deadzone; this test changes neither calibration nor game settings.
Losing input or leaving the tab cancels an unfinished measurement. Finished
results stay frozen until cleared, repeated or closed. Data stays in memory,
sampled at up to 30 updates per second. The guided flow has synthetic test
coverage; physical validation is pending.

Use the light-identification action to find the right physical controller before
renaming it. Names follow the hardware identity when you change USB ports.
Select the shell appearance yourself: USB does not report its color or edition.

## If a game does not respond

Check that the controller is in a play mode and that the game has mapped it.
For PCSX2, enable **SDL** in **Settings → Controllers**, then choose the available
DualSense under **Controller Port 1 → Automatic Mapping**. Native DualSense
features in some games also require disabling Steam Input for that game.

The **Mode per game** button opens optional automatic switching. Mark games that should temporarily use
**Game settings**. This affects controllers in **My settings**; controllers
in **Charge only** remain hidden. When the game closes, the saved app mode returns.

## Battery, closing and updates

Battery percentages arrive in coarse steps. “Charging” is the controller's report,
not a measurement of charging current. Old readings are marked as stale. The app
cannot increase USB power or keep a port powered when the PC is off.

Closing the window keeps the app in the tray. If your desktop has no tray, the
window is minimized instead. Reopening the menu shortcut reveals the same app.
Use **Quit and release controllers to Steam** in the tray to stop it. Without
systemd supervision, a crashed app is not automatically restarted.

To start it automatically, enable **Preferences → Open when the computer starts**.
When you log in, the app starts in the tray (or minimized without a tray) and keeps
each controller's saved mode. The option adds an entry in `~/.config/autostart`;
turning it off or uninstalling removes it.

For updates, quit the app first, then run `python3 install.py` from the new source
folder. Names and preferences are preserved outside the program directory.
Official product images download separately and are cached locally; included
illustrations remain available offline. Downloads can be disabled in Preferences.

The installer refuses an update while the app is running. To uninstall, run
`python3 uninstall.py` in the extracted package folder for a preview, then
`python3 uninstall.py --yes` after quitting the app. Names, preferences, photos
and history remain available for a later reinstall. Add `--remove-access` to
remove the USB helper and its rules too; this requires separate administrator
authorization. Cancelling it keeps the app installed. Modified files are kept.
Maintenance command output is currently in Portuguese. More details:
[update and removal guide](maintenance.md).

Bluetooth, firmware updates and virtual USB audio are not implemented. For full
native audio-based haptics, use Game settings; support still depends on the game.
The code is GPL-3.0-only; the blueprint's MIT notice is included. Product images
retain their original rights. This project is not affiliated with Sony or Valve.

For maintainers: [source package checks](releasing.md),
[support matrix](linux-support.md), [remaining work](roadmap.md).

## Battery history

Open **Battery and connection** in the controller menu. **This USB observation**
shows the port, first/last percentages and elapsed time between actual reports.
Expand **Compare previous observations** to view up to 24 earlier periods.
Reconnections and gaps in reports start a separate period; offline time is not
counted. Readings stay on this computer. The change can include use and charging:
it does not measure charger speed, cable current or battery health. The app
records the USB port but cannot identify which cable you used.

## Recovering an interrupted update

Open the app from the menu and choose **Recover installation**. It restores the
previous version or finishes cleanup if the update had already completed. Your
names, preferences, photos and history are preserved. Recovery runs without a
password and does not change USB access. Choose **Open app** when it finishes.

If the first installation stopped before creating the menu entry, run
`python3 install.py --recover` from the extracted download folder. If it reports
that the first installation was rolled back, run `python3 install.py` again.
Quit the app from the tray first. If files changed after the interruption,
recovery preserves its backups and reports the conflict instead of replacing
them. Keep those recovery files until the problem is resolved.

## Touchpad moves the desktop cursor

Open **Touchpad and cursor** in the controller menu. Choose **Use in games without
moving the Linux cursor**, then **Apply to Linux**. This requests system
authorization and changes only this controller's touchpad policy. It applies to
every account on this computer and remains after closing or uninstalling the app.
To undo it, choose **Restore Linux default behavior** and apply again. A controller
in Charge only stays in that mode; its touchpad uses the setting when it reappears.

Steam can also map the touchpad to a mouse independently. Check both the game's
controller layout and Steam's desktop layout if the cursor still moves. Direct
play does not disable Steam Input or add touchpad support to a game. The displayed
Linux rule is not proof that a game received input; test its click and contacts
in the game. Desktops other than GNOME and most games still need testing.

## Names, models and photos

Open **Name and appearance** from the controller menu or click its model name.
The gallery supports search and category filters; your selection stays selected
when filtered out. **Save** becomes available after a change with a nonempty
name. **Cancel** discards the name/model draft. Pressing Enter in search does
not save the form. A write failure keeps your draft available for another try.

Choose a model, then open **Photo library… → Add or replace photo…** to import
a PNG, JPEG or WebP. **Add to library** saves that photo for all controllers using
the same model. Closing or canceling the name/model form does not remove a photo
you explicitly added in the library. Invalid images do not replace an existing photo.

**Official photos (optional, off by default):** in **Preferences → Controller
photos**, enable **Download photos automatically** and the app fetches the
catalog photos from Sony's servers, for use on this computer only. They are not
part of the project.

## Motion sensors

Open **Test buttons → Motion** to view rotation speed (°/s), acceleration (g),
and a ten-second local trace. Factory calibration is read without being changed.
Missing calibration is shown as unavailable. Leaving the tab or losing input
clears its history. Gravity is included: a stationary controller is normally
near 1 g in total. This does not measure orientation, game latency or gyro-aim
support, and small fluctuations do not diagnose a fault.

## Touchpad click missing in Steam Snap

In **Touchpad and cursor**, choose **Check Steam Snap access**. If Steam is
installed through Snap, you can allow full USB access to this controller with
system authorization. Save your game, close and reopen Steam after applying.
The app does not close Steam or change the controller mode. This does not assign
a touchpad action in a game layout. Use **Remove the permission added by this app**
to undo this grant; other permissions remain. The setting affects all accounts
and remains after uninstalling the app. Its status checks Linux configuration,
not actual behavior inside a game.

## Compare cables and charging observations

Open **Battery and connection → Note cable and conditions**. You can record a
cable, hub or other condition for the current period or a previous observation.
These are your own notes; the app cannot identify cables. **Save** stores up to
160 characters locally. **Cancel** keeps the previous note; saving an empty field
removes it. If the controller reconnects while you write, the note stays with the
original period. It is not copied to the new connection or exported in diagnostics.
Battery percentages are coarse observations, not measurements of charger speed.
