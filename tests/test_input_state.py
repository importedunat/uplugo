# SPDX-License-Identifier: GPL-3.0-only
import unittest
from input_state import decode_input, InputMonitor, BUTTON_NAMES, EDGE_BUTTON_NAMES


def report():
    packet = bytearray(64)
    packet[0] = 1
    packet[1:5] = bytes([128]*4)
    packet[8] = 8  # Neutral hat, not up.
    packet[33] = packet[37] = 0x80  # Inactive touch contacts.
    return packet


def touch(packet, slot, contact, x, y):
    offset = 33 + slot*4
    packet[offset:offset+4] = bytes((contact, x & 255, (x >> 8) | ((y & 15) << 4), y >> 4))


class InputTests(unittest.TestCase):
    def test_touch_layout_shared_nibbles_and_click_are_independent(self):
        packet=report()
        touch(packet,0,0,0x456,0x321)
        touch(packet,1,127,1919,1079)
        state=decode_input(packet)
        self.assertEqual(state['touches'],[{'slot':0,'id':0,'x':1110,'y':801},
                                            {'slot':1,'id':127,'x':1919,'y':1079}])
        self.assertEqual(state['touch_invalid'],0)
        self.assertEqual(state['buttons'],[])
        packet[10]=2
        self.assertEqual(decode_input(packet)['buttons'],['Touchpad'])
        self.assertEqual(decode_input(packet)['touches'],state['touches'])

    def test_touch_release_ignores_stale_coordinates_and_accepts_origin(self):
        packet=report()
        touch(packet,0,127,1500,900)
        touch(packet,1,0x80,4095,4095)
        self.assertEqual(len(decode_input(packet)['touches']),1)
        packet[33]|=0x80
        self.assertEqual(decode_input(packet)['touches'],[])
        self.assertEqual(decode_input(packet)['touch_invalid'],0)
        touch(packet,0,0,0,0)
        self.assertEqual(decode_input(packet)['touches'],[{'slot':0,'id':0,'x':0,'y':0}])

    def test_out_of_range_touch_is_reported_without_faking_edge_position(self):
        for x,y in ((1920,0),(0,1080),(4095,4095)):
            with self.subTest(x=x,y=y):
                packet=report();touch(packet,0,1,x,y);touch(packet,1,2,100,200)
                state=decode_input(packet)
                self.assertEqual(state['touch_invalid'],1)
                self.assertEqual(state['touches'],[{'slot':1,'id':2,'x':100,'y':200}])

    def test_touch_subscription_expiry_does_not_repeat_old_contact(self):
        monitor=InputMonitor();packet=report();touch(packet,0,5,700,350)
        monitor.request(True,10)
        self.assertEqual(len(monitor.feed(packet,10)['input']['touches']),1)
        packet[33]|=0x80
        self.assertEqual(monitor.feed(packet,10.04)['input']['touches'],[])
        self.assertIsNone(monitor.feed(packet,13))
        monitor.request(True,14)
        self.assertEqual(monitor.feed(packet,14)['input']['touches'],[])

    def test_neutral_invalid_and_axes(self):
        self.assertEqual(decode_input(report())['buttons'], [])
        for packet in (b'', bytes(64), bytes([0x31])+bytes(63), bytes([1])+bytes(78)):
            self.assertIsNone(decode_input(packet))
        packet=report();packet[1:7]=bytes([0,255,127,128,70,255])
        self.assertEqual(decode_input(packet)['sticks'], [0,255,127,128])
        self.assertEqual(decode_input(packet)['triggers'], [70,255])

    def test_each_button_has_one_mapping(self):
        for index,name in enumerate(BUTTON_NAMES[4:]):
            packet=report()
            byte,bit=(8,index+4) if index<4 else (9,index-4) if index<12 else (10,index-12)
            packet[byte]|=1<<bit
            self.assertEqual(decode_input(packet)['buttons'],[name])
        for index,name in enumerate(EDGE_BUTTON_NAMES):
            packet=report();packet[10]=1<<(index+4)
            self.assertEqual(decode_input(packet)['buttons'],[name])

    def test_hat_diagonals_and_reserved_values(self):
        for hat, expected in enumerate([['↑'],['↑','→'],['→'],['→','↓'],['↓'],['↓','←'],['←'],['←','↑'],[]]):
            packet=report();packet[8]=hat
            self.assertEqual(decode_input(packet)['buttons'],expected)
        packet[8]=15
        self.assertEqual(decode_input(packet)['buttons'],[])

    def test_telemetry_opt_in_lease_stop_and_short_presses(self):
        monitor=InputMonitor();packet=report()
        self.assertIsNone(monitor.feed(packet,10))
        monitor.request(True,10)
        self.assertEqual(monitor.feed(packet,10)['input']['observed'],[])
        packet[9]=1
        self.assertIsNone(monitor.feed(packet,10.001))
        packet[9]=0
        state=monitor.feed(packet,10.04)['input']
        self.assertEqual(state['buttons'],[])
        self.assertEqual(state['observed'],['L1'])
        self.assertEqual(monitor.feed(packet,10.08)['input']['observed'],[])
        self.assertIsNone(monitor.feed(packet,13))
        monitor.request(True,14)
        self.assertIsNotNone(monitor.feed(packet,14))
        monitor.request(False,14.01)
        self.assertIsNone(monitor.feed(packet,14.1))
        with self.assertRaises(ValueError):monitor.request('true',15)
