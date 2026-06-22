import importlib.util
import socket
import sys
import threading
from pathlib import Path

import jsonpickle

CLI_PATH = Path(__file__).parents[1] / "rofication-cli.py"
sys.path.insert(0, str(CLI_PATH.parent))

from msg import Msg


SPEC = importlib.util.spec_from_file_location("rofication_cli", CLI_PATH)
rofication_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rofication_cli)


def test_fetch_notifications_decodes_fragmented_response(tmp_path):
    socket_path = tmp_path / "daemon.sock"
    notification = Msg()
    notification.mid = 7
    notification.summary = "A notification ✓"
    payload = (jsonpickle.encode(notification) + "\n").encode("utf-8")
    received_command = []

    def serve():
        connection, _ = server.accept()
        with connection:
            received_command.append(connection.recv(64))
            midpoint = len(payload) // 2
            connection.sendall(payload[:midpoint])
            connection.sendall(payload[midpoint:])

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        server.listen(1)
        server_thread = threading.Thread(target=serve)
        server_thread.start()

        notifications = rofication_cli.fetch_notifications(str(socket_path), "unread")
        server_thread.join()

    assert received_command == [b"unread"]
    assert notifications[0]["mid"] == 7
    assert notifications[0]["summary"] == "A notification ✓"
    assert notifications[0]["read"] is False
