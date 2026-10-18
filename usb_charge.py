# SPDX-License-Identifier: GPL-3.0-only
"""Exclusive libusb HID ownership; no kernel input devices while charging."""
import ctypes as C
import ctypes.util
import json
import os
import select
import sys
import time

CHARGE_PROFILE = 'quiet-peripherals-v1'

def charge_report():
    # Output layout and mute bits: nowrep/dualsensectl, main.c.
    # Keep touch/motion functions enabled; only mute audio/haptics and remove
    # adaptive-trigger effects. Never use the former power-save mask 0x0f.
    report=bytearray(63)
    report[0]=2
    report[1]=0x03|0x04|0x08  # rumble zero, right/left trigger commands
    report[2]=0x01|0x02|0x04|0x10  # mic LED, mute, RGB, player LEDs
    report[10]=0xf0  # mic, speaker, headphones and haptics muted
    report[11]=report[22]=0x05  # documented trigger OFF effect
    return report

def charge_usb(device, decoder, identity, managed_mode=None):
    lib=C.CDLL(ctypes.util.find_library('usb-1.0'))
    signatures={
        'libusb_init':([C.POINTER(C.c_void_p)],C.c_int),
        'libusb_exit':([C.c_void_p],None),
        'libusb_get_device_list':([C.c_void_p,C.POINTER(C.POINTER(C.c_void_p))],C.c_ssize_t),
        'libusb_free_device_list':([C.POINTER(C.c_void_p),C.c_int],None),
        'libusb_get_bus_number':([C.c_void_p],C.c_uint8),
        'libusb_get_device_address':([C.c_void_p],C.c_uint8),
        'libusb_open':([C.c_void_p,C.POINTER(C.c_void_p)],C.c_int),
        'libusb_close':([C.c_void_p],None),
        'libusb_kernel_driver_active':([C.c_void_p,C.c_int],C.c_int),
        'libusb_detach_kernel_driver':([C.c_void_p,C.c_int],C.c_int),
        'libusb_attach_kernel_driver':([C.c_void_p,C.c_int],C.c_int),
        'libusb_claim_interface':([C.c_void_p,C.c_int],C.c_int),
        'libusb_release_interface':([C.c_void_p,C.c_int],C.c_int),
        'libusb_reset_device':([C.c_void_p],C.c_int),
        'libusb_control_transfer':([C.c_void_p,C.c_uint8,C.c_uint8,C.c_uint16,C.c_uint16,C.POINTER(C.c_ubyte),C.c_uint16,C.c_uint],C.c_int),
        'libusb_interrupt_transfer':([C.c_void_p,C.c_ubyte,C.POINTER(C.c_ubyte),C.c_int,C.POINTER(C.c_int),C.c_uint],C.c_int),
    }
    for name,(args,result) in signatures.items():
        function=getattr(lib,name);function.argtypes=args;function.restype=result
    def check(result):
        if result<0:raise OSError('Falha libusb: '+str(result))
    interfaces=[p for p in device.parent.glob(device.name+':*') if (p/'bInterfaceClass').read_text().strip()=='03']
    if len(interfaces)!=1:raise ValueError('Interface HID inesperada.')
    interface=interfaces[0];number=int((interface/'bInterfaceNumber').read_text().strip(),16)
    incoming=outgoing=None
    for endpoint in interface.glob('ep_*'):
        if (endpoint/'bmAttributes').read_text().strip()!='03':continue
        address=int((endpoint/'bEndpointAddress').read_text().strip(),16)
        if address&128:incoming=address
        else:outgoing=address
    if incoming is None or outgoing is None:raise ValueError('Endpoints HID indisponíveis.')
    bus=int((device/'busnum').read_text());address=int((device/'devnum').read_text())
    ctx=C.c_void_p();handle=C.c_void_p();items=C.POINTER(C.c_void_p)()
    claimed=detached=False
    check(lib.libusb_init(C.byref(ctx)))
    try:
        count=lib.libusb_get_device_list(ctx,C.byref(items));check(count)
        try:
            for i in range(count):
                if lib.libusb_get_bus_number(items[i])==bus and lib.libusb_get_device_address(items[i])==address:
                    check(lib.libusb_open(items[i],C.byref(handle)));break
            if not handle:raise ValueError('Controle não encontrado no USB.')
        finally:lib.libusb_free_device_list(items,1)
        if lib.libusb_kernel_driver_active(handle,number)==1:
            check(lib.libusb_detach_kernel_driver(handle,number));detached=True
        check(lib.libusb_claim_interface(handle,number));claimed=True
        def send(payload):
            data=(C.c_ubyte*len(payload)).from_buffer_copy(payload);transferred=C.c_int()
            check(lib.libusb_interrupt_transfer(handle,outgoing,data,len(payload),C.byref(transferred),1000))
            if transferred.value!=len(payload):raise OSError('Comando USB incompleto.')
        if managed_mode is not None:
            return broker_usb(device, decoder, identity, lib, handle, number,
                              incoming, send, managed_mode)
        # Isolation from Steam comes from claiming HID, not power-save bits.
        report=charge_report()
        send(report)
        last=0;buffer=b''
        while True:
            if select.select([sys.stdin.fileno()],[],[],0)[0]:
                chunk=os.read(sys.stdin.fileno(),4096)
                if not chunk:break
                buffer+=chunk
                if len(buffer)>8192:raise ValueError('Comando muito longo.')
                stop=False
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    request=json.loads(line)
                    if request.get('stop'):stop=True
                    if request.get('refresh'):
                        sample=(C.c_ubyte*64)()
                        count=lib.libusb_control_transfer(handle,0xa1,1,0x0101,number,sample,64,1000)
                        reading=decoder(bytes(sample[:count])) if count>0 else None
                        print(json.dumps({'event':'refresh','method':'get-report','result':count,'reading':reading,'identity':identity,'exclusive':True}),flush=True)
                    if request.get('reset'):
                        result=lib.libusb_reset_device(handle)
                        print(json.dumps({'event':'reset','result':result}),flush=True)
                        check(result)
                        send(report)
                        last=0
                    if request.get('wake'):
                        awake=bytearray(63);awake[0]=2;awake[2]=2
                        send(awake)
                    if request.get('sensors'):
                        # Fixed sensor-read diagnostic only; never unlock or
                        # write calibration/NVS. Layout implemented by VIIPER.
                        command=(C.c_ubyte*64)(0x80,4,0)
                        sent=lib.libusb_control_transfer(handle,0x21,9,0x0380,number,command,64,1000)
                        sample=(C.c_ubyte*64)()
                        count=lib.libusb_control_transfer(handle,0xa1,1,0x0381,number,sample,64,1000) if sent>=0 else sent
                        print(json.dumps({'event':'sensors','sent':sent,'result':count,'raw':bytes(sample[:max(count,0)]).hex()}),flush=True)
                    if request.get('identify'):
                        for _ in range(4):
                            blink=bytearray(63);blink[0]=2;blink[2]=16;blink[44]=31
                            send(blink);time.sleep(.25)
                            blink[44]=0;send(blink);time.sleep(.25)
                if stop:break
            data=(C.c_ubyte*64)();transferred=C.c_int()
            result=lib.libusb_interrupt_transfer(handle,incoming,data,64,C.byref(transferred),250)
            if result==-7:continue
            check(result)
            packet=bytes(data[:transferred.value])
            reading=decoder(packet)
            if reading and time.monotonic()-last>=1:
                reading.update(raw_status=packet[53], sequence=packet[7], sensor_timestamp=int.from_bytes(packet[28:32],'little'), connection_flags=packet[54], charge_profile=CHARGE_PROFILE)
                print(json.dumps({'reading':reading,'identity':identity,'exclusive':True}),flush=True)
                last=time.monotonic()
    finally:
        if handle:
            if claimed:
                try:
                    report=bytearray(63);report[0]=2;report[2]=2
                    send(report)  # Restore firmware functions before driver returns.
                except Exception:pass
                lib.libusb_release_interface(handle,number)
            if detached:lib.libusb_attach_kernel_driver(handle,number)
            lib.libusb_close(handle)
        lib.libusb_exit(ctx)
