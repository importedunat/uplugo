# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from charge_watch import ChargeWatch, MAX_SESSIONS, MAX_SAMPLES
import i18n


class ChargeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)/'history.json'
        self.watch = ChargeWatch(self.path)
        previous = i18n.language(); i18n.set_language('pt-BR')
        self.addCleanup(i18n.set_language, previous)

    def feed(self, at, capacity=25, status='Charging', connection='first', port='1-2'):
        self.watch.observe('one', connection, dict(capacity=capacity, status=status), at, port=port)

    def test_reconnection_keeps_old_period_without_assigning_gap_gain(self):
        self.feed(1000); self.feed(1010,35)
        self.feed(5000,75,connection='second',port='3-4')
        current,previous=self.watch.sessions('one',5000)
        self.assertEqual((current['baseline'],current['capacity'],current['port']),(75,75,'3-4'))
        self.assertEqual((previous['baseline'],previous['capacity'],previous['seen']-previous['started']),(25,35,10))
        self.assertEqual(previous['port'],'1-2')
        self.assertEqual(previous['reason'],'connection')
        self.assertNotIn('Aumento observado',self.watch.describe('one',5000))
        self.assertFalse(self.watch.sessions('one',5007)[0]['fresh'])
        self.assertEqual(self.watch.sessions('one',8000)[0]['seen'],5000)
        self.watch.flush();loaded=ChargeWatch(self.path)
        self.assertEqual(loaded.sessions('one',5000),self.watch.sessions('one',5000))
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    def test_gap_and_clock_reset_end_at_last_actual_report(self):
        self.feed(1000);self.feed(1010,35);self.feed(1030,45)
        self.assertEqual(self.watch.sessions('one',1030)[1]['reason'],'gap')
        self.feed(900,55)
        sessions=self.watch.sessions('one',900)
        self.assertEqual(sessions[1]['reason'],'clock')
        self.assertEqual(sessions[1]['seen'],1030)
        self.assertEqual(sessions[0]['baseline'],55)
        self.assertFalse(self.watch.sessions('one',899)[0]['fresh'])
        self.assertIn('Sem leitura',self.watch.describe('one',899))

    def test_time_spent_playing_is_not_time_waiting_for_charge(self):
        with patch.object(self.watch,'flush'):
            for at in range(1000,4001,10):self.feed(at,status='Discharging')
            self.feed(4010,status='Charging')
            self.assertIn('há 0 min',self.watch.describe('one',4010))
            self.feed(4020,35)
            self.assertIn('25% → 35%',self.watch.describe('one',4020))
            self.feed(4030,35,'Discharging')
            self.assertIn('não informa carga',self.watch.describe('one',4030))
            self.feed(4040,35)
            self.assertNotIn('Aumento observado',self.watch.describe('one',4040))
            self.assertEqual([s['status'] for s in self.watch.entries['one']['samples'][-4:]],
                             ['Charging','Charging','Discharging','Charging'])

    def test_entering_charge_does_not_reuse_a_change_from_play(self):
        self.feed(1000,25,'Discharging')
        self.feed(1010,35,'Charging')
        self.assertNotIn('Aumento observado',self.watch.describe('one',1010))
        self.feed(1020,45,'Charging')
        self.assertIn('35% → 45%',self.watch.describe('one',1020))

    def test_legacy_migration_keeps_readings_and_infers_port_without_writing(self):
        old={'one':{'connection':'boot-id:3-2.1:7','started':1000,'seen':1010,'changed':1010,
                    'baseline':25,'capacity':35,'status':'Charging','samples':[
                        {'at':1000,'capacity':25,'status':'Discharging'},
                        {'at':1010,'capacity':35,'status':'Charging'}]}}
        self.path.write_text(json.dumps(old));before=self.path.read_bytes()
        loaded=ChargeWatch(self.path)
        self.assertEqual(loaded.sessions('one',1010)[0]['port'],'3-2.1')
        self.assertEqual(loaded.entries['one']['charging_started'],1010)
        self.assertEqual(self.path.read_bytes(),before)
        loaded.observe('one','new',{'capacity':55,'status':'Charging'},1020,port='3-2.2')
        self.assertEqual(loaded.sessions('one',1020)[1]['capacity'],35)

    def test_malformed_nested_history_is_filtered_and_valid_entries_survive(self):
        self.feed(1000)
        entry=self.watch.entries['one']
        entry['sessions']=[None,[],{'started':float('inf')},dict(entry,port='/private',reason=[])]
        entry['samples']=[None,{'at':float('nan'),'capacity':30},
                          {'at':1000,'capacity':25,'status':[],'profile':{}},
                          {'at':1001,'capacity':25}]
        entry['increase']={'at':1000,'before':-1,'after':500}
        self.path.write_text(json.dumps({'one':entry}))
        loaded=ChargeWatch(self.path)
        self.assertEqual(len(loaded.entries['one']['sessions']),1)
        self.assertEqual(loaded.entries['one']['sessions'][0]['port'],'')
        self.assertEqual(len(loaded.entries['one']['samples']),1)
        self.assertNotIn('increase',loaded.entries['one'])
        self.assertIn('Aguardando',loaded.describe('one',1000))

    def test_limits_and_independent_controllers(self):
        with patch.object(self.watch,'flush'):
            for at in range(1000,1000+60*1600,10):self.feed(at)
            self.assertEqual(len(self.watch.entries['one']['samples']),MAX_SAMPLES)
            for at in range(100000,103000,30):self.feed(at)
        self.assertEqual(len(self.watch.sessions('one',102970)),MAX_SESSIONS+1)
        self.watch.observe('two','other',dict(capacity=100,status='Full'),102970,port='9-1')
        self.assertEqual(len(self.watch.sessions('two',102970)),1)
        self.assertEqual(self.watch.sessions('one',102970)[0]['capacity'],25)

    def test_invalid_reports_do_not_change_history(self):
        self.feed(1000);before=json.dumps(self.watch.entries)
        for value in (None,True,-1,101,'35'):
            self.feed(1001,capacity=value)
        for value in (None,[],{},'unknown'):
            self.feed(1001,status=value)
        for value in (float('nan'),float('inf'),-1,1e30):self.feed(value)
        self.assertEqual(json.dumps(self.watch.entries),before)

    def test_failed_save_keeps_previous_file_and_removes_temporary(self):
        self.feed(1000);before=self.path.read_bytes()
        self.feed(1001,35)
        with patch('charge_watch.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.watch.flush()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(self.path.parent.glob('*.tmp')),[])

    def test_note_follows_exact_period_during_reconnection_and_clock_reset(self):
        self.feed(1000)
        original=self.watch.sessions('one',1000)[0]['session_id']
        self.feed(1000,connection='second',port='3-4')
        self.watch.annotate('one',original,'Cabo curto, porta traseira')
        current,old=self.watch.sessions('one',1000)
        self.assertEqual(old['note'],'Cabo curto, porta traseira')
        self.assertEqual(current['note'],'')
        self.assertNotEqual(current['session_id'],original)
        self.feed(900,connection='second',port='3-4')
        self.assertEqual(self.watch.sessions('one',900)[0]['note'],'')
        self.watch.flush();loaded=ChargeWatch(self.path)
        self.assertEqual(loaded.sessions('one',900),self.watch.sessions('one',900))
        loaded.annotate('one',original,'')
        self.assertEqual(loaded.sessions('one',900)[-1]['note'],'')

    def test_note_save_failure_keeps_readings_previous_note_and_file(self):
        self.feed(1000)
        sid=self.watch.sessions('one',1000)[0]['session_id']
        self.watch.annotate('one',sid,'Original')
        before=self.path.read_bytes();self.feed(1001,35)
        with patch('charge_watch.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.watch.annotate('one',sid,'Draft')
        self.assertEqual(self.path.read_bytes(),before)
        period=self.watch.sessions('one',1001)[0]
        self.assertEqual((period['note'],period['capacity']),('Original',35))
        self.watch.annotate('one',sid,'Retry')
        self.assertEqual(ChargeWatch(self.path).sessions('one',1001)[0]['note'],'Retry')

    def test_expired_or_other_controller_period_cannot_be_annotated(self):
        self.feed(1000);sid=self.watch.sessions('one',1000)[0]['session_id']
        self.watch.observe('two','other',dict(capacity=100,status='Full'),1000,port='9-1')
        with self.assertRaises(LookupError):self.watch.annotate('two',sid,'wrong')
        with patch.object(self.watch,'flush'):
            for at in range(2000,5000,30):self.feed(at)
        before=json.dumps(self.watch.entries)
        with self.assertRaises(LookupError):self.watch.annotate('one',sid,'expired')
        self.assertEqual(json.dumps(self.watch.entries),before)

    def test_notes_are_bounded_and_duplicate_legacy_ids_are_repaired_without_write(self):
        self.feed(1000);entry=self.watch.entries['one'];sid=entry['session_id']
        for note in ('x'*161,'a\nb','\x00',[],None):
            with self.assertRaises(ValueError):self.watch.annotate('one',sid,note)
        entry['sessions']=[dict(entry,note='x'*161)]
        self.path.write_text(json.dumps(self.watch.entries));before=self.path.read_bytes()
        loaded=ChargeWatch(self.path);current,old=loaded.sessions('one',1000)
        self.assertNotEqual(current['session_id'],old['session_id'])
        self.assertEqual(old['note'],'')
        self.assertEqual(self.path.read_bytes(),before)
