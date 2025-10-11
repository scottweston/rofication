#!/usr/bin/env python3
import jsonpickle
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import os
import threading
import time
import socket
import pygame
import re
import signal
import logging

from rofication_config import load_config, resolve_socket_path

try:
    import requests
except ImportError:  # pragma: no cover - best effort import
    requests = None

from msg import Msg, Urgency

event = threading.Event()

config = {}
ntfy_config = {}
ntfy_mirror_rules = []


def mirror_notification_to_ntfy(msg):
    if not ntfy_mirror_rules:
        return
    if requests is None:
        logging.debug("requests library missing; cannot mirror to ntfy")
        return

    host = ntfy_config.get("host", "https://ntfy.sh")
    if not host:
        logging.debug("ntfy host is not configured; skipping mirroring")
        return

    token = ntfy_config.get("token")
    summary = msg.summary or ""
    body = msg.body or ""
    application = msg.application or ""
    if msg.desktop_entry:
        application = f"{application},{msg.desktop_entry}"

    for rule in ntfy_mirror_rules:
        pattern = rule.get("regex")
        if not pattern:
            continue
        matches_summary = pattern.search(summary)
        matches_body = pattern.search(body) if body else False
        matches_application = pattern.search(application) if application else False
        if matches_summary or matches_body or matches_application:
            pattern_text = rule.get("pattern", "<unnamed>")
            logging.debug(
                f"ntfy mirror rule matched pattern '{pattern_text}' for application '{application}'"
            )
            topic = rule.get("topic")
            if not topic:
                logging.debug("Matched ntfy rule without topic; skipping")
                continue

            topic = topic.lstrip("/")
            url = f"{host.rstrip('/')}/{topic}"

            headers = {
                "Title": summary,
            }

            if token:
                headers["Authorization"] = f"Bearer {token}"

            priority = rule.get("priority")
            if priority:
                headers["Priority"] = str(priority)

            tags = rule.get("tags")
            if tags:
                if isinstance(tags, (list, tuple)):
                    headers["Tags"] = ",".join(tags)
                else:
                    headers["Tags"] = str(tags)

            message_body = body if body else summary

            try:
                response = requests.post(
                    url, data=message_body, headers=headers, timeout=5
                )
                response.raise_for_status()
                logging.info(f"Mirrored notification to ntfy topic '{topic}'")
            except Exception as exc:
                logging.warning(
                    f"Failed to mirror notification to ntfy topic '{topic}': {exc}"
                )
            finally:
                return


class Rofication(threading.Thread):
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.notification_queue_lock = threading.Lock()
        self.notification_queue = []
        self.last_id = 0
        self.server = None
        cache_dir = f"{os.environ['HOME']}/.cache/rofication"
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        super().__init__()

    def cleanup_socket(self):
        try:
            if self.socket_path and os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logging.warning("Failed to remove socket %s: %s", self.socket_path, exc)

    def prepare_socket(self):
        if not self.socket_path:
            raise RuntimeError("Socket path is not configured")
        if os.path.exists(self.socket_path):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as check_sock:
                    check_sock.connect(self.socket_path)
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                self.cleanup_socket()
            else:
                raise RuntimeError(
                    f"Socket path {self.socket_path} already in use; is another daemon running?"
                )

    def load(self):
        logging.debug("Loading rofication")
        try:
            with open(f"{os.environ['HOME']}/.cache/rofication/not.json", "r") as f:
                self.notification_queue = jsonpickle.decode(f.read())
        except:
            pass

        for noti in self.notification_queue:
            noti.notid = -1
            if self.last_id < noti.mid:
                self.last_id = int(noti.mid)
        logging.debug("Found last id: %s", self.last_id)

    def save(self):
        logging.debug("Saving rofication")
        try:
            with open(f"{os.environ['HOME']}/.cache/rofication/not.json", "w") as f:
                f.write(jsonpickle.encode(self.notification_queue))
        except:
            logging.warn("Failed to store queue.")

    """
    This function updates the queue. E.g. removes popups that are expired
    and allowed to expire
    """

    def update_queue(self):
        with self.notification_queue_lock:
            now = time.time()
            n = [
                n
                for n in self.notification_queue
                if n.application in allowed_expire_app
                and n.deadline > 0
                and n.deadline < now
            ]
            for no in n:
                logging.debug("{mid} expired.".format(mid=no.mid))
                self.notification_queue.remove(no)

    def remove_notification(self, id):
        logging.debug("Removing: {}".format(id))
        with self.notification_queue_lock:
            n = [n for n in self.notification_queue if n.notid == id]
            for no in n:
                logging.debug(
                    "Closing: {id}:{sum}".format(id=no.mid, sum=no.application)
                )

    def add_notification(self, notif):
        with self.notification_queue_lock:
            if notif.application in single_notification_app:
                n = [
                    n
                    for n in self.notification_queue
                    if n.application == notif.application
                ]
                for no in n:
                    self.notification_queue.remove(no)

            self.notification_queue.append(notif)

    """
        Communication command.
    """

    def communication_command_send_list(self, connection):
        with self.notification_queue_lock:
            i = 0
            for noti in self.notification_queue:
                connection.send(bytes(jsonpickle.encode(noti), "utf-8"))
                connection.send(b"\n")
                i += 1

    def communication_command_delete(self, connection, arg):
        with self.notification_queue_lock:
            for noti in self.notification_queue:
                if noti.mid == int(arg):
                    self.notification_queue.remove(noti)
                    break

    def communication_command_delete_apps(self, connection, arg):
        remove_q = []
        with self.notification_queue_lock:
            for noti in self.notification_queue:
                if noti.application == arg:
                    remove_q.append(noti)
            for noti in remove_q:
                self.notification_queue.remove(noti)

    def communication_command_saw(self, connection, arg):
        with self.notification_queue_lock:
            for noti in self.notification_queue:
                if noti.mid == int(arg):
                    noti.urgency = int(Urgency.normal)
                    break

    def communication_command_delete_similar(self, connection, arg):
        with self.notification_queue_lock:
            application = None
            for noti in self.notification_queue:
                if noti.mid == int(arg):
                    application = noti.application
                    break
            if application:
                remove_q = []
                for noti in self.notification_queue:
                    if noti.application == application:
                        remove_q.append(noti)
                for noti in remove_q:
                    self.notification_queue.remove(noti)

    def communication_command_num(self, connection):
        with self.notification_queue_lock:
            u = [n for n in self.notification_queue if n.urgency == Urgency.critical]
            mstr = "{lent}\n{ul}".format(
                lent=len(self.notification_queue), ul=str(len(u))
            )
            connection.send(bytes(mstr, "utf-8"))

    def run(self):
        server = None
        try:
            self.prepare_socket()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server = server
            server.bind(self.socket_path)
            server.listen(1)
            server.settimeout(1)
        except Exception as exc:
            logging.error("Failed to start rofication: %s", exc)
            self.cleanup_socket()
            os._exit(1)

        while not event.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if event.is_set():
                    break
                logging.error("Socket accept failed: %s", exc)
                continue

            with connection:
                self.update_queue()
                try:
                    raw_data = connection.recv(1024)
                except OSError as exc:
                    logging.warning("Failed to receive data from client: %s", exc)
                    continue

                if not raw_data:
                    continue

                try:
                    data = raw_data.decode("utf-8")
                except UnicodeDecodeError:
                    logging.warning("Received undecodable data from client")
                    continue

                data = data.split("\x00", 1)[0]
                data = data.strip("\r\n")

                command = ""
                argument = ""
                if data:
                    parts = data.split(":", 1)
                    command = parts[0]
                    if len(parts) > 1:
                        argument = parts[1].strip()
                        if "\x00" in argument:
                            argument = argument.split("\x00", 1)[0]

                if command == "num":
                    self.communication_command_num(connection)
                elif command == "list":
                    self.communication_command_send_list(connection)
                elif command == "del":
                    if argument:
                        self.communication_command_delete(connection, argument)
                    else:
                        logging.warning("Received 'del' command without argument")
                elif command == "dels":
                    if argument:
                        self.communication_command_delete_similar(connection, argument)
                    else:
                        logging.warning("Received 'dels' command without argument")
                elif command == "dela":
                    if argument:
                        self.communication_command_delete_apps(connection, argument)
                    else:
                        logging.warning("Received 'dela' command without argument")
                elif command == "saw":
                    if argument:
                        self.communication_command_saw(connection, argument)
                    else:
                        logging.warning("Received 'saw' command without argument")

        if server is not None:
            server.close()
        self.cleanup_socket()


"""
    DBUS Notification Listener and Fetcher.
"""


class NotificationFetcher(dbus.service.Object):
    _id = 0
    _rofication = None
    _last_sound_time = 0

    @dbus.service.method(
        "org.freedesktop.Notifications", in_signature="susssasa{ss}i", out_signature="u"
    )
    def Notify(
        self,
        app_name,
        notification_id,
        app_icon,
        summary,
        body,
        actions,
        hints,
        expire_timeout,
    ):
        msg = Msg()
        # find id.
        self._id += 1
        msg.application = str(app_name)
        msg.notid = notification_id
        msg.mid = self._id
        msg.summary = str(summary)
        msg.body = str(body)
        msg.app_icon = str(app_icon)
        msg.triggered = time.time()
        msg.desktop_entry = hints.get("desktop-entry", "")

        logging.debug(
            "Incoming notification | application='%s' summary='%s' body='%s' app_icon='%s' desktop-entry='%s'",
            msg.application,
            msg.summary,
            msg.body,
            msg.app_icon,
            msg.desktop_entry,
        )

        if int(expire_timeout) > 0:
            msg.deadline = time.time() + int(expire_timeout) / 1000.0
        if "urgency" in hints:
            msg.urgency = int(hints["urgency"])

        # check if summary has been silenced, regex matching
        silence = False
        if msg.application in sound_alerts or "sound-file" in hints:
            if silenced_regexes:
                for regex in silenced_regexes:
                    logging.debug(
                        "Checking: {regex} against {sum}".format(
                            regex=regex, sum=msg.summary
                        )
                    )
                    if re.search(regex, msg.summary):
                        logging.debug("Silencing: {regex}".format(regex=regex))
                        silence = True
                        msg.summary = "🔇 {sum}".format(sum=msg.summary)
                        break
                    else:
                        logging.debug("Not silencing: {regex}".format(regex=regex))
            if not silence:
                if msg.application in sound_alerts:
                    msg.sound = sound_alerts[msg.application]
                else:
                    msg.sound = str(hints["sound-file"])
                if os.path.isfile(msg.sound):
                    my_sound = pygame.mixer.Sound(msg.sound)

                    # Add cooldown timer for sound notifications
                    current_time = time.time()
                    last_sound_time = self._last_sound_time
                    sound_cooldown = config.get(
                        "sound_cooldown", 10
                    )  # Default cooldown: 10 seconds

                    if current_time - last_sound_time >= sound_cooldown:
                        my_sound.play()
                        self._last_sound_time = current_time
                    else:
                        logging.debug(
                            f"Sound notification throttled (cooldown: {sound_cooldown}s)"
                        )
        else:
            logging.debug(
                f"No sound file found in hints or configured for {msg.application}."
            )

        mirror_notification_to_ntfy(msg)

        self._rofication.add_notification(msg)
        return notification_id

    @dbus.service.method(
        "org.freedesktop.Notifications", in_signature="", out_signature="as"
    )
    def GetCapabilities(self):
        return ("body", "sound")

    @dbus.service.signal("org.freedesktop.Notifications", signature="uu")
    def NotificationClosed(self, id_in, reason_in):
        _rofication.remove_notification(id_in)
        pass

    @dbus.service.method(
        "org.freedesktop.Notifications", in_signature="u", out_signature=""
    )
    def CloseNotification(self, id):
        _rofication.remove_notification(id)
        pass

    @dbus.service.method(
        "org.freedesktop.Notifications", in_signature="", out_signature="ssss"
    )
    def GetServerInformation(self):
        return ("rofication", "http://gmpclient.org/", "0.0.1", "1")


"""
    Main function
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s"
    )

    config = load_config()

    try:
        socket_path = resolve_socket_path(config, ensure_dir=True)
    except Exception as exc:
        logging.error("Failed to use configured socket path: %s", exc)
        socket_path = resolve_socket_path({}, ensure_dir=True)

    logging.info("Using socket path %s", socket_path)

    rofication = Rofication(socket_path)

    single_notification_app = config.get("single_notification_app", [])
    allowed_expire_app = config.get("allowed_expire_app", [])
    silenced_regexes = config.get("silenced_regexes", [])
    sound_alerts = config.get("sound_alerts", {})
    ntfy_config = config.get("ntfy", {}) or {}

    raw_rules = config.get("ntfy_mirror", []) or []
    compiled_rules = []
    for rule in raw_rules:
        pattern_text = rule.get("regex")
        topic = rule.get("topic")
        if not pattern_text or not topic:
            logging.warning(
                "Skipping ntfy mirror rule without regex or topic: %s", rule
            )
            continue
        try:
            compiled_pattern = re.compile(pattern_text)
        except re.error as exc:
            logging.warning("Invalid ntfy mirror regex '%s': %s", pattern_text, exc)
            continue

        compiled_rule = {
            "regex": compiled_pattern,
            "pattern": pattern_text,
            "topic": topic,
        }

        if "priority" in rule:
            compiled_rule["priority"] = rule["priority"]
        if "tags" in rule:
            compiled_rule["tags"] = rule["tags"]

        compiled_rules.append(compiled_rule)

    ntfy_mirror_rules = compiled_rules

    main_loop = None

    def signal_handler(signum, frame):
        logging.info("Signal handler called with signal: %s", signum)
        event.set()
        if rofication.server is not None:
            try:
                rofication.server.close()
            except Exception:
                pass
        if main_loop is not None:
            main_loop.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)

    pygame.init()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    session_bus = dbus.SessionBus()
    name = dbus.service.BusName("org.freedesktop.Notifications", session_bus)
    nf = NotificationFetcher(session_bus, "/org/freedesktop/Notifications")

    nf._rofication = rofication
    rofication.load()
    nf._id = rofication.last_id

    rofication.start()

    try:
        main_loop = GLib.MainLoop()
        main_loop.run()
    except Exception as exc:
        logging.info("Main loop exited with exception: %s", exc)
        event.set()
    finally:
        event.set()
        rofication.join()
        rofication.save()
        rofication.cleanup_socket()
