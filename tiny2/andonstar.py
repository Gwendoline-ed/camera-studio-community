"""Read-only discovery on an already connected Andonstar Wi-Fi network."""
from .i18n import tr as _t
import http.client
import ipaddress
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit


def stream_url(value, host=None):
    """Accept only the camera's observed local HTTP/MJPEG endpoint."""
    try:
        url=urlsplit(value)
        address=ipaddress.IPv4Address(url.hostname)
        valid=(address.is_private and not address.is_loopback and not address.is_unspecified
               and not address.is_multicast and url.scheme=='http' and url.port==8192
               and url.path in ('','/') and not url.query and not url.fragment
               and url.username is None and url.password is None
               and (host is None or str(address)==host))
        if valid:return f'http://{address}:8192/'
    except (ValueError,TypeError):pass
    raise ValueError(_t('Ungültige Andonstar-Bildadresse.'))


def query(host,command):
    # Only two documented read operations; no recording or camera settings.
    if command not in (3012,2019):raise ValueError(_t('Unbekannte Kameraabfrage.'))
    connection=http.client.HTTPConnection(host,timeout=1.5)
    try:
        connection.request('GET',f'/?custom=1&cmd={command}')
        response=connection.getresponse();body=response.read(65537)
        if response.status!=200 or len(body)>65536:raise ValueError(_t('Ungültige Kameraantwort.'))
        return ET.fromstring(body)
    finally:connection.close()


def probe(host):
    stream_url(f'http://{host}:8192/')
    version=query(host,3012)
    firmware=version.findtext('String','')
    if version.findtext('Status')!='0' or not re.fullmatch(r'AD[0-9][\w.-]{1,100}',firmware):
        raise ValueError(_t('Keine Andonstar-Kamera erkannt.'))
    links=query(host,2019)
    path=stream_url(links.findtext('MovieLiveViewLink',''),host)
    return {'path':path,'name':'Andonstar · WLAN','firmware':firmware}


def nmcli(*args):
    return subprocess.run(['nmcli','-t','-e','no',*args],check=True,capture_output=True,
                          text=True,timeout=2,env={**os.environ,'LC_ALL':'C'}).stdout


def discover():
    """No Wi-Fi switching, guessed host probes or scanning of unrelated networks."""
    found=[]
    try:
        devices=nmcli('-f','DEVICE,TYPE,STATE','device','status')
        for line in devices.splitlines():
            fields=line.split(':')
            if len(fields)!=3 or fields[1:]!=['wifi','connected']:continue
            interface=fields[0]
            networks=nmcli('-f','IN-USE,SSID','device','wifi','list','ifname',interface,'--rescan','no')
            if not any(row.startswith('*:Andonstar-') for row in networks.splitlines()):continue
            options=nmcli('-g','DHCP4.OPTION','device','show',interface)
            server=re.search(r'(?:^|[|\n])\s*dhcp_server_identifier = ([0-9.]+)(?:\s*[|\n]|$)',options)
            if server:
                try:found.append(probe(server.group(1)))
                except (OSError,ValueError,ET.ParseError,http.client.HTTPException):continue
    except (OSError,subprocess.SubprocessError):pass
    return found
