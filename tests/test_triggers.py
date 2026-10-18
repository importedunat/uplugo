# SPDX-License-Identifier: GPL-3.0-only
import unittest
import dualsense
from test_broker import ns


class TriggerTests(unittest.TestCase):
    def test_game_preserves_native_trigger_commands(self):
        packet=bytearray(range(63));packet[0]=2
        result=ns['filter_output'](packet,{'triggers':'game'})
        self.assertEqual(result[11:33],packet[11:33])
        self.assertEqual(result[1],packet[1])

    def test_feedback_uses_only_declared_zones_and_strength(self):
        for preset,strength in [('light',2),('medium',4),('firm',6)]:
            effect=dualsense.trigger_effect(preset)
            self.assertEqual(len(effect),11)
            self.assertEqual(effect[0],0x21)
            mask=int.from_bytes(effect[1:3],'little')
            forces=int.from_bytes(effect[3:7],'little')
            for zone in range(10):
                self.assertEqual(bool(mask & (1<<zone)),zone>=2)
                self.assertEqual((forces>>(zone*3)) & 7,strength-1 if zone>=2 else 0)
            self.assertEqual(effect[7:],bytes(4))

    def test_override_changes_only_trigger_bytes_and_flags(self):
        packet=bytearray(range(63));packet[0]=2
        result=ns['filter_output'](packet,{'triggers':'firm'})
        self.assertEqual(result[1],packet[1]|12)
        self.assertEqual(result[11:22],dualsense.trigger_effect('firm'))
        self.assertEqual(result[22:33],result[11:22])
        for index in [0,5,6,7,8,9,34,35,36,40,41,42,43,44,48,49,50]:self.assertEqual(result[index],packet[index])

    def test_charge_releases_both_triggers(self):
        report=ns['charge_report']()
        self.assertEqual(report[11:22],dualsense.trigger_effect('off'))
        self.assertEqual(report[22:33],dualsense.trigger_effect('off'))
        self.assertEqual(report[3:5],bytes(2))

    def test_game_cannot_attenuate_custom_trigger_weight(self):
        packet=bytearray(63);packet[0]=2
        packet[2]=0x40;packet[37]=0x73  # max trigger attenuation, reduced rumble
        filtered=ns['filter_output'](packet,{'triggers':'firm'})
        self.assertEqual(filtered[37],3)
        self.assertEqual(filtered[2] & 0x40,0x40)
        self.assertEqual(filtered[11:22],dualsense.trigger_effect('firm'))
        native=ns['filter_output'](packet,{'triggers':'game'})
        self.assertEqual(native[37],0x73)

    def test_invalid_preset_never_produces_report(self):
        for value in ('raw',256,-1,None):
            with self.assertRaises(ValueError):dualsense.effects_report({'triggers':value})
