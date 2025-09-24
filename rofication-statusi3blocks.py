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
l = val.split('\n',2)
print(str(l[0]))
if int(l[1]) > 0:
    exit(33)
