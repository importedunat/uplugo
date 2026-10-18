# SPDX-License-Identifier: GPL-3.0-only
"""Protocol/lifecycle regressions; does not open real controllers."""
import ast
import struct
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import game_profiles
from build_helper import helper_source

BASE = Path(__file__).resolve().parent
ns = {'__file__': str(BASE/'dualsense.py'), '__name__': 'test_helper'}
source = helper_source()
exec(source[:source.rfind('\ntry:\n    if len(sys.argv)')], ns)


class ProtocolTests(unittest.TestCase):
    def packet(self):
        p = bytearray(63)
        p[0] = 2
        p[1] = 0x0e  # v2 rumble + both adaptive triggers
        p[2] = 0x0c  # RGB + firmware LED release
        p[3:5] = bytes((90, 180))
        p[5:9] = bytes((10, 20, 30, 40))  # audio
        p[11:22] = bytes(range(11))
        p[22:33] = bytes(range(20, 31))
        p[39] = 7  # v2 rumble + reset/brightness
        p[45:48] = bytes((255, 0, 0))
        return p

    def test_passthrough_exact_native_fields(self):
        p = self.packet()
        self.assertEqual(ns['filter_output'](p), p)
        out = ns['filter_output'](p, {'rgb': [0, 255, 0], 'vibration': 'game'})
        self.assertEqual(out[5:39], p[5:39])
        self.assertEqual(out[45:48], bytes((0, 255, 0)))
        self.assertEqual(out[2] & 8, 0)
        self.assertEqual(out[39] & 3, 0)
        self.assertEqual(out[39] & 4, 4)  # v2 remains enabled

    def test_off_blocks_v1_v2_and_audio_haptics(self):
        for v2 in (0, 4):
            p = self.packet();p[39] = v2
            out = ns['filter_output'](p, {'vibration': 'off'})
            self.assertEqual(out[3:5], b'\0\0')
            self.assertEqual(out[10] & 0x80, 0x80)
            self.assertEqual(out[11:33], p[11:33])

    def test_reduced_rumble_preserves_trigger_power(self):
        p = self.packet();p[37] = 0x70
        out = ns['filter_output'](p, {'vibration': 'low'})
        self.assertEqual(out[3:5], bytes((30, 60)))
        self.assertEqual(out[37], 0x73)

    def test_invalid_commands_and_padding(self):
        self.assertEqual(len(ns['filter_output'](self.packet()[:48])), 63)
        for p in (b'', b'\x80' + bytes(62), b'\x02' + bytes(80)):
            with self.assertRaises(ValueError):ns['filter_output'](p)
        with self.assertRaises(ValueError):
            ns['filter_output'](self.packet(), {'rgb': [999, 0, 0]})

    def events(self, events):
        virtual = ns['VirtualDualSense'].__new__(ns['VirtualDualSense'])
        virtual.fd = 80;virtual.started = False
        replies = [];outputs = []
        virtual.write = lambda kind, data=b'': replies.append((kind, data))
        reads = iter(events)
        def read(*args):
            try:return next(reads)
            except StopIteration:raise BlockingIOError()
        with patch.object(ns['os'], 'read', read):
            virtual.drain({9: bytes([9]) + bytes(19)}, lambda p: outputs.append(p) or True)
        return virtual, replies, outputs

    def test_feature_replies_preserve_id_and_block_writes(self):
        events = [struct.pack('=IIBB', 9, 55, 9, 0),
                  struct.pack('=IIBB', 9, 56, 0x80, 0),
                  struct.pack('=IIBBH', 13, 57, 0x80, 0, 3) + b'\x80\x01\x01']
        _, replies, outputs = self.events(events)
        self.assertEqual(struct.unpack_from('=IHH', replies[0][1]), (55, 0, 20))
        self.assertNotEqual(struct.unpack_from('=IHH', replies[1][1])[1], 0)
        self.assertNotEqual(struct.unpack_from('=IH', replies[2][1])[1], 0)
        self.assertEqual(outputs, [])

    def test_output_interrupt_and_control_channels(self):
        p = bytes(self.packet())
        interrupt = struct.pack('=I', 6) + p.ljust(4096, b'\0') + struct.pack('=HB', len(p), 1)
        control = struct.pack('=IIBBH', 13, 60, 2, 1, len(p)) + p
        _, replies, outputs = self.events([interrupt, control])
        self.assertEqual(outputs, [p, p])
        self.assertEqual(replies, [(14, struct.pack('=IH', 60, 0))])

    def test_create_abi_and_descriptor(self):
        events = []
        with patch.object(ns['os'], 'open', return_value=80), \
                patch.object(ns['os'], 'write', side_effect=lambda fd,e: events.append(e) or len(e)), \
                patch.object(ns['os'], 'close') as close:
            v = ns['VirtualDualSense'](b'\x05\x01', 0x0ce6, 0x100, 'hid:11:22:33:44:55:66')
            v.input(bytes([1])+bytes(63));v.close()
            close.assert_called_once_with(80)
        self.assertEqual(struct.unpack_from('=I',events[0])[0],11)
        self.assertEqual(struct.unpack_from('=HHII', events[0],260), (2,3,0x54c,0xce6))
        self.assertEqual(events[0][280:], b'\x05\x01')
        self.assertEqual(struct.unpack_from('=IH', events[1]), (12,64))


class ProfileTests(unittest.TestCase):
    def test_support_packages_are_not_listed_as_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);apps=root/'steamapps';apps.mkdir()
            names=['Proton 11.0','Proton 9.0','Proton Experimental','Proton Hotfix',
                   'Steam Linux Runtime 3.0 (sniper)','Steam Linux Runtime 4.0',
                   'Steamworks Common Redistributables','Proton Pulse','It Takes Two']
            for number,name in enumerate(names,1):
                (apps/f'appmanifest_{number}.acf').write_text(f'"appid" "{number}" "name" "{name}"')
            self.assertEqual(game_profiles.installed_games([root]),{'9':'It Takes Two','8':'Proton Pulse'})

    def test_installed_names_from_extra_steam_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'Steam';other=Path(tmp)/'Other games'
            (root/'steamapps').mkdir(parents=True);(other/'steamapps').mkdir(parents=True)
            (root/'steamapps/libraryfolders.vdf').write_text('"path" "'+str(other)+'"')
            (other/'steamapps/appmanifest_123.acf').write_text('"AppState" { "appid" "123" "name" "Game Name" }')
            self.assertEqual(game_profiles.installed_games([root]),{'123':'Game Name'})

    def test_explicit_matching(self):
        profiles=game_profiles.parse_profiles('123\nGame.exe\ngame.EXE\n')
        self.assertEqual(profiles,['123','Game.exe'])
        self.assertEqual(game_profiles.matching_game(profiles,[('123',{'game2.exe'})]),'123')
        self.assertEqual(game_profiles.matching_game(profiles,[(None,{'game.exe'})]),'Game.exe')
        self.assertIsNone(game_profiles.matching_game(profiles,[(None,{'mygame.exe'})]))
        for value in ('0','*','game.exe; rm','/path/game.exe'):
            with self.assertRaises(ValueError):game_profiles.parse_profiles(value)

    def test_debounce_and_charge_priority(self):
        d=game_profiles.GameDetector()
        self.assertIsNone(d.update('123'))
        self.assertEqual(d.update('123'),'123')
        self.assertEqual(d.update(None),'123')
        self.assertEqual(d.update(None),'123')
        self.assertIsNone(d.update(None))
        self.assertEqual(game_profiles.effective_mode('charge','123'),'charge')
        self.assertEqual(game_profiles.effective_mode('proxy','123'),'play')
        self.assertEqual(game_profiles.effective_mode('proxy',None),'proxy')


if __name__ == '__main__':
    unittest.main()
