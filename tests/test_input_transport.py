# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the embedded helper loops without root or USB."""
import contextlib
import io
import json
import errno
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from test_broker import ns
from tests.test_input_state import report, touch
from tests.test_motion import calibration, motion_report


class TransportTests(unittest.TestCase):
    def test_direct_loop_uses_real_descriptors_and_closes_at_eof_or_stop(self):
        script=r'''
import json,os,sys
from pathlib import Path
from test_broker import ns
real_open=os.open;real_read=os.read;opened=[];counts={'input':0,'commands':0}
def tracked_open(*args):
    fd=real_open(*args);opened.append(fd);return fd
def tracked_read(fd,size):
    key='input' if fd in opened else 'commands';counts[key]+=1
    assert counts[key]<=3,'Repeated reads after the expected end'
    return real_read(fd,size)
def unexpected_write(*args):raise AssertionError('Read-only scenario wrote an output report')
ns.update(supported=lambda device:True,raw_device=lambda device:Path(sys.argv[1]),hardware_identity=lambda device:'hid:fixture')
os.geteuid=lambda:0  # Simulate the dispatch guard only; no real privileges or USB.
os.open=tracked_open;os.read=tracked_read;os.write=unexpected_write
reason='stop'
try:ns['stream_control']('1-1')
except OSError as error:
    assert str(error)=='A leitura USB foi encerrada pelo dispositivo.'
    reason='eof'
assert len(opened)==1
try:os.fstat(opened[0])
except OSError:pass
else:raise AssertionError('Descriptor leaked')
print(json.dumps({'ended':reason,'reads':counts}),flush=True)
'''
        packet=report();packet[53]=0x15
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);device=root/'fake-report';commands=root/'commands'
            for payload,stop,input_reads in ((b'',False,1),(bytes(packet),False,2),(bytes(packet),True,0)):
                with self.subTest(stop=stop,input_reads=input_reads):
                    device.write_bytes(payload);commands.write_bytes(b'{"stop":true}\n')
                    with commands.open('rb') as command_file:
                        process=subprocess.Popen([sys.executable,'-c',script,str(device)],
                            cwd=Path(__file__).resolve().parents[1],stdin=command_file if stop else subprocess.PIPE,
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                        try:
                            # Keep stdin open: communicate() would close it and
                            # hide an infinite EOF loop by requesting shutdown.
                            process.wait(timeout=5)
                        finally:
                            if process.poll() is None:process.kill()
                            output,error=process.communicate(timeout=5)
                    self.assertEqual(process.returncode,0,error)
                    events=[json.loads(line) for line in output.splitlines()]
                    self.assertEqual(events[-1]['ended'],'stop' if stop else 'eof')
                    self.assertEqual(events[-1]['reads']['input'],input_reads)
                    self.assertEqual(sum('reading' in event for event in events),int(bool(payload) and not stop))

    def direct_context(self,stack,read,ready):
        stdin=Mock();stdin.fileno.return_value=17
        stack.enter_context(patch.object(ns['sys'],'stdin',stdin))
        stack.enter_context(patch.object(ns['os'],'geteuid',return_value=0))
        stack.enter_context(patch.object(ns['os'],'open',return_value=42))
        close=stack.enter_context(patch.object(ns['os'],'close'))
        write=stack.enter_context(patch.object(ns['os'],'write'))
        stack.enter_context(patch.object(ns['os'],'read',side_effect=read))
        stack.enter_context(patch.object(ns['select'],'select',side_effect=ready))
        stack.enter_context(patch.dict(ns,supported=lambda device:True,raw_device=lambda device:Path('/fake'),hardware_identity=lambda device:'hid:fixture'))
        return close,write

    def test_direct_empty_read_ends_once_without_spinning_or_reusing_data(self):
        with contextlib.ExitStack() as stack:
            close,write=self.direct_context(stack,[b'',AssertionError('Repeated read after EOF')],lambda *args:([42],[],[]))
            output=stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaisesRegex(OSError,'leitura USB'):ns['stream_control']('1-1')
            close.assert_called_once_with(42);write.assert_not_called();self.assertEqual(output.getvalue(),'')

    def test_direct_would_block_is_transient_and_next_report_is_received(self):
        packet=report();packet[53]=0x15
        with contextlib.ExitStack() as stack:
            close,write=self.direct_context(stack,[BlockingIOError(errno.EAGAIN,'try again'),bytes(packet),b'{"stop":true}\n'],
                                           [([42],[],[]),([42],[],[]),([17],[],[])])
            output=stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            ns['stream_control']('1-1');close.assert_called_once_with(42);write.assert_not_called()
            readings=[json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(len(readings),1);self.assertEqual(readings[0]['reading']['capacity'],55)

    def test_stop_command_wins_over_simultaneously_ready_controller_input(self):
        with contextlib.ExitStack() as stack:
            close,write=self.direct_context(stack,[b'{"stop":true}\n',AssertionError('Input processed after stop')],
                                           [([17,42],[],[])])
            output=stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            ns['stream_control']('1-1');close.assert_called_once_with(42);write.assert_not_called()
            self.assertEqual(output.getvalue(),'')

    def test_direct_rumble_test_stops_on_deadline_without_new_reports(self):
        for release in (False,True):
            with self.subTest(release=release),contextlib.ExitStack() as stack:
                tick=[0]
                def ready(*args):
                    tick[0]+=1
                    return ([17] if tick[0] in (1,3) or release else [42],[],[])
                reads=[b'{"test":true}\n',b'{"release":true}\n' if release else BlockingIOError(errno.EAGAIN,'no data'),b'{"stop":true}\n']
                close,write=self.direct_context(stack,reads,ready)
                stack.enter_context(patch.object(ns['time'],'monotonic',side_effect=lambda:100+tick[0]*(.1 if release else 2)))
                ns['stream_control']('1-1')
                packets=[call.args[1] for call in write.call_args_list]
                motor_values=[tuple(packet[3:5]) for packet in packets if packet[1]&3]
                self.assertEqual(motor_values,[(100,100),(0,0)])
                close.assert_called_once_with(42)

    def test_one_shot_read_stops_at_eof_and_tolerates_would_block(self):
        packet=report();packet[53]=0x15
        for reads,expected in (([b'',AssertionError('Repeated read after EOF')],None),
                               ([BlockingIOError(errno.EAGAIN,'try again'),bytes(packet)],55)):
            with self.subTest(expected=expected),contextlib.ExitStack() as stack:
                close,write=self.direct_context(stack,reads,lambda *args:([42],[],[]))
                result=ns['raw_battery'](Path('/fake'))
                self.assertEqual(result['capacity'] if result else None,expected)
                close.assert_called_once_with(42);write.assert_not_called()

    def test_one_shot_battery_read_remains_independent(self):
        packet=report();packet[53]=0x15
        with patch.dict(ns,raw_device=lambda device:Path('/fake')),patch.object(ns['os'],'open',return_value=42),patch.object(ns['os'],'close'),patch.object(ns['os'],'read',return_value=bytes(packet)),patch.object(ns['select'],'select',return_value=([42],[],[])):
            self.assertEqual(ns['raw_battery'](Path('/fake'))['capacity'],55)

    def test_exclusive_monitor_does_not_create_virtual_or_change_outputs(self):
        def exercise(monitor):
            count=0
            command=0
            sent=[]
            def ready(*args):
                nonlocal command
                if command==0 or count>=30:
                    command+=1
                    return ([17],[],[])
                return ([],[],[])
            def read(*args):
                return (json.dumps({'monitor':monitor})+'\n').encode() if command==1 else b'{"stop":true}\n'
            def transfer(handle,endpoint,data,size,transferred,timeout):
                nonlocal count
                packet=report();packet[9]=1 if count%2 else 0;packet[53]=0x15
                touch(packet,0,12,400,500);touch(packet,1,13,1400,200)
                for index,value in enumerate(packet):data[index]=value
                transferred._obj.value=64;count+=1
                return 0
            lib=Mock();lib.libusb_interrupt_transfer.side_effect=transfer
            def feature(handle,request_type,request,value,number,data,length,timeout):
                self.assertEqual((request_type,request,value,length),(0xa1,1,0x0305,41))
                data[:]=calibration();return 41
            lib.libusb_control_transfer.side_effect=feature
            stdin=Mock();stdin.fileno.return_value=17
            output=io.StringIO()
            with patch.object(ns['sys'],'stdin',stdin),patch.object(ns['select'],'select',side_effect=ready),patch.object(ns['os'],'read',side_effect=read),patch.object(ns['time'],'monotonic',side_effect=lambda:100+count/100),patch.dict(ns,VirtualDualSense=Mock(side_effect=AssertionError('Created virtual while charging'))),contextlib.redirect_stdout(output):
                ns['broker_usb'](Path('/fake'),ns['decode_battery'],'hid:example',lib,None,0,1,lambda data:sent.append(bytes(data)),'charge')
            self.assertEqual(lib.libusb_control_transfer.call_count,1 if monitor else 0)
            return sent,[json.loads(line) for line in output.getvalue().splitlines()]
        baseline,_=exercise(False)
        sent,events=exercise(True)
        self.assertEqual(sent,baseline)
        self.assertTrue(any('input' in event for event in events))
        self.assertTrue(any('reading' in event for event in events))
        self.assertTrue(any('L1' in event['input']['observed'] for event in events if 'input' in event))
        self.assertTrue(all(len(event['input']['touches'])==2 for event in events if 'input' in event))

    def test_direct_monitor_never_writes_effects(self):
        count=0
        def ready(*args):
            nonlocal count
            count+=1
            return ([17] if count in (1,12) else [42],[],[])
        def read(fd,length):
            if fd==17:return b'{"monitor":true}\n' if count==1 else b'{"stop":true}\n'
            packet=motion_report();packet[9]=1;packet[53]=0x15
            touch(packet,1,4,1000,600)
            return bytes(packet)
        stdin=Mock();stdin.fileno.return_value=17
        output=io.StringIO()
        feature=Mock(return_value=calibration())
        with patch.object(ns['sys'],'stdin',stdin),patch.object(ns['os'],'geteuid',return_value=0),patch.object(ns['os'],'open',return_value=42),patch.object(ns['os'],'close'),patch.object(ns['os'],'write') as write,patch.object(ns['os'],'read',side_effect=read),patch.object(ns['select'],'select',side_effect=ready),patch.object(ns['time'],'monotonic',side_effect=lambda:100+count/10),patch.dict(ns,supported=lambda device:True,raw_device=lambda device:Path('/fake'),hardware_identity=lambda device:'hid:example',read_motion_feature=feature),contextlib.redirect_stdout(output):
            ns['stream_control']('1-1')
        write.assert_not_called()
        feature.assert_called_once_with(42)
        self.assertTrue(all(json.loads(line)['input']['motion']['gyro_dps']==[500,-500,500]
                            for line in output.getvalue().splitlines() if 'input' in json.loads(line)))
        self.assertTrue(any('input' in json.loads(line) for line in output.getvalue().splitlines()))
        self.assertTrue(all(json.loads(line)['input']['touches']==[{'slot':1,'id':4,'x':1000,'y':600}]
                            for line in output.getvalue().splitlines() if 'input' in json.loads(line)))
