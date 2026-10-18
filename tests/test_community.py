import errno
from fractions import Fraction
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from tiny2.camera_profiles import Registry, parse_profile, config_root
from tiny2 import video_modes as V, integrations

PROFILE={'version':1,'id':'usb-example','name':'Meine USB-Kamera','backend':'v4l2','usb':{'vendor':'1234','product':'ABCD'}}


class Profiles(unittest.TestCase):
    def test_isolated_default_and_tiny_fixed(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'XDG_CONFIG_HOME':directory}):
            r=Registry();self.assertEqual(r.root,Path(directory)/'camera-studio-community')
            self.assertEqual(r.enabled,{'tiny2','usb-video'})
            with self.assertRaises(ValueError):r.enable('tiny2',False)
            self.assertFalse((Path(directory)/'tiny2-studio').exists())
            self.assertFalse(r.active('amcam'));self.assertFalse(r.active('andonstar'))

    def test_import_persist_and_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.json';source.write_text(json.dumps(PROFILE))
            r=Registry(root/'config');p=r.install(source)
            r.enable('usb-video',False);r=Registry(root/'config')
            self.assertIn(p,r.profiles);self.assertIn(p.id,r.enabled)
            self.assertEqual(r.match_usb({'vendor':'1234','product':'abcd'}),p)
            self.assertIsNone(r.match_usb({'vendor':'1111','product':'2222'}))
            with self.assertRaisesRegex(ValueError,'bereits'):r.install(source)
            r.enable(p.id,False);self.assertIsNone(r.match_usb(p.usb))

    def test_no_code_paths_tiny_override_or_unknown_adapter(self):
        for change in ({'id':'../../evil'},{'backend':'python'},{'command':'anything'},
                       {'id':'tiny2'},{'version':True},{'usb':{'vendor':'3564','product':'fef8'}},
                       {'usb':{'vendor':'no','product':'0000'}}):
            with self.subTest(change=change),self.assertRaises(ValueError):parse_profile(PROFILE|change)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'big.json';source.write_bytes(b' '*16385)
            with self.assertRaises(ValueError):Registry.read(source)

    def test_bad_profile_is_reported_without_losing_core(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'profiles';folder.mkdir();(folder/'bad.json').write_text('{}')
            r=Registry(directory);self.assertTrue(r.errors);self.assertIn('tiny2',r.enabled)

    def test_disabled_adapters_are_not_probed(self):
        from tiny2.scope_window import sources
        with tempfile.TemporaryDirectory() as directory,patch('tiny2.scope_window.device.discover',return_value=[]),\
             patch('tiny2.scope_window.Path.glob',return_value=[]),patch('tiny2.amcam_preview.discover') as sdk,\
             patch('tiny2.andonstar.discover') as wifi:
            registry=Registry(directory)
            self.assertEqual(sources(registry),[]);sdk.assert_not_called();wifi.assert_not_called()
            sdk.return_value=[];wifi.return_value=[]
            registry.enable('amscope',True);registry.enable('andonstar',True)
            self.assertEqual(sources(registry),[]);sdk.assert_called_once();wifi.assert_called_once()


class Modes(unittest.TestCase):
    def fake_ioctl(self,fd,request,data,mutate):
        index=struct.unpack_from('=I',data)[0]
        if request==V.QUERYCAP:struct.pack_into('=II',data,84,0x80000000,1);return
        if request==V.ENUM_FMT:
            if index>1:raise OSError(errno.EINVAL,'end')
            data[44:48]=b'MJPG' if index==0 else b'YUYV';return
        if request==V.ENUM_SIZE:
            if index:raise OSError(errno.EINVAL,'end')
            struct.pack_into('=III',data,8,1,853,479);return
        if request==V.ENUM_INTERVAL:
            if index>1:raise OSError(errno.EINVAL,'end')
            struct.pack_into('=III',data,16,1,1001 if index==0 else 1,30000 if index==0 else 60);return
        raise AssertionError(request)

    def test_enumerates_formats_unusual_dimensions_and_fractional_rates(self):
        with patch.object(V.fcntl,'ioctl',side_effect=self.fake_ioctl):catalog=V.enumerate_fd(5)
        self.assertEqual(len(catalog.modes),4)
        self.assertIn(V.VideoMode(853,479,'MJPG',Fraction(30000,1001)),catalog.modes)
        self.assertIn('format=YUY2',V.VideoMode(853,479,'YUYV').caps)
        self.assertIn('framerate=30000/1001',catalog.modes[1].caps)

    def test_stepwise_size_uses_only_declared_grid(self):
        def ioctl(fd,request,data,mutate):
            if request==V.ENUM_SIZE:
                struct.pack_into('=7I',data,8,3,320,1920,16,240,1080,8);return
            return self.fake_ioctl(fd,request,data,mutate)
        with patch.object(V.fcntl,'ioctl',side_effect=ioctl):catalog=V.enumerate_fd(5)
        self.assertEqual(len(catalog.ranges),2);self.assertFalse(catalog.modes)
        self.assertEqual(catalog.ranges[0].mode(848,480).width,848)
        for size in ((849,480),(160,120),(2000,1080)):
            with self.assertRaises(ValueError):catalog.ranges[0].mode(*size)

    def test_continuous_fps_is_negotiated_not_fabricated(self):
        def ioctl(fd,request,data,mutate):struct.pack_into('=I',data,16,2)
        with patch.object(V.fcntl,'ioctl',side_effect=ioctl):self.assertEqual(V.frame_rates(5,0,640,480),[None])

    def test_unavailable_or_metadata_node_and_bounded_caps(self):
        self.assertTrue(V.available('/not/a/camera').note)
        with patch.object(V.fcntl,'ioctl',return_value=0),self.assertRaises(ValueError):V.enumerate_fd(5)
        for width,height,format in ((0,480,'MJPG'),(32000,32000,'MJPG'),(640,480,'!filesink')):
            with self.assertRaises(ValueError):V.VideoMode(width,height,format)

    def test_ioctl_matches_linux_header(self):
        self.assertEqual((V.ENUM_FMT,V.ENUM_SIZE,V.ENUM_INTERVAL),(0xc0405602,0xc02c564a,0xc034564b))


class Integrations(unittest.TestCase):
    def tearDown(self):integrations.configure(None)
    def test_config_persists_only_in_separate_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            integrations.configure(directory)
            self.assertEqual(integrations.load()['model'],'')
            integrations.save({'model':'my-vision','port':11436})
            self.assertEqual(integrations.load()['model'],'my-vision')
            self.assertEqual(integrations.load()['port'],11436)
            with self.assertRaises(ValueError):integrations.save({'port':0})
            with self.assertRaises(ValueError):integrations.save({'port':True})
            with self.assertRaises(ValueError):integrations.save({'remote':'example.org'})


if __name__=='__main__':unittest.main()
