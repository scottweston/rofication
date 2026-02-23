#!/usr/bin/env python3
import socket

from rofication_config import load_config, resolve_socket_path


try:
    SOCKET_PATH = resolve_socket_path(load_config())
except Exception:
    SOCKET_PATH = resolve_socket_path({})
client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
client.connect(SOCKET_PATH)
client.sendall(bytes("num",'utf-8'))

val = client.recv(32)
val = val.decode('utf-8')
l = val.split('\n')
count = int(l[0]) if len(l) > 0 and l[0].isdigit() else 0
critical = int(l[1]) if len(l) > 1 and l[1].isdigit() else 0
muted = len(l) > 2 and l[2].strip() == "1"
mute_icon = " 🔇" if muted else ""
print(f"{count}{mute_icon}")
if critical > 0:
    exit(33)
