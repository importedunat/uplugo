#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
"""Small USB interface switch for Sony DualSense controllers."""
import os
from pathlib import Path
import re
import subprocess
import sys
import json
import time
import select
import tempfile
from datetime import datetime

USB = Path('/sys/bus/usb/devices')
def xdg_directory(variable, fallback):
    value = os.environ.get(variable, '')
    return Path(value) if value and Path(value).is_absolute() else Path.home()/fallback

CONFIG_DIR = xdg_directory('XDG_CONFIG_HOME', '.config')/'dualsense-usb'
STATE_DIR = xdg_directory('XDG_STATE_HOME', '.local/state')/'dualsense-usb'
CACHE = STATE_DIR/'battery-readings.json'
SETTINGS = CONFIG_DIR/'controllers.json'

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def migrate_legacy():
    """One-time migration; retain source files as ignored recovery backups."""
    base = Path(__file__).resolve().parent
    for name, target in [('controllers.json', SETTINGS),
                         ('battery-readings.json', CACHE),
                         ('charge-history.json', STATE_DIR/'charge-history.json')]:
        source = base/name
        if not target.exists() and source.exists():
            try: write_json(target, json.loads(source.read_text()))
            except (OSError, ValueError): pass

def settings():
    try:
        data = json.loads(SETTINGS.read_text())
        if not isinstance(data, dict): raise ValueError('Preferências inválidas.')
    except (OSError, ValueError): data = {}
    for section in ('names','connections','modes','effects','ui','appearance','protection'):
        if not isinstance(data.get(section),dict): data[section] = {}
    for section in ('names','connections','appearance'):
        data[section]={key:value for key,value in data[section].items() if isinstance(value,str)}
    data['modes']={key:value for key,value in data['modes'].items() if isinstance(value,str) and value in {'charge','proxy','play'}}
    effects={}
    for key,value in data['effects'].items():
        if not isinstance(value,dict):continue
        clean={}
        rgb=value.get('rgb')
        if isinstance(rgb,list) and len(rgb)==3 and all(type(channel) is int and 0<=channel<=255 for channel in rgb):clean['rgb']=rgb
        for field,choices in [('vibration',('game','low','off')),('triggers',('game','off','light','medium','firm'))]:
            if value.get(field) in choices:clean[field]=value[field]
        if clean:effects[key]=clean
    data['effects']=effects
    protection=data['protection']
    if not isinstance(protection.get('play_exceptions',[]),list):protection['play_exceptions']=[]
    protection['play_exceptions']=[item for item in protection.get('play_exceptions',[]) if isinstance(item,str)]
    if not isinstance(protection.get('last_actions',{}),dict):protection['last_actions']={}
    protection['last_actions']={key:value for key,value in protection.get('last_actions',{}).items() if isinstance(value,str)}
    if not isinstance(data.get('native_games'), list): data['native_games'] = []
    data['native_games']=[item for item in data['native_games'] if isinstance(item,str)]
    return data

def fingerprint(device):
    try:
        return ':'.join([Path('/proc/sys/kernel/random/boot_id').read_text().strip(), device.name, (device/'devnum').read_text().strip()])
    except OSError: return ''

def hardware_identity(device):
    try:
        value = (device/'serial').read_text().strip()
        if value: return 'serial:' + value
    except OSError: pass
    for hid in Path('/sys/bus/hid/devices').iterdir():
        if belongs(hid, device):
            try:
                for line in (hid/'uevent').read_text().splitlines():
                    if line.startswith('HID_UNIQ=') and line[9:].strip():
                        return 'hid:' + line[9:].strip().lower()
            except OSError: pass
    return None

def remember(device, identity):
    if identity:
        data = settings()
        connection = fingerprint(device)
        if data['connections'].get(connection) != identity:
            data['connections'][connection] = identity
            write_json(SETTINGS, data)

def nickname(device):
    return settings()['names'].get(key(device), 'DualSense — ' + device.name)

def belongs(entry, device):
    return device.resolve() in entry.resolve().parents

def battery(device):
    for entry in Path('/sys/class/power_supply').iterdir():
        if belongs(entry, device):
            try:
                capacity = int((entry/'capacity').read_text().strip())
                status = (entry/'status').read_text().strip()
                if status == 'Unknown' or not 0 <= capacity <= 100:
                    return None
                reading = {'capacity': capacity, 'status': status, 'time': datetime.now().strftime('%H:%M:%S')}
                try: reading['voltage'] = int((entry/'voltage_now').read_text().strip()) / 1000000
                except (OSError, ValueError): pass
                return reading
            except (OSError, ValueError):
                pass
    return None

def raw_device(device):
    for raw in Path('/sys/class/hidraw').iterdir():
        if belongs(raw, device):
            return Path('/dev')/raw.name
    return None

def decode_battery(report):
    if len(report) != 64 or report[0] != 1: return None
    value = report[53]
    state = value >> 4
    if state not in {0, 1, 2}: return None
    return {'capacity': 100 if state == 2 else min((value & 15)*10+5, 100),
            'status': {0:'Discharging',1:'Charging',2:'Full'}[state],
            'time':datetime.now().strftime('%H:%M:%S'), 'source':'USB'}

def raw_battery(device, timeout=5):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        node=raw_device(device)
        if node: break
        time.sleep(.1)
    else: return None
    fd=os.open(node,os.O_RDONLY|os.O_NONBLOCK)
    try:
        while time.monotonic()<deadline:
            if select.select([fd],[],[],.2)[0]:
                try:packet=os.read(fd,128)
                except BlockingIOError:continue
                if not packet:return None
                reading=decode_battery(packet)
                if reading:return reading
    finally:os.close(fd)
    return None

TRIGGER_PRESETS = {'game': None, 'off': 0, 'light': 2, 'medium': 4, 'firm': 6}

def trigger_effect(preset):
    """USB feedback effect: ten zones, each with a three-bit strength.

    Protocol reference: nowrep/dualsensectl main.c (GPL-2.0-or-later),
    Sony Interactive Entertainment and dualsensectl contributors.
    This implementation offers fixed feedback presets only, never raw writes.
    """
    if preset not in TRIGGER_PRESETS: raise ValueError('Resistência de gatilho inválida.')
    strength = TRIGGER_PRESETS[preset]
    if strength is None: return None
    if strength == 0: return bytes([5]) + bytes(10)
    active = 0x3fc  # Zones 2..9: allow initial free movement.
    packed = sum((strength - 1) << (zone * 3) for zone in range(2,10))
    return bytes([0x21]) + active.to_bytes(2,'little') + packed.to_bytes(4,'little') + bytes(4)

def effects_report(config, test=False):
    rgb=config.get('rgb')
    vibration=config.get('vibration','game')
    if rgb is not None and (not isinstance(rgb,list) or len(rgb)!=3 or any(type(v)!=int or not 0<=v<=255 for v in rgb)):
        raise ValueError('Cor inválida.')
    if vibration not in {'game','low','off'}: raise ValueError('Vibração inválida.')
    report=bytearray(63);report[0]=2
    trigger=trigger_effect(config.get('triggers','game'))
    if trigger is not None:
        report[1]|=0x0c
        report[11:22]=report[22:33]=trigger
    if rgb is not None:
        report[2]|=4;report[45:48]=bytes(rgb)
    if vibration in {'game','low'}:
        report[2]|=64;report[37]=3 if vibration=='low' else 0
    if vibration=='off' or test:
        report[1]|=3;report[3]=report[4]=100 if test else 0
    return bytes(report)

def stream_control(name):
    if os.geteuid()!=0 or not re.fullmatch(r'\d+-\d+(?:\.\d+)*',name) or not supported(USB/name):
        raise ValueError('Controle inválido.')
    device=USB/name;node=raw_device(device)
    deadline=time.monotonic()+3
    while node is None and time.monotonic()<deadline:
        time.sleep(.05);node=raw_device(device)
    if not node: raise ValueError('Ative Jogar para controlar luzes e vibração.')
    fd=os.open(node,os.O_RDWR|os.O_NONBLOCK)
    config=None;next_write=0;next_status=0;test_until=0;stopping=False
    buffer=b''
    monitor=InputMonitor()
    try:
        while supported(device) and not stopping:
            ready=select.select([fd,sys.stdin.fileno()],[],[],.05)[0]
            if sys.stdin.fileno() in ready:
                chunk=os.read(sys.stdin.fileno(),4096)
                if not chunk:break
                buffer+=chunk
                if len(buffer)>8192:raise ValueError('Comando muito longo.')
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    request=json.loads(line)
                    if 'monitor' in request:
                        monitor.request(request['monitor'],time.monotonic())
                        if request['monitor']:monitor.load_calibration(lambda:read_motion_feature(fd))
                        continue
                    if request.get('stop'):stopping=True;break
                    if request.get('release'):
                        if test_until:os.write(fd,effects_report({'vibration':'off'}));test_until=0
                        config=None
                    else:
                        effects_report(request)
                        config=request
                        if request.get('test'):test_until=time.monotonic()+1
                    next_write=0
            if stopping:break
            if fd in ready:
                try:packet=os.read(fd,128)
                except BlockingIOError:pass
                else:
                    if not packet:raise OSError('A leitura USB foi encerrada pelo dispositivo.')
                    telemetry=monitor.feed(packet,time.monotonic())
                    if telemetry:print(json.dumps(telemetry),flush=True)
                    reading=decode_battery(packet)
                    if reading and time.monotonic()>=next_status:
                        print(json.dumps({'reading':reading,'identity':hardware_identity(device)}),flush=True)
                        next_status=time.monotonic()+1
            now=time.monotonic()
            if test_until and now>=test_until:
                os.write(fd,effects_report({'vibration':'off'}));test_until=0;next_write=0
            if config is not None and now>=next_write:
                os.write(fd,effects_report(config,now<test_until));next_write=now+.15
    finally:
        try:
            if config and (config.get('vibration')=='off' or test_until):
                os.write(fd,effects_report({'vibration':'off'}))
        except OSError:pass
        os.close(fd)

def inspect_control(name, identify=False):
    if os.geteuid() != 0 or not re.fullmatch(r'\d+-\d+(?:\.\d+)*', name) or not supported(USB/name):
        raise ValueError('Controle inválido.')
    device = USB/name
    original = {p.name: (p/'authorized').read_text().strip() for p in interfaces(device)}
    if not original:
        raise ValueError('Reconecte o controle.')
    try:
        switch(name, 'play')
        reading = raw_battery(device) or battery(device)
        if identify:
            leds = [p/'brightness' for p in Path('/sys/class/leds').iterdir() if belongs(p, device) and 'player' in p.name]
            if not leds:
                raise ValueError('Luzes de identificação indisponíveis. Reconecte o controle e tente novamente.')
            saved = {p: p.read_text().strip() for p in leds}
            try:
                for _ in range(4):
                    for p in leds: p.write_text('1')
                    time.sleep(.35)
                    for p in leds: p.write_text('0')
                    time.sleep(.35)
            finally:
                for p, value in saved.items(): p.write_text(value)
        return {'reading': reading, 'identity': hardware_identity(device)}
    finally:
        for interface, value in original.items():
            (USB/interface/'authorized').write_text(value)
        for interface, value in original.items():
            if value == '1': (USB.parent/'drivers_probe').write_text(interface)

def read_cache():
    try:
        data=json.loads(CACHE.read_text())
        if not isinstance(data,dict):return {}
        return {key:value for key,value in data.items() if isinstance(value,dict)
                and value.get('status') in ('Charging','Discharging','Full')
                and type(value.get('capacity')) is int and 0<=value['capacity']<=100
                and isinstance(value.get('time',''),str)}
    except (OSError, ValueError): return {}

def key(device):
    identity = hardware_identity(device)
    if identity:
        remember(device, identity)
        return identity
    return settings()['connections'].get(fingerprint(device), 'connection:' + fingerprint(device))

def save_reading(device, reading):
    if reading and reading.get('status') != 'Unknown':
        cache = read_cache()
        cache[key(device)] = {k:v for k,v in reading.items() if not k.startswith('_')}
        write_json(CACHE, cache)

def supported(p):
    try:
        return (p/'idVendor').read_text().strip() == '054c' and (p/'idProduct').read_text().strip() in {'0ce6', '0df2'}
    except OSError:
        return False

def interfaces(p):
    return sorted(x for x in USB.glob(p.name + ':*') if (x/'authorized').exists())

def switch(name, mode):
    if os.geteuid() != 0 or not re.fullmatch(r'\d+-\d+(?:\.\d+)*', name) or mode not in {'play', 'charge'}:
        raise ValueError('Operação inválida.')
    p = USB/name
    if not supported(p):
        raise ValueError('DualSense não encontrado nessa conexão USB.')
    items = interfaces(p)
    if not items:
        raise ValueError('Nenhuma interface USB encontrada. Reconecte o controle.')
    value = '1' if mode == 'play' else '0'
    try:
        for item in items:
            (item/'authorized').write_text(value)
        if mode == 'play':
            for item in items:
                (USB.parent/'drivers_probe').write_text(item.name)
        if any((item/'authorized').read_text().strip() != value for item in items):
            raise OSError('Não foi possível confirmar o modo.')
    except Exception:
        # Restore usable interfaces if a partial transition fails.
        for item in items:
            try:
                (item/'authorized').write_text('1')
                (USB.parent/'drivers_probe').write_text(item.name)
            except OSError:
                pass
        raise

if __name__ == '__main__':
    raise SystemExit('Abra o aplicativo com python3 launch.py.')
