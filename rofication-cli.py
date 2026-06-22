#!/usr/bin/env python3
import argparse
import json
import socket
import sys

import jsonpickle

from rofication_config import load_config, resolve_socket_path


def fetch_notifications(socket_path, command):
    """Fetch newline-delimited notifications from the daemon."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall(command.encode("utf-8"))

        response = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk

    notifications = []
    for line in response.splitlines():
        if line:
            notification = jsonpickle.decode(line.decode("utf-8"))
            notifications.append(vars(notification))
    return notifications


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Query the rofication daemon")
    parser.add_argument(
        "command",
        choices=("unread",),
        help="output unread notifications as JSON",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    socket_path = resolve_socket_path(load_config())

    try:
        notifications = fetch_notifications(socket_path, args.command)
    except (ConnectionError, OSError, ValueError) as exc:
        print(f"rofication-cli: {exc}", file=sys.stderr)
        return 1

    json.dump(notifications, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
