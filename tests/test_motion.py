# SPDX-License-Identifier: GPL-3.0-only
import math
import unittest
from unittest.mock import patch
from motion_state import MotionCalibration,read_motion_feature
from motion_trace import MotionTrace,motion_demo
from input_state import InputMonitor
from tests.test_input_state import report


def calibration():
    data=bytearray(41);data[0]=5
    # Nonzero biases and unequal sensitivities catch incorrect nominal scaling
    # and subtracting the gyro bias, which the DualSense driver does not do.
    values={1:100,3:-200,5:50,7:10100,9:-9900,11:5800,13:-6200,
            15:3050,17:-2950,19:500,21:500,
            23:8202,25:-8182,27:8100,29:-7900,31:8011,33:-7988}
    for offset,value in values.items():data[offset:offset+2]=value.to_bytes(2,'little',signed=True)
    return bytes(data)


def motion_report(gyro=(10000,-6000,3000),accel=(8202,100,12),ticks=123456):
    data=report()
    for offset,values in ((16,gyro),(22,accel)):
        for index,value in enumerate(values):data[offset+2*index:offset+2*index+2]=value.to_bytes(2,'little',signed=True)
    data[28:32]=ticks.to_bytes(4,'little');return data


class MotionTests(unittest.TestCase):
    def test_factory_scaling_signed_layout_and_gyro_bias_convention(self):
        sample=MotionCalibration(calibration()).decode(motion_report())
        self.assertEqual(sample['gyro_dps'],[500,-500,500])
        self.assertEqual(sample['accel_g'],[1,0,0])
        self.assertEqual(sample['sensor_ticks'],123456)
        self.assertEqual(sample['gyro_raw'],[10000,-6000,3000])

    def test_negative_gravity_and_int16_extremes(self):
        cal=MotionCalibration(calibration())
        sample=cal.decode(motion_report((-32768,32767,-1),(-8182,-7900,-7988)))
        self.assertAlmostEqual(sample['gyro_dps'][0],-1638.4)
        self.assertEqual(sample['accel_g'][:2],[-1,-1])
        self.assertAlmostEqual(sample['accel_g'][2],-16000/15999)
        self.assertTrue(all(math.isfinite(x) for x in sample['gyro_dps']+sample['accel_g']))

    def test_missing_wrong_short_and_zero_calibration_never_guess_units(self):
        for data in (None,b'',b'\x04'+calibration()[1:],calibration()[:-1],b'\x05'+bytes(40)):
            sample=MotionCalibration(data).decode(motion_report())
            self.assertIsNone(sample['gyro_dps']);self.assertIsNone(sample['accel_g'])
            self.assertEqual(sample['accel_raw'],[8202,100,12])
        for data in (None,b'',bytes(64),bytes(78)):
            self.assertIsNone(MotionCalibration(calibration()).decode(data))

    def test_one_invalid_sensor_preserves_the_other_sensor_units(self):
        data=bytearray(calibration());data[23:27]=bytes(4)
        sample=MotionCalibration(data).decode(motion_report())
        self.assertEqual(sample['gyro_dps'],[500,-500,500]);self.assertIsNone(sample['accel_g'])
        data=bytearray(calibration());data[19:23]=bytes(4)
        sample=MotionCalibration(data).decode(motion_report())
        self.assertIsNone(sample['gyro_dps']);self.assertEqual(sample['accel_g'],[1,0,0])

    def test_feature_ioctl_is_one_fixed_read_and_rejects_short_reply(self):
        def ioctl(fd,request,data,mutate):
            self.assertEqual(fd,42);self.assertEqual(request,0xc0294807)
            self.assertTrue(mutate);self.assertEqual(data,bytearray([5])+bytearray(40))
            data[:]=calibration();return 41
        with patch('fcntl.ioctl',side_effect=ioctl):self.assertEqual(read_motion_feature(42),calibration())
        with patch('fcntl.ioctl',return_value=12):self.assertIsNone(read_motion_feature(42))

    def test_subscription_loads_calibration_once_and_keeps_lease_limit(self):
        monitor=InputMonitor()
        with patch('motion_state.read_motion_feature',return_value=calibration()) as reader:
            for _ in range(3):monitor.load_calibration(reader)
        reader.assert_called_once()
        self.assertIsNone(monitor.feed(motion_report(),1))
        monitor.request(True,1)
        self.assertEqual(monitor.feed(motion_report(),1)['input']['motion']['accel_g'],[1,0,0])
        self.assertIsNone(monitor.feed(motion_report(),1.01))
        self.assertIsNone(monitor.feed(motion_report(),4.01))
        monitor=InputMonitor()
        with patch('motion_state.read_motion_feature',side_effect=OSError('unavailable')) as reader:
            monitor.load_calibration(reader);monitor.load_calibration(reader)
        reader.assert_called_once();monitor.request(True,1)
        self.assertIsNone(monitor.feed(motion_report(),1)['input']['motion']['gyro_dps'])

    def test_trace_memory_time_limit_and_missing_data(self):
        trace=MotionTrace()
        for frame in range(10000):trace.observe(motion_demo(frame),frame/100)
        self.assertLessEqual(len(trace.samples),301)
        self.assertLessEqual(trace.samples[-1][0]-trace.samples[0][0],10)
        trace.observe(None,101);self.assertIsNone(trace.current);self.assertFalse(trace.samples)

    def test_trace_stall_wrap_reset_time_gap_and_recovery(self):
        trace=MotionTrace();sample=motion_demo(1);sample['sensor_ticks']=2**32-10
        trace.observe(sample,10)
        sample=dict(sample,sensor_ticks=5);trace.observe(sample,10.1)
        self.assertEqual(len(trace.samples),2)  # Natural 32-bit wrap.
        for now in (10.3,10.5,10.7):trace.observe(sample,now)
        self.assertTrue(trace.stalled);self.assertIsNone(trace.current);self.assertFalse(trace.samples)
        trace.observe(motion_demo(2),10.8);self.assertFalse(trace.stalled);self.assertEqual(len(trace.samples),1)
        trace.observe(motion_demo(1),10.9);self.assertEqual(len(trace.samples),1)  # Sensor reset.
        trace.observe(motion_demo(2),12);self.assertEqual(len(trace.samples),1)  # Missing samples.
        trace.observe(motion_demo(3),11);self.assertEqual(len(trace.samples),1)  # Host clock reset.

    def test_trace_rejects_invalid_vectors_and_does_not_mix_calibration_states(self):
        trace=MotionTrace();trace.observe(motion_demo(1),10)
        for index,value in enumerate(([float('nan'),0,0],[True,0,0],[1,2],[float('inf'),0,0],[10**12,0,0])):
            sample=motion_demo(index+2);sample['gyro_dps']=value
            trace.observe(sample,10.1+index*.1)
            self.assertIsNone(trace.current[0]);self.assertIsNotNone(trace.current[1])
        trace.observe(motion_demo(9),10.7);self.assertEqual(len(trace.samples),1)
        sample=motion_demo(10);sample['sensor_ticks']=-1;trace.observe(sample,10.8)
        self.assertFalse(trace.samples);self.assertIsNone(trace.current)
