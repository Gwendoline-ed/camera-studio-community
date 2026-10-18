import http.client
import unittest
from unittest.mock import patch,Mock
import xml.etree.ElementTree as ET
from tiny2 import andonstar as wifi


class AndonstarTests(unittest.TestCase):
    def test_stream_address_stays_on_selected_local_camera(self):
        self.assertEqual(wifi.stream_url('http://192.168.1.254:8192'),'http://192.168.1.254:8192/')
        bad=['http://example.com:8192/','http://8.8.8.8:8192/','http://127.0.0.1:8192/',
             'http://192.168.1.254/','file:///tmp/image','http://user:pw@192.168.1.254:8192/',
             'http://192.168.1.254:8192/?cmd=3010','http://192.168.1.254:8192/" ! fakesink']
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):wifi.stream_url(value)
        with self.assertRaises(ValueError):wifi.stream_url('http://192.168.1.253:8192/','192.168.1.254')

    def test_camera_supplies_its_stream_address(self):
        version=ET.fromstring('<Function><Status>0</Status><String>AD400.22101990.V31-DUAL10</String></Function>')
        links=ET.fromstring('<LIST><MovieLiveViewLink>http://192.168.1.254:8192</MovieLiveViewLink></LIST>')
        with patch.object(wifi,'query',side_effect=[version,links]) as query:
            found=wifi.probe('192.168.1.254')
        self.assertEqual(found['name'],'Andonstar · WLAN')
        self.assertEqual([c.args for c in query.call_args_list],[('192.168.1.254',3012),('192.168.1.254',2019)])

    def test_wrong_camera_not_added(self):
        for value in ('other-camera','AD400</String>',''):
            root=ET.Element('Function');ET.SubElement(root,'Status').text='0';ET.SubElement(root,'String').text=value
            with patch.object(wifi,'query',return_value=root),self.assertRaises(ValueError):wifi.probe('192.168.1.254')

    def test_queries_are_read_only_and_bounded(self):
        with self.assertRaises(ValueError):wifi.query('192.168.1.254',3010)
        connection=Mock();response=connection.getresponse.return_value;response.status=200
        response.read.return_value=b'x'*65537
        with patch.object(http.client,'HTTPConnection',return_value=connection),self.assertRaises(ValueError):
            wifi.query('192.168.1.254',3012)
        connection.close.assert_called_once()

    def test_only_connected_andonstar_network_is_probed(self):
        replies=['enp7s0:ethernet:connected\nwlp8s0:wifi:connected\n',
                 ' :Andonstar-nearby\n*:Home WiFi\n']
        with patch.object(wifi,'nmcli',side_effect=replies),patch.object(wifi,'probe') as probe:
            self.assertEqual(wifi.discover(),[]);probe.assert_not_called()
        replies=['wlp8s0:wifi:connected\n','*:Andonstar-test\n',
                 'ip_address = 192.168.1.33 | dhcp_server_identifier = 192.168.1.254 | routers = 192.168.1.254\n']
        with patch.object(wifi,'nmcli',side_effect=replies),patch.object(wifi,'probe',return_value={'path':'camera'}) as probe:
            self.assertEqual(wifi.discover(),[{'path':'camera'}]);probe.assert_called_once_with('192.168.1.254')

    def test_unavailable_network_manager_or_camera_is_not_fatal(self):
        with patch.object(wifi,'nmcli',side_effect=FileNotFoundError):self.assertEqual(wifi.discover(),[])
        replies=['wlp8s0:wifi:connected\n','*:Andonstar-1234\n','dhcp_server_identifier = 192.168.1.254']
        with patch.object(wifi,'nmcli',side_effect=replies),patch.object(wifi,'probe',side_effect=TimeoutError):
            self.assertEqual(wifi.discover(),[])


if __name__=='__main__':unittest.main()
