# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in native-game exceptions; never infer support or launch commands."""
from i18n import _
import os
import re
from pathlib import Path


def is_steam_component(name):
    """Exclude known support packages without hiding games such as Proton Pulse."""
    return bool(re.fullmatch(
        r'Proton (?:Experimental|Hotfix|Next|\d+(?:\.\d+)*(?:[ -].*)?)'
        r'|Steam Linux Runtime(?: [\d.]+)?(?: \([^)]+\))?'
        r'|Steamworks (?:Common Redistributables|Shared)'
        r'|Steam (?:Controller Configs|Input Configs|VR|Linux Soldier Runtime)',
        name.strip(), re.IGNORECASE))


def installed_games(roots=None):
    if roots is None:
        home = Path.home()
        roots = [home/'.local/share/Steam', home/'.steam/steam',
                 home/'snap/steam/common/.local/share/Steam']
    libraries = {Path(root).resolve() for root in roots}
    def field(text, key):
        match = re.search(r'"' + key + r'"\s+"((?:\\.|[^"\\])*)"', text)
        return re.sub(r'\\([\\"])', r'\1', match[1]) if match else None
    for root in list(libraries):
        try:
            text = (root/'steamapps/libraryfolders.vdf').read_text()
            for match in re.finditer(r'"path"\s+"((?:\\.|[^"\\])*)"', text):
                libraries.add(Path(re.sub(r'\\([\\"])', r'\1', match[1])))
        except OSError:
            continue
    games = {}
    for root in libraries:
        for manifest in (root/'steamapps').glob('appmanifest_*.acf'):
            try:
                text = manifest.read_text()
                appid, name = field(text, 'appid'), field(text, 'name')
                if appid and appid.isdecimal() and name and not is_steam_component(name):
                    games[appid] = name
            except OSError:
                continue
    return dict(sorted(games.items(), key=lambda item: item[1].casefold()))


def parse_profiles(text):
    profiles = []
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        if value.isdecimal():
            if int(value) <= 0:
                raise ValueError(_('O ID da Steam deve ser maior que zero.'))
            value = str(int(value))
        elif not re.fullmatch(r'[\w .+()\-]+\.exe', value, re.IGNORECASE):
            raise ValueError(_('Use um ID numérico da Steam ou o nome completo do jogo.exe por linha.'))
        if value.casefold() not in {p.casefold() for p in profiles}:
            profiles.append(value)
    return profiles


def matching_game(profiles, processes):
    for profile in profiles:
        for steam_id, executables in processes:
            if (profile.isdecimal() and profile == steam_id or
                    not profile.isdecimal() and profile.casefold() in executables):
                return profile
    return None


def running_game(profiles):
    if not profiles:
        return None
    processes = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            args = (proc/'cmdline').read_bytes().split(b'\0')
            # Do not treat arbitrary arguments as processes. Wine commonly puts
            # the Windows executable immediately after wine[64]/wine-preloader.
            names = set()
            first = args[0].decode(errors='replace').replace('\\', '/').rsplit('/', 1)[-1]
            names.add(first.casefold())
            if first.casefold().startswith('wine') and len(args) > 1:
                names.add(args[1].decode(errors='replace').replace('\\', '/').rsplit('/', 1)[-1].casefold())
            steam_id = None
            for entry in (proc/'environ').read_bytes().split(b'\0'):
                if entry.startswith(b'SteamAppId='):
                    steam_id = entry.partition(b'=')[2].decode(errors='replace')
                    break
            processes.append((steam_id, names))
        except (OSError, IndexError):
            continue
    return matching_game(profiles, processes)


class GameDetector:
    def __init__(self):
        self.candidate = None
        self.count = 0
        self.active = None

    def update(self, candidate):
        if candidate != self.candidate:
            self.candidate, self.count = candidate, 1
        else:
            self.count += 1
        # Two sightings to enter; three absent scans to leave. Avoid rapidly
        # reconnecting on process handoffs during Proton/game startup.
        if self.count >= (2 if candidate else 3):
            self.active = candidate
        return self.active


def effective_mode(preferred, native_game):
    return 'play' if preferred == 'proxy' and native_game else preferred
