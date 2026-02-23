#!/usr/bin/env python3
import os
import time
import socket

from rofication_config import load_config, resolve_socket_path


try:
    SOCKET_PATH = resolve_socket_path(load_config())
except Exception:
    SOCKET_PATH = resolve_socket_path({})

while True:
    if not os.path.exists(SOCKET_PATH):
        print(f"""{{"text": "error", "class": "critical", "tooltip": "Is rofication-daemon.py running? socket not found"}}""", flush=True)
        time.sleep(1)
        continue
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.sendall(bytes("num",'utf-8'))
        val = client.recv(32)
        client.close()
        val = val.decode('utf-8')
        l = val.split('\n')
        # l[0] is the number of notifications
        # l[1] is the number of critical notifications
        # l[2] is 1 when muted, otherwise 0 (optional)
        count = int(l[0]) if len(l) > 0 and l[0].isdigit() else 0
        critical = int(l[1]) if len(l) > 1 and l[1].isdigit() else 0
        muted = len(l) > 2 and l[2].strip() == "1"
        mute_icon = " 🔇" if muted else ""
        if critical > 0:
            crit=f'  {str(critical)}'
        else:
            crit=''
        if count == 0 and critical == 0:
            class_='none'
        elif count > 0 and critical == 0:
            class_='normal'
        else:
            class_='critical'
        tooltip = f"{count} notifications\\n{critical} critical"
        if muted:
            tooltip += "\\nMuted"
        print(f"""{{"text": "{count}{mute_icon}{crit}", "class": "{class_}", "tooltip": "{tooltip}"}}""", flush=True)
    except Exception as e:
        print(f"""{{"text": "error", "class": "critical", "tooltip": "Is rofication-daemon.py running? {e}"}}""", flush=True)
    time.sleep(1)
