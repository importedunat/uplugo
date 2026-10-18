# SPDX-License-Identifier: GPL-3.0-only
"""Read-only USB input telemetry. Layout: Linux hid-playstation.c.

Also embedded into the privileged helper; no external modules, files or writes
to the controller. Telemetry is enabled only by a short-lived UI subscription.
"""
from motion_state import MotionCalibration

INPUT_MONITOR_VERSION = 3
TOUCH_WIDTH, TOUCH_HEIGHT = 1920, 1080
BUTTON_NAMES = ('↑', '→', '↓', '←', '□', '×', '○', '△',
                'L1', 'R1', 'L2', 'R2', 'Create', 'Options', 'L3', 'R3',
                'PS', 'Touchpad', 'Mute')
EDGE_BUTTON_NAMES = ('Fn esquerdo', 'Fn direito', 'Traseiro esquerdo', 'Traseiro direito')


def decode_input(packet):
    if len(packet) != 64 or packet[0] != 1:
        return None
    hat = packet[8] & 15
    directions = {0: ('↑',), 1: ('↑', '→'), 2: ('→',), 3: ('→', '↓'),
                  4: ('↓',), 5: ('↓', '←'), 6: ('←',), 7: ('←', '↑')}
    buttons = list(directions.get(hat, ()))
    for byte, names, first in ((8, BUTTON_NAMES[4:8], 4),
                               (9, BUTTON_NAMES[8:16], 0),
                               (10, BUTTON_NAMES[16:], 0),
                               (10, EDGE_BUTTON_NAMES, 4)):
        buttons.extend(name for bit, name in enumerate(names, first)
                       if packet[byte] & (1 << bit))
    touches = []
    invalid = 0
    # USB report ID occupies byte 0. Each contact is four bytes; bit 7
    # marks inactive contacts whose coordinates must not be interpreted.
    # Reference: Linux hid-playstation.c, dualsense_input_report/parse_report.
    for slot, offset in enumerate((33, 37)):
        contact, low_x, shared, high_y = packet[offset:offset+4]
        if contact & 0x80:
            continue
        x = low_x | ((shared & 0x0f) << 8)
        y = (shared >> 4) | (high_y << 4)
        if x >= TOUCH_WIDTH or y >= TOUCH_HEIGHT:
            invalid += 1
            continue
        touches.append({'slot': slot, 'id': contact & 0x7f, 'x': x, 'y': y})
    return {'buttons': buttons, 'sticks': list(packet[1:5]),
            'triggers': list(packet[5:7]), 'touches': touches,
            'touch_invalid': invalid}


class InputMonitor:
    """At most 30 snapshots/s; retain quick presses between snapshots.

    A three-second lease prevents collection after a closed or crashed UI.
    Nothing is stored on disk. No effect configuration is touched.
    """
    def __init__(self):
        self.until = self.next_frame = 0
        self.seen = set()
        self.calibration = MotionCalibration()
        self.calibration_attempted = False

    def load_calibration(self, reader):
        if self.calibration_attempted:
            return
        self.calibration_attempted = True
        try:self.calibration = MotionCalibration(reader())
        except (OSError, ValueError, TypeError):pass

    def request(self, enabled, now):
        if type(enabled) is not bool:
            raise ValueError('Pedido de teste inválido.')
        if not enabled or now >= self.until:
            self.seen.clear()
        self.until = now + 3 if enabled else 0

    def feed(self, packet, now):
        if now >= self.until:
            self.seen.clear()
            return None
        state = decode_input(packet)
        if state is None:
            return None
        self.seen.update(state['buttons'])
        if now < self.next_frame:
            return None
        state['observed'] = sorted(self.seen)
        state['motion'] = self.calibration.decode(packet)
        self.seen.clear()
        self.next_frame = now + 1 / 30
        return {'input': state}
