"""Maintenance mode without a restart: the server list says so and nobody can join (ops still can).

  sudo python3 maintenance.py on [--wait MINUTES]   waits until nobody is online (or refuses), then turns it on
  sudo python3 maintenance.py off                   restores the MiniMOTD file and turns the whitelist off again

"on" saves MiniMOTD main.conf to /opt/minecraft-backups/maintenance/minimotd-main.conf.before, swaps line2, reloads
MiniMOTD and runs `whitelist on`. A player who tries to join sees Minecraft's own "not white-listed" text: the client
translates it, so the server cannot reword it (a custom kick message needs the onboarding add-on).
"""
import re, shutil, socket, struct, sys, time
from pathlib import Path

ROOT = Path('/opt/minecraft')
FIFO = '/run/minecraft-console.fifo'
MOTD = ROOT / 'config/MiniMOTD/main.conf'
SAVED = Path('/opt/minecraft-backups/maintenance/minimotd-main.conf.before')
LINE2 = 'line2="<#FF5555>⚠ Maintenance:</#FF5555> <white>back in a few minutes</white>"'


def console(*commands):
    with open(FIFO, 'w') as fifo:
        for text in commands: fifo.write(text + '\n')


def varint(value):
    out = b''
    while True:
        b = value & 127; value >>= 7
        out += bytes([b | (128 if value else 0)])
        if not value: return out


def read_varint(sock):
    value = shift = 0
    while True:
        b = sock.recv(1)[0]; value |= (b & 127) << shift; shift += 7
        if not b & 128: return value


def online():
    """Players online by the server list ping on localhost (staff hidden by the add-on are not counted)."""
    with socket.create_connection(('127.0.0.1', 25565), 5) as s:
        packet = varint(0) + varint(777) + varint(9) + b'localhost' + struct.pack('>H', 25565) + varint(1)
        s.sendall(varint(len(packet)) + packet + b'\x01\x00')
        read_varint(s); read_varint(s); size = read_varint(s); data = b''
        while len(data) < size: data += s.recv(size - len(data))
    return int(re.search(rb'"online":\s*(\d+)', data).group(1))


def on(wait_minutes):
    if SAVED.exists(): raise SystemExit('Maintenance is already on (saved MOTD exists); run "off" first.')
    deadline = time.time() + wait_minutes * 60
    while online():
        if time.time() > deadline: raise SystemExit('Players are online; maintenance not started.')
        time.sleep(20)
    text = MOTD.read_text(encoding='utf-8')
    if len(re.findall(r'(?m)^\s*line2=.*$', text)) != 1: raise SystemExit('Unexpected MiniMOTD config')
    SAVED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MOTD, SAVED)
    MOTD.write_text(re.sub(r'(?m)^(\s*)line2=.*$', lambda m: m.group(1) + LINE2, text), encoding='utf-8')
    console('whitelist on', 'minimotd reload')
    print('Maintenance on: whitelist on, server list shows maintenance.')


def off():
    if SAVED.exists():
        shutil.copy2(SAVED, MOTD); SAVED.unlink()
    console('whitelist off', 'minimotd reload')
    print('Maintenance off: whitelist off, MOTD restored.')


if __name__ == '__main__':
    if sys.argv[1:2] == ['on']:
        on(int(sys.argv[3]) if sys.argv[2:3] == ['--wait'] else 0)
    elif sys.argv[1:2] == ['off']:
        off()
    else:
        raise SystemExit(__doc__)
