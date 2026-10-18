# SPDX-License-Identifier: GPL-3.0-only
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import dualsense
from charge_watch import ChargeWatch
from diagnostics import snapshot
from presentation import ControllerState


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        import i18n
        previous=i18n.language();i18n.set_language("pt-BR")
        self.addCleanup(i18n.set_language,previous)

    def test_snapshot_excludes_personal_and_button_data(self):
        state=ControllerState('hid:private-serial','My private name',port='9-9',error='/home/private-user/error',
                              reading={'capacity':55,'status':'Charging','time':'private-time'})
        payload=snapshot([state],{'9-9':{'packets':123,'identity':state.identity,'input':{'buttons':['SECRET']}}},
                         {state.identity:{'connection':'private-connection','sessions':[{'port':'private-port','note':'private-cable'}],'samples':[{'at':1000,'capacity':25},{'at':2800,'capacity':55}]}},[], 'wayland')
        text=json.dumps(payload)
        for private in ('private','9-9','SECRET','hid:'):self.assertNotIn(private,text)
        self.assertEqual(payload['controllers'][0]['observed_change'],30)
        self.assertEqual(payload['controllers'][0]['observed_minutes'],30)

    def test_corrupt_settings_cache_and_history_do_not_crash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'data.json'
            for bad in ([],None,{'hid:test':None},{'hid:test':{'capacity':-1,'status':'Charging'}},'{'):
                path.write_text(bad if bad=='{' else json.dumps(bad))
                with patch.object(dualsense,'SETTINGS',path),patch.object(dualsense,'CACHE',path):
                    self.assertIsInstance(dualsense.settings(),dict)
                    self.assertEqual(dualsense.read_cache(),{})
                watch=ChargeWatch(path)
                self.assertIn('Sem leitura',watch.describe('hid:test'))

    def test_invalid_nested_preferences_preserve_valid_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'data.json'
            path.write_text(json.dumps({'names':{'bad':123,'good':'Branco'},'modes':{'bad':{},'good':'charge'},
                'effects':{'bad':[],'good':{'rgb':[0,100,255],'vibration':'low','triggers':'firm'}},
                'protection':{'play_exceptions':None,'last_actions':[]},'native_games':[{},'123']}))
            with patch.object(dualsense,'SETTINGS',path):data=dualsense.settings()
            self.assertEqual(data['names'],{'good':'Branco'})
            self.assertEqual(data['modes'],{'good':'charge'})
            self.assertEqual(data['effects']['good']['triggers'],'firm')
            self.assertEqual(data['protection']['play_exceptions'],[])
            self.assertEqual(data['native_games'],['123'])

    def test_charge_observation_gap_and_unchanged_capacity(self):
        with tempfile.TemporaryDirectory() as temp:
            watch=ChargeWatch(Path(temp)/'history.json')
            for instant in range(1000,2901,10):watch.observe('test','connection',{'capacity':25,'status':'Charging'},instant)
            self.assertIn('Sem aumento',watch.describe('test',2900))
            watch.observe('test','connection',{'capacity':35,'status':'Charging'},2910)
            self.assertIn('25% → 35%',watch.describe('test',2910))
            watch.observe('test','new-connection',{'capacity':35,'status':'Charging'},4000)
            self.assertNotIn('Aumento observado',watch.describe('test',4000))
            watch.observe('test','new-connection',{'capacity':999,'status':'Charging'},4001)
            self.assertEqual(watch.entries['test']['capacity'],35)
