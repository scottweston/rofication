#!/usr/bin/env python3
import os
import time
import socket

while True:
    if not os.path.exists("/tmp/rofi_notification_daemon"):
        print(f"""{{"text": "error", "class": "critical", "tooltip": "Is rofication-daemon.py running? socket not found"}}""", flush=True)
        time.sleep(1)
        continue
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect("/tmp/rofi_notification_daemon")
        client.sendall(bytes("num",'utf-8'))
        val = client.recv(32)
        client.close()
        val = val.decode('utf-8')
        l = val.split('\n',2)
        # l[0] is the number of notifications
        # l[1] is the number of critical notifications
        if int(l[1]) > 0:
            crit=f'  {str(l[1])}'
        else:
            crit=''
        if int(l[0]) == 0 and int(l[1]) == 0:
            class_='none'
        elif int(l[0]) > 0 and int(l[1]) == 0:
            class_='normal'
        else:
            class_='critical'
        print(f"""{{"text": "{l[0]}{crit}", "class": "{class_}", "tooltip": "{l[0]} notifications\\n{l[1]} critical"}}""", flush=True)
    except Exception as e:
        print(f"""{{"text": "error", "class": "critical", "tooltip": "Is rofication-daemon.py running? {e}"}}""", flush=True)
    time.sleep(1)
