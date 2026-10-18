# SPDX-License-Identifier: GPL-3.0-only
"""Read-only USB motion decoding using the factory feature report 0x05.

Layout and scaling reference: Linux hid-playstation.c (GPL-2.0-or-later),
Sony Interactive Entertainment. Gyro bias participates in the sensitivity
denominator; it is NOT subtracted from samples, matching the DualSense driver.
Missing/invalid calibration stays unavailable instead of guessing physical units.
"""


def motion_i16(data, offset):
    return int.from_bytes(data[offset:offset+2], 'little', signed=True)


class MotionCalibration:
    def __init__(self, report=None):
        self.gyro = self.accel = None
        if not isinstance(report, (bytes, bytearray)) or len(report) != 41 or report[0] != 5:
            return
        speed = motion_i16(report,19) + motion_i16(report,21)
        denominators = [abs(motion_i16(report,7+4*i)-motion_i16(report,1+2*i)) +
                        abs(motion_i16(report,9+4*i)-motion_i16(report,1+2*i)) for i in range(3)]
        if speed > 0 and all(value > 0 for value in denominators):
            self.gyro = [(speed, value) for value in denominators]
        pairs = [(motion_i16(report,23+4*i),motion_i16(report,25+4*i)) for i in range(3)]
        if all(plus > minus for plus, minus in pairs):
            # Positive integer division matches the kernel's midpoint rounding.
            self.accel = [(plus-(plus-minus)//2,plus-minus) for plus,minus in pairs]

    def decode(self, packet):
        if not isinstance(packet, (bytes, bytearray)) or len(packet) != 64 or packet[0] != 1:
            return None
        gyro = [motion_i16(packet,16+2*i) for i in range(3)]
        accel = [motion_i16(packet,22+2*i) for i in range(3)]
        return {'gyro_raw':gyro, 'accel_raw':accel,
                'gyro_dps': [raw*n/d for raw,(n,d) in zip(gyro,self.gyro)] if self.gyro else None,
                'accel_g': [2*(raw-bias)/span for raw,(bias,span) in zip(accel,self.accel)] if self.accel else None,
                'sensor_ticks':int.from_bytes(packet[28:32],'little')}


def read_motion_feature(fd):
    """Fixed HIDIOCGFEATURE read, never SET_REPORT or calibration writes."""
    import fcntl
    data = bytearray(41);data[0] = 5
    count = fcntl.ioctl(fd, (3 << 30) | (len(data) << 16) | (ord('H') << 8) | 7, data, True)
    return bytes(data) if count == len(data) else None
