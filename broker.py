# SPDX-License-Identifier: GPL-3.0-only
"""Exclusive physical USB -> Linux UHID, with a narrow output policy.

This module is embedded into the root-owned helper at build time. It never
loads user-provided descriptors, Python modules, paths or feature commands.
ABI: include/uapi/linux/uhid.h; reports: Linux hid-playstation.c.
"""
import errno
import struct

BROKER_VERSION = 'uhid-1'
TRIGGER_CONTROL_VERSION = 2
FEATURE_LENGTHS = {0x05: 41, 0x09: 20, 0x20: 64}


def filter_output(packet, config=None):
    """Keep native trigger/audio fields; override only selected effects."""
    if len(packet) not in (48, 63, 64) or packet[0] != 2:
        raise ValueError('Relatório de efeitos inválido.')
    result = bytearray(packet[:63]).ljust(63, b'\0')
    if config is None:
        return bytes(result)
    effects_report(config)  # Shared validation, including RGB bounds.
    trigger = trigger_effect(config.get('triggers','game'))
    if trigger is not None:
        result[1] |= 0x0c
        result[11:22] = result[22:33] = trigger
        # A game's attenuation packet can otherwise weaken our feedback even
        # though its trigger-effect bytes are replaced. Keep rumble attenuation.
        result[2] |= 0x40
        result[37] &= 0x0f
    rgb = config.get('rgb')
    if rgb is not None:
        result[2] = (result[2] | 4) & ~8  # Do not release LEDs to firmware.
        result[39] &= ~3  # Ignore game lightbar reset/brightness commands.
        result[45:48] = bytes(rgb)
    vibration = config.get('vibration', 'game')
    if vibration == 'off':
        result[1] |= 3
        result[3:5] = b'\0\0'
        result[2] |= 2
        result[10] |= 0x80  # Also mute haptics fed through USB audio.
    elif vibration == 'low':
        # Scale both rumble protocols, preserving adaptive-trigger effects.
        result[3] //= 3
        result[4] //= 3
        result[2] |= 0x40
        result[37] = (result[37] & 0xf0) | 3
    return bytes(result)


class VirtualDualSense:
    def __init__(self, descriptor, product, version, identity):
        if not 1 <= len(descriptor) <= 4096:
            raise ValueError('Descritor HID inválido.')
        self.fd = os.open('/dev/uhid', os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        self.started = False
        try:
            uniq = (identity or '').removeprefix('hid:').encode('ascii')[:63]
            payload = struct.pack('=128s64s64sHHIIII',
                                  b'Uplugo DualSense',
                                  b'dualsense-usb/' + uniq, uniq,
                                  len(descriptor), 3, 0x054c, product, version, 0)
            self.write(11, payload + descriptor)  # UHID_CREATE2
        except BaseException:
            self.close()
            raise

    def write(self, kind, payload=b''):
        event = struct.pack('=I', kind) + payload
        if os.write(self.fd, event) != len(event):
            raise OSError('Evento UHID incompleto.')

    def input(self, packet):
        self.write(12, struct.pack('=H', len(packet)) + packet)

    def close(self):
        if self.fd is not None:
            # Closing destroys the virtual device before physical reattachment.
            os.close(self.fd)
            self.fd = None

    def drain(self, features, output):
        for _ in range(64):  # Bound work so physical input cannot starve.
            try:
                event = os.read(self.fd, 4380)
            except BlockingIOError:
                break
            if not event:
                raise OSError('Dispositivo UHID encerrado.')
            kind = struct.unpack_from('=I', event)[0]
            event = event.ljust(4380, b'\0')
            if kind == 2:
                self.started = True
            elif kind == 6:  # UHID_OUTPUT
                size, report_type = struct.unpack_from('=HB', event, 4100)
                if report_type == 1 and size <= 4096:
                    output(event[4:4 + size])
            elif kind == 9:  # UHID_GET_REPORT
                request, number, report_type = struct.unpack_from('=IBB', event, 4)
                data = features.get(number, b'') if report_type == 0 else b''
                self.write(10, struct.pack('=IHH', request,
                                          0 if data else errno.EOPNOTSUPP,
                                          len(data)) + data)
            elif kind == 13:  # UHID_SET_REPORT
                request, number, report_type, size = struct.unpack_from('=IBBH', event, 4)
                # Games may set OUTPUT reports, but never firmware, pairing,
                # calibration or NVS feature writes through this root helper.
                error = errno.EOPNOTSUPP
                if report_type == 1 and number == 2 and size <= 4096:
                    error = 0 if output(event[12:12 + size]) else errno.EINVAL
                self.write(14, struct.pack('=IH', request, error))


def broker_usb(device, decoder, identity, lib, handle, number, incoming, send, mode):
    if mode not in {'charge', 'proxy'}:
        raise ValueError('Modo exclusivo inválido.')

    def control(request_type, request, value, length):
        data = (C.c_ubyte * length)()
        count = lib.libusb_control_transfer(handle, request_type, request,
                                            value, number, data, length, 1000)
        if count < 0:
            raise OSError('Não foi possível ler o DualSense: libusb ' + str(count))
        return bytes(data[:count])

    # Read only well-known immutable feature reports. No calibration writes.
    features = {}
    descriptor = None
    virtual = None
    config = None
    applied_mode = None
    last_status = 0
    last_output = bytes([2]) + bytes(62)
    game_triggers = [trigger_effect('off'), trigger_effect('off')]
    identify_until = 0
    blink_at = 0
    test_until = 0
    virtual_since = 0
    packets = outputs = rejected = 0
    last_applied = None
    buffer = b''
    monitor = InputMonitor()

    def game_output(packet):
        nonlocal last_output, outputs, rejected, last_applied
        try:
            filtered = bytearray(filter_output(packet, config))
        except ValueError:
            rejected += 1
            return False
        last_output = filter_output(packet)
        for index, offset in enumerate((11,22)):
            if last_output[1] & (4 << index):
                game_triggers[index] = last_output[offset:offset+11]
        if time.monotonic() < identify_until:
            filtered[2] &= ~16
        if time.monotonic() < test_until:
            filtered[1] |= 3
            filtered[3:5] = bytes((70, 70))
        send(filtered)
        last_applied = {'rgb': list(filtered[45:48]), 'motors': list(filtered[3:5])}
        outputs += 1
        return True

    def apply_preferences():
        # Changes take effect immediately; game outputs are filtered before USB.
        report = bytearray(effects_report(config or {}))
        if not config or config.get('triggers','game') == 'game':
            report[1] |= 0x0c
            report[11:22], report[22:33] = game_triggers
        report[2] |= 2
        report[10] = 0x80 if config and config.get('vibration') == 'off' else 0
        send(report)

    try:
        while True:
            if mode != applied_mode:
                if virtual:
                    virtual.close()
                    virtual = None
                if mode == 'charge':
                    send(charge_report())
                else:
                    if descriptor is None:
                        descriptor = control(0x81, 6, 0x2200, 4096)
                        for report_id, size in FEATURE_LENGTHS.items():
                            value = control(0xa1, 1, 0x0300 | report_id, size)
                            if len(value) != size or value[0] != report_id:
                                raise OSError('Resposta de identificação/calibração inválida.')
                            features[report_id] = value
                        identity = 'hid:' + ':'.join(f'{b:02x}' for b in features[9][1:7][::-1])
                    apply_preferences()
                    virtual = VirtualDualSense(descriptor,
                                               int((device/'idProduct').read_text(), 16),
                                               int((device/'bcdDevice').read_text(), 16), identity)
                    virtual_since = time.monotonic()
                applied_mode = mode
                identify_until = test_until = 0
                print(json.dumps({'event': 'mode', 'mode': mode, 'identity': identity}), flush=True)
            if select.select([sys.stdin.fileno()], [], [], 0)[0]:
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > 8192:
                    raise ValueError('Comando muito longo.')
                stop = False
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise ValueError('Comando inválido.')
                    if 'monitor' in request:
                        monitor.request(request['monitor'], time.monotonic())
                        if request['monitor']:
                            monitor.load_calibration(lambda:features.get(5) or control(0xa1,1,0x0305,41))
                    if request.get('stop'):
                        stop = True
                        break
                    if 'mode' in request:
                        if request['mode'] not in {'charge', 'proxy'}:
                            raise ValueError('Modo inválido.')
                        mode = request['mode']
                    if 'config' in request:
                        new_config = request['config']
                        if new_config is not None:
                            effects_report(new_config)
                        if new_config != config:
                            config = new_config
                            if applied_mode == 'proxy':
                                apply_preferences()
                    if request.get('identify'):
                        identify_until = time.monotonic() + 2
                        blink_at = 0
                    if request.get('test') and applied_mode == 'proxy':
                        test_until = time.monotonic() + 1
                        test = bytearray(effects_report(config or {}, test=True))
                        test[2] |= 2
                        test[10] = 0
                        send(test)
                if stop:
                    break
                if mode != applied_mode:
                    continue
            now = time.monotonic()
            if test_until and now >= test_until:
                test_until = 0
                # End app tests even when games send no further output.
                send(effects_report({'vibration': 'off'}))
                apply_preferences()
            if identify_until and now >= blink_at:
                blink = bytearray(63)
                blink[0] = 2
                blink[2] = 16
                blink[44] = 31 if now < identify_until and int(now * 4) % 2 else 0
                if now >= identify_until:
                    identify_until = 0
                    if mode == 'proxy':
                        blink[44] = last_output[44]
                send(blink)
                blink_at = now + .25
            if virtual:
                virtual.drain(features, game_output)
                if not virtual.started and now - virtual_since > 8:
                    raise OSError('O Linux não iniciou o controle virtual. Use Acesso direto.')
            data = (C.c_ubyte * 64)()
            transferred = C.c_int()
            result = lib.libusb_interrupt_transfer(handle, incoming, data, 64,
                                                    C.byref(transferred), 4 if virtual else 100)
            if result == -7:
                continue
            if result < 0:
                raise OSError('Conexão USB interrompida: ' + str(result))
            packet = bytes(data[:transferred.value])
            if len(packet) != 64 or packet[0] != 1:
                continue
            packets += 1
            if virtual:
                virtual.input(packet)  # Preserve buttons, gyro and touchpad byte for byte.
            telemetry = monitor.feed(packet, now)
            if telemetry:
                print(json.dumps(telemetry), flush=True)
            reading = decoder(packet)
            if reading and now - last_status >= 1:
                reading.update(raw_status=packet[53], sequence=packet[7],
                               sensor_timestamp=int.from_bytes(packet[28:32], 'little'),
                               connection_flags=packet[54])
                if mode == 'charge':
                    reading['charge_profile'] = CHARGE_PROFILE
                print(json.dumps({'reading': reading, 'identity': identity,
                                  'exclusive': True, 'mode': mode, 'broker': BROKER_VERSION,
                                  'virtual_started': bool(virtual and virtual.started),
                                  'packets': packets, 'outputs': outputs, 'rejected': rejected,
                                  'last_applied': last_applied}), flush=True)
                last_status = now
    finally:
        if virtual:
            virtual.close()
        try:
            # Stop transient rumble/triggers before returning the physical device.
            neutral = charge_report()
            neutral[10] = 0
            send(neutral)
        except OSError:
            pass
