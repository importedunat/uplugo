# SPDX-License-Identifier: GPL-3.0-only
import unittest
from analog_test import AnalogSession, percent


def rested():
    session = AnalogSession(); session.observe([128]*4, 0)
    assert session.start_rest(0)
    for index in range(126): session.observe([127,128,129,126], .04*(index+1))
    assert session.phase == 'ready'
    return session, 5.04


class AnalogTests(unittest.TestCase):
    def test_no_collection_before_explicit_start_or_after_reset(self):
        session=AnalogSession()
        self.assertFalse(session.start_rest(0))
        for index in range(200): session.observe([128]*4,index*.04)
        self.assertEqual(session.rest.count,0)
        self.assertEqual(session.travel.count,0)
        self.assertTrue(session.start_rest(7.96))
        session.observe([0]*4,8);self.assertEqual(session.rest.count,1)
        session.reset();self.assertEqual(session.phase,'idle')
        self.assertEqual(session.rest.count,0)
        self.assertTrue(all(not trail for trail in session.trails))

    def test_rest_means_all_axes_and_duration_start_on_first_new_sample(self):
        session,now=rested()
        self.assertAlmostEqual(session.rest.seconds,5)
        self.assertEqual(session.rest.count,126)
        self.assertEqual(session.rest.means,[percent(v) for v in (127,128,129,126)])
        session.observe([0]*4,now+.04)
        self.assertEqual(session.rest.count,126)  # Ready stage is frozen.
        self.assertEqual(session.travel.count,0)

    def test_reading_gap_interrupts_and_requires_a_new_explicit_start(self):
        session=AnalogSession();session.observe([128]*4,0);session.start_rest(0)
        session.observe([128]*4,.04);session.observe([128]*4,.6)
        self.assertEqual(session.phase,'interrupted')
        self.assertEqual(session.rest.count,0)
        session.observe([128]*4,.64)
        self.assertEqual(session.phase,'interrupted')
        self.assertTrue(session.start_rest(.64))
        session.observe([128]*4,.68)
        self.assertEqual(session.rest.seconds,0)

    def test_duplicate_and_bad_samples_cannot_inflate_a_measurement(self):
        session=AnalogSession();session.observe([128]*4,0);session.start_rest(0)
        session.observe([128]*4,.04)
        for index in range(100): session.observe([0]*4,.04)
        self.assertEqual(session.rest.count,1)
        for values,now in (([128]*3,.08),([False]*4,.08),([256]*4,.08),([128]*4,float('nan'))):
            session.observe(values,now)
            self.assertIsNone(session.values)
            self.assertEqual(session.rest.count,0)
        session.observe([128]*4,.2);session.start_rest(.2)
        session.observe([128]*4,.1)
        self.assertEqual(session.phase,'interrupted')

    def test_travel_preserves_raw_range_and_has_bounded_traces(self):
        session,now=rested();self.assertTrue(session.start_travel(now))
        for values in ([0,128,128,0],[255,128,128,255],[128,0,0,128],[128,255,255,128]):
            now+=.04;session.observe(values,now)
        for stick in range(2): self.assertEqual(session.travel.directions(stick),{'up','right','down','left'})
        self.assertEqual(session.travel.low,[0]*4);self.assertEqual(session.travel.high,[255]*4)
        for index in range(10000):
            now+=.04;session.observe([128]*4,now)
        self.assertEqual([len(trail) for trail in session.trails],[120,120])
        self.assertEqual(session.rest.count,126)

    def test_partial_travel_can_be_finished_without_claiming_all_directions(self):
        session,now=rested();session.start_travel(now)
        self.assertFalse(session.finish(now))
        now+=.04;session.observe([0,128,128,128],now)
        self.assertTrue(session.finish(now))
        self.assertEqual(session.travel.directions(0),{'left'})
        self.assertEqual(session.travel.directions(1),set())
        count=session.travel.count;session.observe([255]*4,now+.04)
        self.assertEqual(session.travel.count,count)
        session.interrupt()
        self.assertEqual(session.phase,'done')
        self.assertFalse(session.live(now+.1));self.assertIsNone(session.values)
        self.assertEqual(session.travel.count,count)

    def test_stale_actions_and_interruptions_do_not_combine_sessions(self):
        session,now=rested()
        self.assertFalse(session.start_travel(now+.5))
        session.interrupt()
        self.assertEqual(session.phase,'interrupted');self.assertEqual(session.rest.count,0)
        self.assertFalse(session.start_rest(now+1))
        session.observe([128]*4,now+1)
        self.assertTrue(session.start_rest(now+1))
        self.assertEqual(session.travel.count,0)

