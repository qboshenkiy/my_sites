"""Install the local-only HTTP protection socket in Caddy's existing data volume."""
import json
import os
from pathlib import Path
import subprocess


def main():
    if os.geteuid()!=0:raise SystemExit('Требуются права root')
    mounts=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}','glava-marathon-proxy-1'],text=True))
    data=next(m['Source'] for m in mounts if m['Destination']=='/data')
    socket=str(Path(data)/'guard-request.sock')
    Path('/etc/guard-request-gate.json').write_text(json.dumps({'socket':socket}))
    Path('/etc/guard-request-gate.json').chmod(0o600)
    source=Path(__file__).with_name('request_gate.py').resolve()
    unit=f'''[Unit]
Description=Guard shared HTTP rate and scanner protection
After=docker.service guard-firewall.service
Requires=guard-firewall.service
[Service]
ExecStart=/usr/bin/python3 {source}
Restart=always
RestartSec=1
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths={data}
[Install]
WantedBy=multi-user.target
'''
    Path('/etc/systemd/system/guard-request-gate.service').write_text(unit)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','guard-request-gate'],check=True)
    subprocess.run(['systemctl','restart','guard-request-gate'],check=True)
    import time, socket as sockets
    for _ in range(30):
        try:
            with sockets.socket(sockets.AF_UNIX,sockets.SOCK_STREAM) as client:
                client.settimeout(1);client.connect(socket)
                client.sendall(b'GET /check HTTP/1.1\r\nHost: guard\r\nX-Guard-IP: 127.0.0.1\r\nConnection: close\r\n\r\n')
                if b' 204 ' in client.recv(1024):break
        except OSError:pass
        time.sleep(.1)
    else:raise ValueError('HTTP protection socket unavailable')
    print('Guard request gate installed')

if __name__=='__main__':main()
