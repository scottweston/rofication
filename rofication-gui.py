#!/usr/bin/env python3
import re
import time
import socket
import struct
import subprocess
import jsonpickle
from rofication_config import load_config, resolve_socket_path
from dateutil.relativedelta import relativedelta
from gi.repository import GLib
from enum import Enum
from msg import Msg, Urgency

try:
    CONFIG = load_config()
    SOCKET_PATH = resolve_socket_path(CONFIG)
except Exception:
    CONFIG = {}
    SOCKET_PATH = resolve_socket_path({})


def linesplit(socket):
    buffer = socket.recv(16)
    buffer = buffer.decode("UTF-8")
    buffering = True
    while buffering:
        if "\n" in buffer:
            (line, buffer) = buffer.split("\n", 1)
            yield line
        else:
            more = socket.recv(16)
            more = more.decode("UTF-8")
            if not more:
                buffering = False
            else:
                buffer += more
    if buffer:
        yield buffer


msg = """<span font-size='small'>	<i>Alt+x</i>: Dismiss notification	<i>Alt+Enter</i>: Mark notification seen
	<i>Alt+r</i>: Reload			<i>Alt+a</i>:     Delete application notification
	<i>Alt+1</i>: Del &gt;1h ago		<i>Alt+2</i>:     Del &gt;8h ago
	<i>Alt+3</i>: Del &gt;24h ago		<i>Alt+z</i>:     Toggle time sort
	<i>Alt+m</i>: Toggle mute</span>"""
rofi_command = ["rofi", "-dmenu", "-p", "Notifications:", "-markup", "-mesg", msg]


def strip_tags(value):
    "Return the given HTML with all tags stripped."
    return re.sub(r"<[^>]*?>", "", value)


def call_rofi(entries, additional_args=[]):
    additional_args.extend(
        [
            "-kb-clear-line",
            "",
            "-kb-move-front",
            "",
            "-kb-custom-1",
            "Alt+x,Ctrl+x,Ctrl+X",
            "-kb-custom-2",
            "Alt+Return",
            "-kb-custom-3",
            "Alt+r",
            "-kb-custom-4",
            "Alt+a,Ctrl+a,Ctrl+A",
            "-kb-custom-5",
            "Alt+X",
            "-kb-custom-6",
            "Alt+A",
            "-kb-custom-7",
            "Alt+1,Ctrl+1",
            "-kb-custom-8",
            "Alt+2,Ctrl+2",
            "-kb-custom-9",
            "Alt+3,Ctrl+3",
            "-kb-custom-10",
            "Alt+z,Alt+Z",
            "-kb-custom-11",
            "Alt+m,Alt+M",
            "-markup-rows",
            "-sep",
            "\3",
            "-format",
            "i",
            "-l",
            f"{min(len(entries), 5)}",
            "-eh",
            "3",
            "-i",
            "-sync",
            "-dynamic",
            "-width",
            "-70",
        ]
    )
    if len(entries) > 0:
        proc = subprocess.Popen(
            rofi_command + additional_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        for e in entries:
            proc.stdin.write((e).encode("utf-8"))
            proc.stdin.write(struct.pack("B", 3))
        proc.stdin.close()
        answer = proc.stdout.read().decode("utf-8")
        exit_code = proc.wait()
        # trim whitespace
        if answer == "":
            return None, exit_code
        else:
            return int(answer), exit_code
    else:
        return None, 0


def send_command(cmd, expect_response=False):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)
    print("Send: {cmd}".format(cmd=cmd))
    client.send(bytes(cmd, "utf-8"))
    response = None
    if expect_response:
        chunks = []
        while True:
            data = client.recv(64)
            if not data:
                break
            chunks.append(data.decode("utf-8"))
        response = "".join(chunks).strip()
    client.close()
    return response


def set_dnd_state(enabled):
    """Best-effort DBus hooks for popular notification centers."""
    state_arg = "boolean:true" if enabled else "boolean:false"
    commands = [
        [
            "dbus-send",
            "--session",
            "--dest=org.erikreider.swaync",
            "/org/erikreider/swaync/cc",
            "org.erikreider.swaync.cc.SetDndState",
            state_arg,
        ],
        [
            "dbus-send",
            "--session",
            "--dest=org.dunstproject.cmd0",
            "/org/dunstproject/Command0",
            "org.dunstproject.cmd0.SetPaused",
            state_arg,
        ],
    ]
    for command in commands:
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


did = None
selected_mid = None
sort_descending = False
cont = True
while cont:
    cont = False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)
    client.send(b"list", 4)
    notifications = []
    for a in linesplit(client):
        if len(a) > 0:
            notifications.append(jsonpickle.decode(a))

    notifications.sort(
        key=lambda noti: getattr(noti, "triggered", 0), reverse=sort_descending
    )

    ids = []
    entries = []
    urgent = []
    low = []
    args = []
    for index, msg in enumerate(notifications):
        ids.append(msg)
        attrs = ["years", "months", "days", "hours", "minutes", "seconds"]
        human_readable = lambda delta: [
            "%d %s"
            % (
                getattr(delta, attr),
                attr if getattr(delta, attr) > 1 else attr[:-1],
            )
            for attr in attrs
            if getattr(delta, attr)
        ]
        mst = "<b>{summ}</b>\n<small>{age} ago by {app}</small>".format(
            summ=GLib.markup_escape_text(strip_tags(msg.summary)),
            age=GLib.markup_escape_text(
                strip_tags(
                    " ".join(
                        human_readable(
                            relativedelta(seconds=time.time() - msg.triggered)
                        )
                    )
                )
            ),
            app=GLib.markup_escape_text(strip_tags(msg.application)),
        )
        if len(msg.body) > 0:
            mst += "\n<i>{}</i>".format(
                GLib.markup_escape_text(strip_tags(msg.body.replace("\n", " ")))
            )
        if len(msg.app_icon) > 0:
            mst += "\0icon\x1f{app_icon}".format(app_icon=msg.app_icon)

        entries.append(mst)
        if Urgency(msg.urgency) is Urgency.critical:
            urgent.append(str(index))
        if Urgency(msg.urgency) is Urgency.low:
            low.append(str(index))
    if len(urgent):
        args.append("-u")
        args.append(",".join(urgent))
    if len(low):
        args.append("-a")
        args.append(",".join(low))

    if selected_mid is not None:
        for idx, msg in enumerate(ids):
            if msg.mid == selected_mid:
                args.append("-selected-row")
                args.append(str(idx))
                break
    # Show rofi
    did, code = call_rofi(entries, args)
    print("{a},{b}".format(a=did, b=code))
    selected_mid = ids[did].mid if did is not None else None
    # Dismiss notification
    if did is not None and (code == 10 or code == 14):
        send_command("del:{mid}".format(mid=ids[did].mid))
        cont = True
    # Seen notification
    elif did is not None and code == 11:
        send_command("saw:{mid}".format(mid=ids[did].mid))
        cont = True
    elif did is not None and code == 12:
        cont = True
    elif did is not None and (code == 13 or code == 15):
        send_command("dela:{app}".format(app=ids[did].application))
        cont = True
    elif code == 16:
        send_command("del-older-than:3600")  # 1 hour
        cont = True
    elif code == 17:
        send_command("del-older-than:28800")  # 8 hours
        cont = True
    elif code == 18:
        send_command("del-older-than:86400")  # 24 hours
        cont = True
    elif code == 19:
        sort_descending = not sort_descending
        cont = True
    elif code == 20:
        mute_state = send_command("mute", expect_response=True)
        if mute_state in ("0", "1"):
            set_dnd_state(mute_state == "1")
        cont = True
