"""EQ Triage: on-screen HP and charm break alerts for Project Quarm, fed by Zeal's named pipe.

Author: SEBIK (EUROPA)
"""

import argparse
import codecs
import csv
import ctypes
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

APP_NAME = 'EQ Triage'
APP_ID = 'SebikEuropa.EQTriage'
PIPE_DIR = '\\\\.\\pipe\\'
PIPE_PREFIX = 'zeal_'
LOG_TYPE = 0
GAUGE_TYPE = 2
PLAYER_TYPE = 3
RAID_TYPE = 5
GROUP_TYPE = 6
MEMBER_GAUGES = range(11, 16)
PLAYER_PET_GAUGE = 16
PET_GAUGE_OFFSET = 6
GAUGE_FULL = 1000
MISSING_FRAMES = 2
ALERT_SECONDS = 6.0
DEATH_SECONDS = 10.0
WATCH_SECONDS = 30.0
AGGRO_SECONDS = 6.0
RECHARM_GRACE_SECONDS = 2.0
STALE_SECONDS = 2.0
MIN_BREAK_HP = 10
OUT_OF_RANGE_TAG = ' (OOR)'
PET_BREAK_PREFIX = 'PET BREAK '
UNTAGGED_PREFIXES = ('DEAD ', PET_BREAK_PREFIX)
SCAN_SECONDS = 5.0
ZEAL_GRACE_SECONDS = 20.0
EQ_PROCESS = 'eqgame.exe'
STATUS_OK = '#3fb950'
STATUS_WARN = '#e3a008'
STATUS_WAIT = '#8a93a3'
REFRESH_MS = 100
STATUS_MS = 1000
CONTROL_WIDTH = 340
PIN_LIST_HEIGHT = 90
MAX_BUFFER = 1_000_000
CHARMER_COLOR = '#ff0000'
LOW_HP_COLOR = '#ffff00'
CRITICAL_HP_COLOR = '#ff0000'
DEATH_COLOR = '#b877ff'
# Chat lines can carry a leading timestamp; mobs share the wording, so matches are checked against known players.
OTHER_DIED = re.compile(r'(?:^|\] )([A-Z][a-z]+) (?:has been slain by .+|died\.)$')
YOU_DIED = re.compile(r'(?:^|\] )You (?:have been slain by .+|died\.)$')
PINNED_COLOR = '#e8e8e8'
STALE_COLOR = '#8a8a8a'
EMPTY_ROW = ('', '', '', LOW_HP_COLOR, None)
VERBOSE_ROW = ('Type ', '/pipeverbose on', '', STALE_COLOR, None)
PREVIEW_SECONDS = 10.0
# One of each row type, so text size, width and position can be judged before any real data arrives.
SAMPLE_ROWS = [
    ('', 'Sebik', ' 95%', PINNED_COLOR, None),
    ('!! ', 'Sebik', ' 80%', CHARMER_COLOR, None),
    (PET_BREAK_PREFIX, 'Sebik', '', CHARMER_COLOR, None),
    ('DEAD ', 'Sebik', '', DEATH_COLOR, None),
    ('', 'Sebik', ' 22%', CRITICAL_HP_COLOR, None),
    ('', 'Sebik', ' pet 41%', LOW_HP_COLOR, None),
    ('', 'Sebik', f' 38%{OUT_OF_RANGE_TAG}', LOW_HP_COLOR, None),
]
ROWS = 10
SAMPLE_ROWS += [EMPTY_ROW] * (ROWS - len(SAMPLE_ROWS))
DEFAULT_Y = 150
FONT_FAMILY = 'Segoe UI'
TITLE_POINT_SIZE = 8
HEADER_HEIGHT = 20
PADDING = 6
PIN_WIDTH = 14
ROW_GAP = 4
CORNER_RADIUS = 3
PANEL_COLOR = QColor(14, 18, 26, 180)
HEADER_COLOR = QColor(255, 255, 255, 20)
EDGE_COLOR = QColor(255, 255, 255, 50)
DIVIDER_COLOR = QColor(255, 255, 255, 22)
PIN_COLOR = QColor(255, 255, 255, 230)
PIN_HINT_COLOR = QColor(255, 255, 255, 80)
HEADER_TEXT_COLOR = QColor(255, 255, 255, 190)
SHADOW_COLOR = QColor(0, 0, 0, 210)
# A one-file build unpacks into a temp directory, so the position is kept next to the exe instead.
APP_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
POSITION_FILE = os.path.join(APP_DIR, 'position.json')
PINS_FILE = os.path.join(APP_DIR, 'pins.json')
DOCS_URL = 'https://github.com/CopperGlade/EQTriage#readme'
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
# Setting key -> (default, minimum, maximum, label in the control window, suffix shown after the value).
SETTINGS = {
    'low_hp': (50, 1, 100, 'List players below', '% HP'),
    'critical_hp': (30, 1, 100, 'Show in red below', '% HP'),
    'range': (100, 10, 1000, 'Out of range beyond', ' units'),
    'font_size': (10, 7, 20, 'Text size', ' pt'),
    # Counted in characters rather than pixels, so the overlay widens with the text size and names keep fitting.
    'width': (19, 12, 40, 'Overlay width', ' characters'),
}

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

state_lock = threading.Lock()
members = {}
pet_hp = {}
charm_breaks = {}
deaths = {}
own_locations = {}
member_locations = {}
aggro = {}
hp_seen = {}
connected = set()
pipe_characters = {}
member_messages = {}
eq_started = None
verbose_missing = False


def is_watched(name, now):
    broke = charm_breaks.get(name)
    if not broke:
        return False
    return now - broke[1] < WATCH_SECONDS or now - aggro.get(name, -AGGRO_SECONDS) < AGGRO_SECONDS


def location(loc):
    return loc['x'], loc['y'], loc['z']


def handle_player(data, pipe_name):
    if 'location' in data:
        with state_lock:
            own_locations[pipe_name] = (location(data['location']), time.monotonic())


def handle_members(entries, pipe_name):
    global verbose_missing
    now = time.monotonic()
    with state_lock:
        # Zeal only sends group and raid data while you are in one, so this also tells whether you are grouped.
        if entries:
            member_messages[pipe_name] = now
        for entry in entries:
            # A member only has a location while in the reporting client's zone, so it is kept per client.
            if 'loc' in entry:
                member_locations[(pipe_name, entry['name'])] = (location(entry['loc']), now)
            if 'hp_current' not in entry:
                # Raid members outside the zone carry no spawn_id and never have HP; one in the zone
                # without HP means /pipeverbose is off.
                if 'spawn_id' in entry:
                    if not verbose_missing:
                        print('Group/raid data has no HP. Enable it in game with: /pipeverbose on')
                    verbose_missing = True
                continue
            verbose_missing = False
            name, current, maximum = entry['name'], entry['hp_current'], entry['hp_max']
            if maximum <= 0:
                continue
            members[name] = (current * 100 / maximum, now)
            # Compared per client: another client's view can lag, and regen then looks like damage.
            previous = hp_seen.get((pipe_name, name))
            hp_seen[(pipe_name, name)] = (current, maximum)
            if previous and previous[1] == maximum and current < previous[0] and is_watched(name, now):
                if now - aggro.get(name, -AGGRO_SECONDS) >= AGGRO_SECONDS:
                    print(f'AGGRO {name} took damage after a charm break ({previous[0]} -> {current} HP)')
                aggro[name] = now


def handle_log(entry, character):
    text = entry.get('text', '').strip()
    if YOU_DIED.search(text):
        name = character
    else:
        match = OTHER_DIED.search(text)
        name = match.group(1) if match else None
    if not name:
        return
    now = time.monotonic()
    with state_lock:
        if name not in members and name != character:
            return
        if now - deaths.get(name, -DEATH_SECONDS) >= DEATH_SECONDS:
            print(f'DEAD {name}: {text}')
        deaths[name] = now


class PetWatcher:
    def __init__(self, pipe_name, dump):
        self.pipe_name = pipe_name
        self.min_break_value = MIN_BREAK_HP * GAUGE_FULL / 100
        self.dump = dump
        self.pets = {}
        self.last_gauges = {}

    def handle_gauges(self, gauges, character):
        by_type = {g['type']: (g['text'], g['value']) for g in gauges}
        if self.dump:
            self.print_changes(by_type)

        current = {}
        for member_type in MEMBER_GAUGES:
            owner, owner_value = by_type.get(member_type, ('', 0))
            owner = owner.rstrip('*')
            if owner:
                pet_name, pet_value = by_type.get(member_type + PET_GAUGE_OFFSET, ('', 0))
                current[owner] = (pet_name, pet_value, owner_value)
        self.record_pet_hp(current, character, by_type.get(PLAYER_PET_GAUGE, ('', 0))[1])

        for owner, (pet_name, pet_value, owner_value) in current.items():
            if pet_value > 0 or pet_name:
                self.pets[owner] = {'name': pet_name, 'value': pet_value, 'missing': 0}
                self.clear_if_recharmed(owner)
                continue
            pet = self.pets.get(owner)
            if not pet:
                continue
            pet['missing'] += 1
            if pet['missing'] < MISSING_FRAMES:
                continue
            del self.pets[owner]
            if owner_value > 0 and pet['value'] >= self.min_break_value:
                self.report_break(owner, pet)

        for owner in self.pets.keys() - current.keys():
            del self.pets[owner]

    def record_pet_hp(self, current, character, own_pet_value):
        now = time.monotonic()
        values = {owner: pet_value for owner, (_, pet_value, _) in current.items()}
        if character:
            values[character] = own_pet_value
        with state_lock:
            for owner, value in values.items():
                if value > 0:
                    pet_hp[owner] = (value * 100 / GAUGE_FULL, now)

    def report_break(self, owner, pet):
        now = time.monotonic()
        with state_lock:
            if now - charm_breaks.get(owner, (None, -ALERT_SECONDS))[1] < ALERT_SECONDS:
                return
            charm_breaks[owner] = (pet['name'], now)
        hp = pet['value'] * 100 / GAUGE_FULL
        print(f'PET BREAK? {owner} lost {pet["name"] or "pet"} at {hp:.0f}% ({self.pipe_name})')

    def clear_if_recharmed(self, owner):
        with state_lock:
            broke = charm_breaks.get(owner)
            if broke and time.monotonic() - broke[1] >= RECHARM_GRACE_SECONDS:
                del charm_breaks[owner]
                aggro.pop(owner, None)

    def print_changes(self, by_type):
        for member_type in MEMBER_GAUGES:
            for gauge_type in (member_type, member_type + PET_GAUGE_OFFSET):
                gauge = by_type.get(gauge_type)
                if gauge != self.last_gauges.get(gauge_type):
                    print(f'{self.pipe_name} gauge {gauge_type}: {gauge}')
                    self.last_gauges[gauge_type] = gauge


def read_pipe(name, args):
    decoder = json.JSONDecoder()
    utf8 = codecs.getincrementaldecoder('utf-8')(errors='replace')
    watcher = PetWatcher(name, args.dump)
    buf = ''
    try:
        with open(PIPE_DIR + name, 'rb', buffering=0) as pipe:
            print(f'connected {name}')
            while chunk := pipe.read(65536):
                buf += utf8.decode(chunk)
                while buf:
                    buf = buf.lstrip()
                    try:
                        message, end = decoder.raw_decode(buf)
                    except json.JSONDecodeError:
                        break
                    buf = buf[end:]
                    character = message.get('character')
                    if character and pipe_characters.get(name) != character:
                        with state_lock:
                            pipe_characters[name] = character
                    if message.get('type') in (GROUP_TYPE, RAID_TYPE):
                        handle_members(json.loads(message['data']), name)
                    elif message.get('type') == GAUGE_TYPE:
                        watcher.handle_gauges(json.loads(message['data']), message.get('character', ''))
                    elif message.get('type') == PLAYER_TYPE:
                        handle_player(json.loads(message['data']), name)
                    elif message.get('type') == LOG_TYPE:
                        handle_log(json.loads(message['data']), message.get('character', ''))
                if len(buf) > MAX_BUFFER:
                    buf = ''
    except OSError as error:
        print(f'{name}: {error}')
    finally:
        with state_lock:
            connected.discard(name)
            pipe_characters.pop(name, None)
        print(f'disconnected {name}')


def running_eq_pids():
    try:
        result = subprocess.run(
            ['tasklist', '/FI', f'IMAGENAME eq {EQ_PROCESS}', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=SCAN_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    rows = csv.reader(result.stdout.splitlines())
    return {int(row[1]) for row in rows if len(row) > 1 and row[0].lower() == EQ_PROCESS}


def track_eq_processes():
    global eq_started
    pids = running_eq_pids()
    now = time.monotonic()
    with state_lock:
        if pids is None:
            eq_started = None
        else:
            eq_started = {pid: (eq_started or {}).get(pid, now) for pid in pids}


def scan_pipes(args):
    while True:
        track_eq_processes()
        try:
            names = [n for n in os.listdir(PIPE_DIR) if n.startswith(PIPE_PREFIX)]
        except OSError:
            names = []
        for name in names:
            with state_lock:
                if name in connected:
                    continue
                connected.add(name)
            threading.Thread(target=read_pipe, args=(name, args), daemon=True).start()
        time.sleep(SCAN_SECONDS)


def hp_color(pct, settings):
    return CRITICAL_HP_COLOR if pct < settings['critical_hp'] else LOW_HP_COLOR


def below(readings, threshold, now):
    return sorted(
        (pct, name) for name, (pct, seen) in readings.items()
        if pct < threshold and now - seen < STALE_SECONDS
    )


def status_row(name, hp, dead, attacked, breaks, settings):
    if name in dead:
        return ('DEAD ', name, '', DEATH_COLOR, name)
    pct = hp.get(name)
    suffix = '' if pct is None else f' {int(pct)}%'
    if name in attacked:
        return ('!! ', name, suffix, CHARMER_COLOR, name)
    if name in breaks:
        return (PET_BREAK_PREFIX, name, '', CHARMER_COLOR, name)
    if pct is None:
        return ('', name, ' --', STALE_COLOR, name)
    return ('', name, suffix, hp_color(pct, settings) if pct < settings['low_hp'] else PINNED_COLOR, name)


def out_of_range(name, origin, max_range, now):
    own = own_locations.get(origin)
    if not own or now - own[1] >= STALE_SECONDS:
        return False
    theirs = member_locations.get((origin, name))
    if not theirs or now - theirs[1] >= STALE_SECONDS:
        return True
    return math.dist(own[0], theirs[0]) > max_range


def tagged_out_of_range(row):
    prefix, name, suffix, color, key = row
    return prefix, name, suffix + OUT_OF_RANGE_TAG, color, key


def alert_rows(settings, pinned, origin=None):
    now = time.monotonic()
    with state_lock:
        far = {name for name in members if out_of_range(name, origin, settings['range'], now)}
        low = below(members, settings['low_hp'], now)
        low_pets = below(pet_hp, settings['low_hp'], now)
        hp = {name: pct for name, (pct, seen) in members.items() if now - seen < STALE_SECONDS}
        dead = sorted(name for name, at in deaths.items() if now - at < DEATH_SECONDS)
        attacked = sorted(
            (name for name, hit in aggro.items() if now - hit < AGGRO_SECONDS and name not in dead),
            key=lambda n: hp.get(n, 100),
        )
        breaks = [
            owner for owner, (_, at) in charm_breaks.items()
            if now - at < ALERT_SECONDS and owner not in attacked and owner not in dead
        ]
    # Each row is (prefix, name, suffix, color, pin key). Only the name is shortened when a row is too wide,
    # and the pin key is the player a click on the row's pin toggles (None for pets and empty rows).
    flagged = [name for name in attacked + breaks + dead if name not in pinned]
    rows = [status_row(name, hp, dead, attacked, breaks, settings) for name in pinned + flagged]
    shown = set(pinned) | set(flagged)
    players = [(pct, name, '', name) for pct, name in low if name not in shown]
    pets = [(pct, owner, ' pet', None) for pct, owner in low_pets]
    rows += [
        ('', name, f'{label} {int(pct)}%', hp_color(pct, settings), key)
        for pct, name, label, key in sorted(players + pets, key=lambda row: row[:3])
    ]
    rows = [
        tagged_out_of_range(row) if row[4] in far and row[0] not in UNTAGGED_PREFIXES else row for row in rows
    ]
    if verbose_missing:
        rows.insert(0, VERBOSE_ROW)
    return rows[:ROWS] + [EMPTY_ROW] * (ROWS - len(rows))


def load_json(path):
    try:
        with open(path, encoding='utf-8') as file:
            return json.load(file)
    except (OSError, ValueError):
        return None


def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file)
    except OSError as error:
        print(f'could not save {os.path.basename(path)}: {error}')


def load_position():
    position = load_json(POSITION_FILE)
    try:
        return int(position['x']), int(position['y'])
    except (KeyError, TypeError, ValueError):
        return None


def save_position(x, y):
    save_json(POSITION_FILE, {'x': x, 'y': y})


def load_pins():
    pins = load_json(PINS_FILE)
    if not isinstance(pins, list):
        return []
    return list(dict.fromkeys(name for name in pins if isinstance(name, str)))[:ROWS]


def load_settings():
    saved = load_json(SETTINGS_FILE)
    saved = saved if isinstance(saved, dict) else {}
    settings = {}
    for key, (default, minimum, maximum, _, _) in SETTINGS.items():
        value = saved.get(key)
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        settings[key] = min(max(int(value), minimum), maximum) if valid else default
    settings['critical_hp'] = min(settings['critical_hp'], settings['low_hp'])
    return settings


class TriageWindow(QWidget):
    def __init__(self, settings):
        # A tool window, like NAG's overlays: Windows leaves it out of virtual desktops, so it floats over EQ
        # on every desktop. The taskbar button belongs to ControlWindow instead.
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.settings = settings
        self.origin = None
        self.preview_until = 0.0
        self.pinned = load_pins()
        self.rows = [EMPTY_ROW] * ROWS
        self.title_font = QFont(FONT_FAMILY, TITLE_POINT_SIZE, QFont.Bold)
        self.apply_font()
        self.drag_offset = None
        self.passthrough = None
        self.previous_foreground = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def apply_font(self):
        self.row_font = QFont(FONT_FAMILY, self.settings['font_size'], QFont.DemiBold)
        self.metrics = QFontMetrics(self.row_font)
        self.row_height = self.metrics.height() + ROW_GAP
        self.text_width = self.metrics.horizontalAdvance('0') * self.settings['width']
        self.pin_left = PADDING + self.text_width
        self.setFixedSize(
            self.pin_left + PIN_WIDTH + PADDING, HEADER_HEIGHT + ROWS * self.row_height + ROW_GAP
        )
        self.update()

    def default_position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        return screen.x() + (screen.width() - self.width()) // 2, screen.y() + DEFAULT_Y

    def reset_position(self):
        self.move(*self.default_position())
        save_position(self.x(), self.y())

    def start(self):
        ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self.set_ex_style(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, True)
        self.timer.start(REFRESH_MS)

    def hwnd(self):
        return ctypes.c_void_p(int(self.winId()))

    def set_ex_style(self, flags, enabled):
        user32 = ctypes.windll.user32
        hwnd = self.hwnd()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | flags if enabled else style & ~flags)

    def take_focus(self):
        # EQ reads the mouse through DirectInput while it is the foreground window, so a drag
        # would also turn the camera. Taking the foreground for the drag cuts EQ off from the mouse.
        user32 = ctypes.windll.user32
        self.previous_foreground = user32.GetForegroundWindow()
        self.set_ex_style(WS_EX_NOACTIVATE, False)
        user32.SetForegroundWindow(self.hwnd())

    def return_focus(self):
        self.set_ex_style(WS_EX_NOACTIVATE, True)
        if self.previous_foreground:
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(self.previous_foreground))
        self.previous_foreground = None

    def refresh(self):
        rows = self.current_rows()
        cursor = self.mapFromGlobal(QCursor.pos())
        if rows != self.rows:
            self.rows = rows
            self.update()
        over_pin = self.pin_key_at(cursor) is not None
        over_header = self.rect().contains(cursor) and cursor.y() < HEADER_HEIGHT
        self.setCursor(Qt.PointingHandCursor if over_pin else Qt.SizeAllCursor)
        self.set_passthrough(self.drag_offset is None and not over_header and not over_pin)
        ctypes.windll.user32.SetWindowPos(
            self.hwnd(), ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )

    def pin_key_at(self, pos):
        if pos.x() < self.pin_left or pos.x() >= self.width() or pos.y() < HEADER_HEIGHT:
            return None
        index = int((pos.y() - HEADER_HEIGHT) // self.row_height)
        return self.rows[index][4] if index < ROWS else None

    def set_pinned(self, names):
        self.pinned = list(dict.fromkeys(names))[:ROWS]
        save_json(PINS_FILE, self.pinned)
        self.redraw()

    def toggle_pin(self, name):
        self.set_pinned([n for n in self.pinned if n != name] if name in self.pinned else self.pinned + [name])

    def redraw(self):
        self.rows = self.current_rows()
        self.update()

    def current_rows(self):
        if self.previewing():
            return SAMPLE_ROWS
        return alert_rows(self.settings, self.pinned, self.active_pipe())

    def previewing(self):
        return time.monotonic() < self.preview_until

    def start_preview(self):
        self.preview_until = time.monotonic() + PREVIEW_SECONDS
        self.show()
        self.redraw()

    def active_pipe(self):
        # Range is measured from the EQ client in the foreground; while another window (or Triage itself,
        # during a drag) is in front, the last active client is kept.
        user32 = ctypes.windll.user32
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(user32.GetForegroundWindow()), ctypes.byref(pid))
        pipe = f'{PIPE_PREFIX}{pid.value}'
        with state_lock:
            if pipe in connected:
                self.origin = pipe
        return self.origin

    def set_passthrough(self, enabled):
        # Clicks pass through to the game everywhere except over the header and the row pins.
        if enabled == self.passthrough:
            return
        self.passthrough = enabled
        self.set_ex_style(WS_EX_TRANSPARENT, enabled)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        width = self.width()
        panel = QPainterPath()
        panel.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), CORNER_RADIUS, CORNER_RADIUS)

        painter.fillPath(panel, PANEL_COLOR)
        painter.save()
        painter.setClipPath(panel)
        painter.fillRect(QRectF(0, 0, width, HEADER_HEIGHT), HEADER_COLOR)
        painter.restore()

        painter.setPen(QPen(DIVIDER_COLOR, 1))
        for i in range(ROWS):
            y = HEADER_HEIGHT + i * self.row_height
            painter.drawLine(QPointF(PADDING / 2, y), QPointF(width - PADDING / 2, y))
        painter.setPen(QPen(EDGE_COLOR, 1))
        painter.drawPath(panel)

        header = QRectF(PADDING, 0, width - 2 * PADDING, HEADER_HEIGHT)
        painter.setPen(HEADER_TEXT_COLOR)
        painter.setFont(self.title_font)
        painter.drawText(header, Qt.AlignVCenter | Qt.AlignLeft, 'Triage (preview)' if self.previewing() else 'Triage')

        painter.setFont(self.row_font)
        for i, (prefix, name, suffix, color, key) in enumerate(self.rows):
            if not name:
                continue
            cell = QRectF(PADDING, HEADER_HEIGHT + i * self.row_height, self.text_width, self.row_height)
            text = self.fit(prefix, name, suffix)
            painter.setPen(SHADOW_COLOR)
            painter.drawText(cell.translated(1, 1), Qt.AlignVCenter | Qt.AlignLeft, text)
            painter.setPen(QColor(color))
            painter.drawText(cell, Qt.AlignVCenter | Qt.AlignLeft, text)
            if key in self.pinned:
                self.draw_pin(painter, cell.center().y(), PIN_COLOR)
            elif key:
                self.draw_pin(painter, cell.center().y(), PIN_HINT_COLOR)

    def draw_pin(self, painter, y, color):
        x = self.pin_left + PIN_WIDTH / 2
        painter.setPen(QPen(color, 1.5))
        painter.drawLine(QPointF(x, y), QPointF(x, y + 5))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(x, y - 2), 3, 3)
        painter.setBrush(Qt.NoBrush)

    def fit(self, prefix, name, suffix):
        room = self.text_width - self.metrics.horizontalAdvance(prefix + suffix)
        return prefix + self.metrics.elidedText(name, Qt.ElideRight, room) + suffix

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        key = self.pin_key_at(event.position())
        if key:
            self.toggle_pin(key)
        elif event.position().y() < HEADER_HEIGHT:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self.take_focus()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset = None
            save_position(self.x(), self.y())
            self.return_focus()


def feed_status():
    # Plain-language state of the Zeal feed for the EQ Triage window, most urgent problem first.
    now = time.monotonic()
    with state_lock:
        pipes = set(connected)
        names = sorted(pipe_characters[pipe] for pipe in pipes if pipe in pipe_characters)
        started = dict(eq_started) if eq_started is not None else None
        in_world = [pipe for pipe in pipes if now - own_locations.get(pipe, (None, -STALE_SECONDS))[1] < STALE_SECONDS]
        grouped = any(now - member_messages.get(pipe, -STALE_SECONDS) < STALE_SECONDS for pipe in pipes)
        missing_hp = verbose_missing
    if started is not None:
        without_feed = [pid for pid in started if f'{PIPE_PREFIX}{pid}' not in pipes]
        # Zeal opens its feed while the game loads, so a client only counts as missing it after a grace period.
        late = [pid for pid in without_feed if now - started[pid] >= ZEAL_GRACE_SECONDS]
        if late:
            where = (f'{len(late)} of your EverQuest windows {"has" if len(late) == 1 else "have"} no Zeal feed'
                     if pipes else "EverQuest is running, but Zeal's feed wasn't found")
            return STATUS_WARN, f'{where}. Make sure Zeal is installed (Zeal.asi in your EverQuest folder).'
        if without_feed and not pipes:
            return STATUS_WAIT, "EverQuest is starting. Waiting for Zeal's feed..."
    if not pipes:
        return STATUS_WAIT, 'Waiting for EverQuest to start.'
    if not in_world:
        return STATUS_WAIT, 'Connected. Waiting for you to enter Norrath.'
    if missing_hp:
        return STATUS_WARN, 'Health data is off. Type /pipeverbose on in game.'
    unnamed = len(pipes) - len(names)
    sources = ', '.join(names + ([f'{unnamed} other window{"" if unnamed == 1 else "s"}'] if unnamed else []))
    if not grouped:
        return STATUS_OK, f'Receiving data from {sources}. Join a group or raid to see other players.'
    return STATUS_OK, f'Receiving data from {sources}.'


def open_docs():
    QDesktopServices.openUrl(QUrl(DOCS_URL))


class ControlWindow(QWidget):
    # The normal window that owns the taskbar button and stays on the desktop EQ Triage was started on.
    # It holds the settings and pins; closing it quits the app.
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.known_names = []
        self.setWindowTitle(APP_NAME)
        self.setFixedWidth(CONTROL_WIDTH)
        intro = QLabel(
            f'<b>{APP_NAME}</b>: a healer\'s overlay for Project Quarm. Low health, pet breaks, deaths and range '
            'at a glance.'
        )
        intro.setWordWrap(True)
        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.status.setWordWrap(True)

        settings_box = QGroupBox('Settings')
        form = QFormLayout(settings_box)
        self.spins = {}
        for key, (_, minimum, maximum, label, suffix) in SETTINGS.items():
            spin = QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSuffix(suffix)
            spin.setValue(overlay.settings[key])
            spin.valueChanged.connect(lambda value, key=key: self.change_setting(key, value))
            form.addRow(label, spin)
            self.spins[key] = spin
        # Red is a stronger warning than listed, so it can never start above the listing level.
        self.spins['critical_hp'].setMaximum(overlay.settings['low_hp'])
        defaults_button = QPushButton('Restore defaults')
        defaults_button.clicked.connect(self.restore_defaults)
        form.addRow('', defaults_button)

        pins_box = QGroupBox('Pinned players (always shown at the top)')
        self.pin_list = QListWidget()
        self.pin_list.setFixedHeight(PIN_LIST_HEIGHT)
        self.pin_name = QComboBox()
        self.pin_name.setEditable(True)
        self.pin_name.lineEdit().setPlaceholderText('Player name')
        self.pin_name.lineEdit().returnPressed.connect(self.pin_player)
        add_button = QPushButton('Add')
        add_button.clicked.connect(self.pin_player)
        remove_button = QPushButton('Remove')
        remove_button.clicked.connect(self.unpin_player)
        pin_row = QHBoxLayout()
        pin_row.addWidget(self.pin_name, 1)
        pin_row.addWidget(add_button)
        pin_row.addWidget(remove_button)
        pins_layout = QVBoxLayout(pins_box)
        pins_layout.addWidget(self.pin_list)
        pins_layout.addLayout(pin_row)

        overlay_box = QGroupBox('Overlay')
        preview_button = QPushButton('Preview')
        preview_button.setToolTip(
            f'Fill the overlay with sample rows for {PREVIEW_SECONDS:g} seconds to check its size and position.'
        )
        preview_button.clicked.connect(self.preview)
        self.visibility_button = QPushButton()
        self.visibility_button.clicked.connect(self.toggle_overlay)
        reset_button = QPushButton('Recenter')
        reset_button.setToolTip('Move the overlay back to the top center of the screen, e.g. if it is off-screen.')
        reset_button.clicked.connect(overlay.reset_position)
        overlay_row = QHBoxLayout(overlay_box)
        overlay_row.addWidget(preview_button)
        overlay_row.addWidget(self.visibility_button)
        overlay_row.addWidget(reset_button)

        docs_button = QPushButton('Read the docs')
        docs_button.clicked.connect(open_docs)
        quit_button = QPushButton('Quit')
        quit_button.clicked.connect(QApplication.quit)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(docs_button)
        buttons.addWidget(quit_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        layout.addWidget(overlay_box)
        layout.addWidget(settings_box)
        layout.addWidget(pins_box)
        layout.addLayout(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(STATUS_MS)
        self.refresh()

    def change_setting(self, key, value):
        self.overlay.settings[key] = value
        save_json(SETTINGS_FILE, self.overlay.settings)
        if key == 'low_hp':
            # Lowering the list level below the red level pulls the red level down with it.
            self.spins['critical_hp'].setMaximum(value)
        if key in ('font_size', 'width'):
            self.overlay.apply_font()
        self.overlay.redraw()

    def restore_defaults(self):
        # low_hp comes first in SETTINGS, so the red level's cap is raised before its default is applied.
        for key, (default, *_) in SETTINGS.items():
            self.spins[key].setValue(default)

    def preview(self):
        self.overlay.start_preview()
        self.refresh()

    def toggle_overlay(self):
        self.overlay.setVisible(not self.overlay.isVisible())
        self.refresh()

    def pin_player(self):
        # EverQuest names are a capital letter followed by lowercase, so typed names are normalized to match.
        name = self.pin_name.currentText().strip().capitalize()
        if name:
            self.overlay.set_pinned(self.overlay.pinned + [name])
            self.pin_name.setEditText('')
            self.refresh()

    def unpin_player(self):
        selected = {item.text() for item in self.pin_list.selectedItems()}
        if selected:
            self.overlay.set_pinned([name for name in self.overlay.pinned if name not in selected])
            self.refresh()

    def refresh(self):
        with state_lock:
            names = sorted(members)
        color, message = feed_status()
        self.status.setText(f'<span style="color:{color}">&#9679;</span> {message}')
        self.visibility_button.setText('Hide' if self.overlay.isVisible() else 'Show')

        # Pins can also change from the overlay itself, so the list follows it.
        if [self.pin_list.item(i).text() for i in range(self.pin_list.count())] != self.overlay.pinned:
            self.pin_list.clear()
            self.pin_list.addItems(self.overlay.pinned)
        if names != self.known_names:
            self.known_names = names
            typed = self.pin_name.currentText()
            self.pin_name.clear()
            self.pin_name.addItems(names)
            self.pin_name.setEditText(typed)

    def closeEvent(self, event):
        QApplication.quit()


def icon_pixmap(size):
    # Drawn on a 32-unit grid and scaled, so the taskbar icon and triage.ico share one design.
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 32, size / 32)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(20, 24, 32))
    painter.drawRoundedRect(QRectF(1, 1, 30, 30), 5, 5)
    painter.setBrush(QColor(CRITICAL_HP_COLOR))
    painter.drawRect(QRectF(13, 6, 6, 20))
    painter.drawRect(QRectF(6, 13, 20, 6))
    painter.end()
    return pixmap


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        icon.addPixmap(icon_pixmap(size))
    return icon


def main():
    parser = argparse.ArgumentParser(description=f'{APP_NAME}: on-screen alerts for low HP, charm breaks and charmers under attack.')
    parser.add_argument('--dump', action='store_true', help='print every change to the group and pet gauges')
    args = parser.parse_args()

    threading.Thread(target=scan_pipes, args=(args,), daemon=True).start()

    # Without its own app ID, a script run by python.exe is grouped under Python's taskbar icon.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())
    window = TriageWindow(load_settings())
    window.move(*(load_position() or window.default_position()))
    window.show()
    window.start()
    control = ControlWindow(window)
    control.show()

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    print('Watching for Zeal pipes. Quit from the EQ Triage window or Ctrl+C.')
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
