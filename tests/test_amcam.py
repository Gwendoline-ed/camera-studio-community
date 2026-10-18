import ctypes as C
import io
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch
from tiny2.amcam import Device,Model,FrameInfo,SDK,Capture,EVENT_IMAGE
from tiny2.amcam_preview import read_frame


class FakeSDK:
    def __init__(self):self.events=[];self.callback=None
    def resolve(self,identifier):return identifier
    def Open(self,identifier):self.events.append('open');return 1
    def put_Option(self,*_):return 0
    def put_RealTime(self,*_):return 0
    def get_FinalSize(self,_h,w,h):w._obj.value=2;h._obj.value=1;return 0
    def StartPullModeWithCallback(self,_h,cb,_ctx):self.callback=cb;return 0
    def PullImageWithRowPitchV2(self,_h,buffer,bits,stride,info):
        self.events.append('pull');C.memmove(buffer,bytes([240,40,30,20,180,230]),6)
        info._obj.width=2;info._obj.height=1;return 0
    def Stop(self,_h):self.events.append('stop');return 0
    def Close(self,_h):self.events.append('close')


class AmcamTests(unittest.TestCase):
    def test_linux_sdk_layout(self):
        self.assertEqual(C.sizeof(Device),136);self.assertEqual(Device.model.offset,128)
        self.assertEqual(C.sizeof(Model),176);self.assertEqual(Model.res.offset,44)
        self.assertEqual(C.sizeof(FrameInfo),24)

    def test_callback_only_pulls_latest_rgb_then_main_thread_closes(self):
        sdk=FakeSDK();camera=Capture(sdk,'chosen')
        sdk.callback(EVENT_IMAGE,None);sdk.callback(EVENT_IMAGE,None)
        width,height,stride,data=camera.next_frame()
        self.assertEqual((width,height,stride),(2,1,6));self.assertEqual(data[:3],bytes([240,40,30]))
        self.assertIsNone(camera.next_frame(.001));self.assertNotIn('close',sdk.events)
        sdk.callback(0x81,None)
        with self.assertRaisesRegex(RuntimeError,'getrennt'):camera.next_frame()
        self.assertNotIn('close',sdk.events)
        camera.close();camera.close();self.assertEqual(sdk.events[-2:],['stop','close'])

    def test_start_failure_closes_handle(self):
        sdk=FakeSDK();sdk.StartPullModeWithCallback=lambda *_:-1
        with self.assertRaises(RuntimeError):Capture(sdk,'chosen')
        self.assertEqual(sdk.events,['open','close'])

    def test_busy_open_has_actionable_error(self):
        sdk=FakeSDK();sdk.Open=lambda _:None
        with self.assertRaisesRegex(RuntimeError,'AmLite'):Capture(sdk,'chosen')
        self.assertNotIn('close',sdk.events)

    def test_sdk_model_identifies_non_v4l_usb_node(self):
        sdk=SDK.__new__(SDK);model=Model();model.name=b'MU300'
        sdk.get_Model=lambda v,p:C.pointer(model) if (v,p)==(0x0547,0x6310) else None
        with tempfile.TemporaryDirectory() as folder:
            node=Path(folder)/'5-1';node.mkdir();(node/'idVendor').write_text('0547');(node/'idProduct').write_text('6310')
            cameras=sdk.usb_cameras(Path(folder))
        self.assertEqual(cameras[0]['name'],'AmScope MU300');self.assertFalse(cameras[0]['available'])
        self.assertEqual(cameras[0]['path'],'amcam-usb:5-1')

    def test_no_arbitrary_camera_when_selected_device_disappears(self):
        sdk=SDK.__new__(SDK);sdk.cameras=lambda:[{'path':'other','model':'MU300'}]
        sdk.usb_cameras=lambda:[]
        with self.assertRaisesRegex(RuntimeError,'Neu suchen'):sdk.resolve('missing')
        with self.assertRaises(RuntimeError):sdk.resolve('amcam-usb:5-1')
        self.assertEqual(sdk.resolve('other'),'other')

    def test_frame_protocol_bounds_and_eof(self):
        data=bytes([240,40,30,20,180,230]);header=dict(type='frame',width=2,height=1,stride=6,size=6)
        self.assertEqual(read_frame(io.BytesIO(json.dumps(header).encode()+b'\n'+data)),(2,1,6,data))
        with self.assertRaises(EOFError):read_frame(io.BytesIO(json.dumps(header).encode()+b'\n'+data[:2]))
        for changes in ({'width':-1},{'width':20000001},{'stride':3},{'size':999},{'height':True}):
            with self.assertRaises(ValueError):read_frame(io.BytesIO(json.dumps({**header,**changes}).encode()+b'\n'+data))
        with self.assertRaisesRegex(RuntimeError,'USB getrennt'):
            read_frame(io.BytesIO(b'{"type":"error","error":"USB getrennt"}\n'))


if __name__=='__main__':unittest.main()
