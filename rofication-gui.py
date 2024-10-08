#!/usr/bin/env python3
import re
import time
import socket
import struct
import subprocess
import jsonpickle
from dateutil.relativedelta import relativedelta
from gi.repository import GLib
from enum import Enum
from msg import Msg,Urgency

def linesplit(socket):
    buffer = socket.recv(16)
    buffer = buffer.decode("UTF-8")
    buffering = True
    while buffering:
        if '\n' in buffer:
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
	<i>Alt+r</i>: Reload			<i>Alt+a</i>:     Delete application notification</span>""";
rofi_command = [ 'rofi' , '-dmenu', '-p', 'Notifications:', '-markup', '-mesg', msg]

def strip_tags(value):
  "Return the given HTML with all tags stripped."
  return re.sub(r'<[^>]*?>', '', value)

def call_rofi(entries, additional_args=[]):
    additional_args.extend([ '-kb-custom-1', 'Alt+x',
                             '-kb-custom-2', 'Alt+Return',
                             '-kb-custom-3', 'Alt+r',
                             '-kb-custom-4', 'Alt+a',
                             '-kb-custom-5', 'Alt+X',
                             '-kb-custom-6', 'Alt+A',
                             '-markup-rows',
                             '-sep', '\3',
                             '-format', 'i',
                             '-l', f'{min(len(entries),5)}',
                             '-eh', '3',
							 '-i',
                             '-sync',
                             '-dynamic',
                             '-width', '-70' ])
    if len(entries) > 0:
        proc = subprocess.Popen(rofi_command+additional_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        for e in entries:
            proc.stdin.write((e).encode('utf-8'))
            proc.stdin.write(struct.pack('B', 3))
        proc.stdin.close()
        answer = proc.stdout.read().decode("utf-8")
        exit_code = proc.wait()
        # trim whitespace
        if answer == '':
            return None,exit_code
        else:
            return int(answer),exit_code
    else:
        return None,0


def send_command(cmd):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect("/tmp/rofi_notification_daemon")
    print("Send: {cmd}".format(cmd=cmd))
    client.send(bytes(cmd, 'utf-8'))
    client.close()


did = None
cont=True
while cont:
    cont=False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect("/tmp/rofi_notification_daemon")
    client.send(b"list",4)
    ids=[]
    entries=[]
    index=0
    urgent=[]
    low=[]
    args=[]
    for a in linesplit(client):
        if len(a) > 0:
            msg = jsonpickle.decode(a)
            #for key in msg.__dict__:
            #    print("{key} = {value}".format(key=key,value=msg.__dict__[key]))
            ids.append(msg)
            attrs = ['years', 'months', 'days', 'hours', 'minutes', 'seconds']
            human_readable = lambda delta: ['%d %s' % (getattr(delta, attr), attr if getattr(delta, attr) > 1 else attr[:-1])
                for attr in attrs if getattr(delta, attr)]
            mst = ("<b>{summ}</b>\n<small>{age} ago by {app}</small>".format(
                   summ=GLib.markup_escape_text(strip_tags(msg.summary)),
                   age=GLib.markup_escape_text(strip_tags(" ".join(human_readable(relativedelta(seconds=time.time()-msg.triggered))))),
                   app=GLib.markup_escape_text(strip_tags(msg.application))))
            if len(msg.body) > 0:
                mst+= "\n<i>{}</i>".format(GLib.markup_escape_text(strip_tags(msg.body.replace("\n"," "))))
            if len(msg.app_icon) > 0:
                mst += "\0icon\x1f{app_icon}".format(app_icon=msg.app_icon)

            entries.append(mst)
            if Urgency(msg.urgency) is Urgency.critical:
                urgent.append(str(index))
            if Urgency(msg.urgency) is Urgency.low:
                low.append(str(index))
            index+=1
    if len(urgent):
        args.append("-u")
        args.append(",".join(urgent))
    if len(low):
        args.append("-a")
        args.append(",".join(low))

    # Select previous selected row.
    if did != None:
        args.append("-selected-row")
        args.append(str(did))
    # Show rofi
    did,code = call_rofi(entries,args)
    print("{a},{b}".format(a=did,b=code))
    # Dismiss notification
    if did != None and (code == 10 or code == 14):
        send_command("del:{mid}".format(mid=ids[did].mid))
        cont=True
    # Seen notification
    elif did != None and code == 11:
        send_command("saw:{mid}".format(mid=ids[did].mid))
        cont=True
    elif did != None and code == 12:
        cont=True
    elif did != None and (code == 13 or code == 15):
        send_command("dela:{app}".format(app=ids[did].application))
        cont=True
