import ctypes
from dataclasses import asdict
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tiny2 import protocol as p
from tiny2.device import Camera, Candidate, XU, XU_QUERY, extension_unit, XU_GUID
from tiny2.controller import Controller, Presets


def response(seq=7, command=0x43, payload=bytes(32), sender=3, flags=0x29):
    data=bytearray(p.frame(seq,command,sender,payload))
    data[1]=flags;data[8]=sender;data[9]=10;data[6:8]=b'\0\0'
    struct.pack_into('<H',data,6,p.crc16(data[:12]))
    return bytes(data)


class PacketTests(unittest.TestCase):
    def test_standard_crc_check_value(self):
        self.assertEqual(p.crc16(b'123456789'),0xB4C8)

    def test_captured_windows_wake_packet(self):
        # Header + payload CRCs from the published Windows USB capture.
        expected=bytes.fromhex('aa25ac000c008fc00a02c2a00400be0700000000')+bytes(40)
        self.assertEqual(p.frame(172,0xA0C2,2,bytes(4)),expected)

    def test_captured_windows_sleep_packet(self):
        expected=bytes.fromhex('aa25ab000c003e1a0a02c2a00400bffb01000000')+bytes(40)
        self.assertEqual(p.frame(171,0xA0C2,2,struct.pack('<I',1)),expected)

    def test_get_and_empty_set_flags_differ(self):
        self.assertEqual(p.frame(3,0x43,3,query=True)[1],1)
        self.assertEqual(p.frame(3,0x6704,4)[1],5)

    def test_axis_order_and_tilt_sign(self):
        self.assertEqual(struct.unpack('<fff',p.angle_payload(20,10)),(0,-10,20))

    def test_invalid_angles_rejected(self):
        for pan,tilt in [(131,0),(0,-91),(float('nan'),0),(0,float('inf'))]:
            with self.assertRaises(ValueError):p.angle_payload(pan,tilt)

    def test_frame_limits(self):
        for args in [(1,0x43,3,bytes(45)),(-1,0x43,3,b''),(1,0x43,64,b'')]:
            with self.assertRaises(ValueError):p.frame(*args)

    def test_reply_roundtrip_and_integrity(self):
        good=response();self.assertEqual(p.parse_reply(good).payload,bytes(32))
        for offset in (0,4,6,10,14,20):
            bad=bytearray(good);bad[offset]^=1
            with self.assertRaises(p.ProtocolError):p.parse_reply(bytes(bad))

    def test_not_a_reply(self):
        with self.assertRaises(p.ProtocolError):p.parse_reply(p.frame(7,0x43,3,bytes(32)))

    def test_error_reply(self):
        with self.assertRaises(p.ProtocolError):p.parse_reply(response(flags=0xA9))

    def test_oversize_payload(self):
        bad=bytearray(response());struct.pack_into('<H',bad,12,45)
        with self.assertRaises(p.ProtocolError):p.parse_reply(bytes(bad))

    def test_transient_not_misreported_as_hand(self):
        data=bytearray(60);data[0x18]=6
        self.assertEqual(p.status(data)['mode'],'Wechsel / unbekannt')
        data[0x18]=3;self.assertEqual(p.status(data)['mode'],'Hand')

    def test_xu_matches_video_interface_and_guid(self):
        interface=bytes([9,4,0,0,0,14,1,0,0])
        xu=bytes([24,0x24,6,2])+XU_GUID+bytes(4)
        self.assertEqual(extension_unit(interface+xu),2)
        with self.assertRaises(ValueError):extension_unit(xu)
        with self.assertRaises(ValueError):extension_unit(interface+xu[:14])


class MailboxTests(unittest.TestCase):
    def camera(self, replies):
        camera=Camera.__new__(Camera)
        camera.seq=7;camera.lock=threading.RLock()
        self.writes=[]
        def query(selector,request,data=None,size=60):
            if request==1:self.writes.append(data);return data
            return next(replies)
        camera.query=query
        return camera

    @patch('tiny2.device.time.sleep',lambda _:None)
    def test_stale_reply_ignored(self):
        camera=self.camera(iter([response(seq=6),response(command=0x6604),response()]))
        self.assertEqual(camera.send(0x43,3,read=True),bytes(32))
        self.assertEqual(len(self.writes),1)

    @patch('tiny2.device.time.sleep',lambda _:None)
    def test_wrong_sender_ignored(self):
        camera=self.camera(iter([response(sender=4),response()]))
        self.assertEqual(camera.send(0x43,3,read=True),bytes(32))

    @patch('tiny2.device.time.sleep',lambda _:None)
    def test_matching_crc_error_not_success(self):
        bad=bytearray(response());bad[18]=1
        camera=self.camera(iter([bytes(bad)]))
        with self.assertRaises(p.ProtocolError):camera.send(0x43,3,read=True)

    def test_write_never_claims_ack(self):
        camera=self.camera(iter([]));self.assertIsNone(camera.send(0x6444,4,bytes(12)))

    def test_sequence_wrap(self):
        camera=self.camera(iter([]));camera.seq=65535
        camera.send(0x6704,4);camera.send(0x6704,4)
        self.assertEqual([struct.unpack_from('<H',b,2)[0] for b in self.writes],[65535,0])


class FakeCamera:
    def __init__(self):
        self.events=[]
        self.snapshot={'awake':True,'mode':'Normal','speed':'Standard','zoom_percent':0,'hdr':False,'fov':'Weit'}
    def status(self):return dict(self.snapshot)
    def raw_write(self,tag,values):
        self.events.append(('raw',tag,values))
        if tag==0x16:self.snapshot['mode']=next(k for k,v in p.MODES.items() if v==tuple(values))
    def send(self,command,receiver,payload=b'',**kwargs):self.events.append(('send',command,receiver,payload))


class ControllerTests(unittest.TestCase):
    def test_invalid_move_has_no_side_effects(self):
        camera=FakeCamera();control=Controller(camera)
        with self.assertRaises(ValueError):control.move(999,0)
        self.assertEqual(camera.events,[])

    def test_manual_move_disables_tracking_first(self):
        camera=FakeCamera();result=Controller(camera).move(12,7)
        self.assertEqual(camera.events[0],('raw',0x16,b'\0\0'))
        self.assertEqual(camera.events[1][1],0x6444)
        self.assertFalse(result.confirmed)

    def test_mode_confirmed_only_after_device_state(self):
        camera=FakeCamera();result=Controller(camera).mode('Nahansicht')
        self.assertTrue(result.confirmed);self.assertEqual(result.snapshot['mode'],'Nahansicht')

    def test_timeout_no_false_confirmation(self):
        control=Controller(FakeCamera())
        with self.assertRaises(TimeoutError):control.verify(lambda _:False,timeout=0)

    def test_cancel_before_motion(self):
        camera=FakeCamera();control=Controller(camera);control.cancel.set()
        with self.assertRaises(InterruptedError):control.move(5,5)
        self.assertFalse(any(e[0]=='send' and e[1]==0x6444 for e in camera.events))

    def test_stop_attempts_all_three_paths_after_failure(self):
        camera=FakeCamera();camera.raw_write=lambda *_:(_ for _ in ()).throw(OSError('gone'))
        control=Controller(camera)
        with self.assertRaises(OSError):control.stop()
        self.assertEqual([e[1] for e in camera.events],[0x6484,0x6704])


class StorageTests(unittest.TestCase):
    def test_targets_persist_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Presets(temp);store.save(2,25,-10,35)
            self.assertEqual(Presets(temp).get(2),dict(pan=25,tilt=-10,zoom=35))
            with self.assertRaises(ValueError):store.get(1)
            self.assertEqual(len(list(Path(temp).iterdir())),1)

    def test_bad_file_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'presets.json';file.write_text('broken')
            with self.assertRaises(ValueError):Presets(temp).save(1,0,0,0)
            self.assertEqual(file.read_text(),'broken')


class ReadOnlyTransportTests(unittest.TestCase):
    def test_diagnosis_uses_read_only_fd_and_blocks_writes(self):
        import os,stat
        from tiny2 import device
        candidate=Candidate('/dev/video1','/sys/fake-tiny2',2,True)
        queries=[]
        def control(fd,number,pointer):
            q=pointer._obj;queries.append(q.query)
            if q.query==0x85:q.data[0]=60;q.data[1]=0
            elif q.query==0x86:q.data[0]=3
            return 0
        def capability(fd,number,buffer,mutate):
            struct.pack_into('<II',buffer,84,0x80000001,1)
        with patch.object(device,'discover',return_value=[candidate]), \
             patch.object(device.os,'open',return_value=77) as opening, \
             patch.object(device.os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
             patch.object(device.os,'close') as closing, \
             patch.object(device.fcntl,'ioctl',side_effect=capability), \
             patch.object(device.libc,'ioctl',side_effect=control):
            camera=Camera(candidate,writable=False)
            self.assertEqual(opening.call_args.args[1]&os.O_ACCMODE,os.O_RDONLY)
            self.assertTrue(camera.status()['awake'])
            with self.assertRaises(PermissionError):camera.raw_write(0x16,b'\0\0')
            with self.assertRaises(PermissionError):camera.set_control('zoom',10)
            with self.assertRaises(PermissionError):camera.send(0x43,3,read=True)
            self.assertNotIn(1,queries)
            camera.close();closing.assert_called_once_with(77)


if __name__=='__main__':unittest.main()
