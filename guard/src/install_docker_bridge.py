"""Install Guard's allowlisted Docker and SSH journal bridge on the host."""
import os
from pathlib import Path
import subprocess
import time

from docker_bridge import SOCKET


def main():
    if os.geteuid() != 0:
        raise SystemExit('Требуются права root на сервере')
    source = Path(__file__).with_name('docker_bridge.py').resolve()
    unit = f'''[Unit]
Description=Guard allowlisted host operations
After=docker.service
Requires=docker.service

[Service]
ExecStart=/usr/bin/python3 {source}
Restart=on-failure
RestartSec=2
RuntimeDirectory=guard-docker
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
RestrictAddressFamilies=AF_UNIX

[Install]
WantedBy=multi-user.target
'''
    path = Path('/etc/systemd/system/guard-docker-bridge.service')
    path.write_text(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'guard-docker-bridge'], check=True)
    subprocess.run(['systemctl', 'restart', 'guard-docker-bridge'], check=True)
    for _ in range(50):
        if Path(SOCKET).is_socket():
            return
        time.sleep(0.1)
    raise RuntimeError('Сокет диагностики Guard не появился')


if __name__ == '__main__':
    main()
