"""EQ Triage: on-screen HP and charm break alerts for Project Quarm, fed by Zeal's named pipe.

Author: Sebik <Europa>
"""

import argparse
import codecs
import collections
import csv
import ctypes
import json
import math
import os
import re
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QPushButton, QSpinBox, QVBoxLayout, QWidget,
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
CHARMER_HIT_SECONDS = 6.0
RECHARM_GRACE_SECONDS = 2.0
STALE_SECONDS = 2.0
MIN_BREAK_HP = 10
DISTANCE_STEP = 10
CHARM_BREAK_PREFIX = 'CHARM BREAK '
CHARMER_HIT_PREFIX = 'CHARMER HIT '
UNTAGGED_PREFIXES = ('DEAD ', CHARM_BREAK_PREFIX)
DROP_MARKED_PREFIXES = ('', CHARMER_HIT_PREFIX)
SCAN_SECONDS = 5.0
ZEAL_GRACE_SECONDS = 20.0
EQ_PROCESS = 'eqgame.exe'
STATUS_OK = '#3fb950'
STATUS_WARN = '#e3a008'
STATUS_WAIT = '#8a93a3'
REFRESH_MS = 100
STATUS_MS = 1000
CONTROL_WIDTH = 340
NOTE_SPACING = 8
PIN_LIST_HEIGHT = 90
TEST_BUTTON_WIDTH = 28
CUSTOM_ITEM_TEXT = 'Custom file\u2026'
GRID_SPACING = 18
SHOW_COLUMN_WIDTH = 120
DIVIDER_COLUMN_WIDTH = 24
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
    (CHARMER_HIT_PREFIX, 'Sebik', ' 80%', CHARMER_COLOR, None),
    (CHARM_BREAK_PREFIX, 'Sebik', '', CHARMER_COLOR, None),
    ('DEAD ', 'Sebik', '', DEATH_COLOR, None),
    ('', 'Sebik', ' 22%', CRITICAL_HP_COLOR, None),
    ('', 'Sebik', ' pet 41%', LOW_HP_COLOR, None),
    ('', 'Sebik', ' 38% (150 away)', LOW_HP_COLOR, None),
]
# Dropping fast: HP lost per second, measured over a short window and held briefly so the marker doesn't flicker.
DROP_MARKER = ' \u25bc'
DROP_WINDOW_SECONDS = 1.0
DROP_MIN_SPAN_SECONDS = 0.5
DROP_HOLD_SECONDS = 1.5
DROP_PROJECT_SECONDS = 2.0
DEFAULT_DROP_RATE = 10
DROP_RATE_RANGE = (3, 50)
# Watch setting: every raid member, only the active character's raid group, or chosen raid groups.
FOCUS_ALL = 'all'
FOCUS_MINE = 'mine'
FOCUS_GROUPS = 'groups'
RAID_GROUPS = 12
RAID_GROUP_COLUMNS = 4
FOCUS_GROUPS_TEXT = 'Chosen groups\u2026'
FOCUS_CHOICES = (('Whole raid', FOCUS_ALL), ('My group', FOCUS_MINE), (FOCUS_GROUPS_TEXT, FOCUS_GROUPS))
# Pins are capped at the most rows the overlay can show; with fewer rows set, only the first pins fit.
MAX_PINS = 25
DEFAULT_Y = 150
FONT_FAMILY = 'Segoe UI'
TITLE_POINT_SIZE = 8
HEADER_HEIGHT = 20
PADDING = 6
PIN_WIDTH = 14
ROW_GAP = 4
CORNER_RADIUS = 3
PANEL_RGB = (14, 18, 26)
HEADER_COLOR = QColor(255, 255, 255, 20)
# The header's own dark backing, matching the default 70% background, so it looks the same at any opacity.
HEADER_BACKING_COLOR = QColor(*PANEL_RGB, 178)
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
LATEST_RELEASE_API = 'https://api.github.com/repos/CopperGlade/EQTriage/releases/latest'
UPDATE_TIMEOUT_SECONDS = 10
# version_info.txt is the single source of the version; the build bundles it into the exe's unpack directory.
BUNDLE_DIR = getattr(sys, '_MEIPASS', APP_DIR)
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
# Setting key -> (default, minimum, maximum, label in the control window, suffix shown after the value).
SETTINGS = {
    # Listed players farther away than this get their distance shown, e.g. (150 away), when warnings are on.
    'range': (70, 10, 1000, 'Distance warning beyond', ' units'),
    'font_size': (10, 7, 20, 'Text size', ' pt'),
    # Counted in characters rather than pixels, so the overlay widens with the text size and names keep fitting.
    'width': (26, 12, 40, 'Overlay width', ' characters'),
    # The frame: background, outer border and row dividers. Text, alert colors, pins, the header strip and the
    # bottom edge always stay as they are, and the header's fixed backing keeps it grabbable at 0%.
    'opacity': (70, 0, 100, 'Background opacity', '%'),
    'rows': (10, 3, MAX_PINS, 'Number of rows', ' rows'),
}
# How the EQ Triage window groups them: what the overlay looks like, and what gets listed on it.
OVERLAY_SETTINGS = ('font_size', 'width', 'opacity', 'rows')
ALERT_SETTINGS = ('range',)
# EverQuest's class numbers as Zeal reports them.
CLASSES = {
    1: 'Warrior', 2: 'Cleric', 3: 'Paladin', 4: 'Ranger', 5: 'Shadow Knight', 6: 'Druid', 7: 'Monk', 8: 'Bard',
    9: 'Rogue', 10: 'Shaman', 11: 'Necromancer', 12: 'Wizard', 13: 'Magician', 14: 'Enchanter', 15: 'Beastlord',
}
# Health thresholds are set per class. Pets have no class in Zeal's data, and a player's class can be unknown
# for a moment while data arrives, so both get their own entry.
# The only classes that charm at high level; other classes losing a pet is never a charm break.
CHARM_CLASSES = ('Bard', 'Enchanter', 'Necromancer')
# Every name the Project Quarm server can generate for a summoned pet: one fragment from each slot, the middle two
# optional (EQMacEmu common/name_generator.cpp, pet table).
SUMMONED_PET_NAME = re.compile(r'^[GJKLVXZ](?:ab|on|ib|as|ar|ob|eb|en)?(?:ar|an|ek|ob)?(?:tik|er|n|ab)$')
PET_GROUP = 'Pets'
UNKNOWN_GROUP = 'Unknown class'
# Default (list, red) levels by how much punishment a class can take: melee last, pure casters first.
CATEGORIES = {
    'Melee': (('Bard', 'Monk', 'Paladin', 'Ranger', 'Rogue', 'Shadow Knight', 'Warrior'), (40, 25)),
    'Hybrid casters': (('Beastlord', 'Cleric', 'Druid', 'Shaman'), (50, 30)),
    'Pure casters': (('Enchanter', 'Magician', 'Necromancer', 'Wizard'), (75, 50)),
    'Other': ((PET_GROUP, UNKNOWN_GROUP), (50, 30)),
}
THRESHOLD_GROUPS = [group for groups, _ in CATEGORIES.values() for group in groups]
DEFAULT_LEVELS = {group: levels for groups, levels in CATEGORIES.values() for group in groups}
# Version 1.0 had a single warning/critical level, saved as these values unless the player changed them.
LEGACY_LEVELS = (50, 30)
# Event key -> (label in the EQ Triage window, shown by default, sound on by default; None when it has no sound).
EVENTS = {
    'low': ('Warning health (yellow)', True, False),
    'critical': ('Critical health (red)', True, False),
    'charm_break': ('Charm break', True, True),
    'charmer_hit': ('Charmer hit', True, True),
    'dropping': ('Dropping fast (\u25bc)', True, False),
    'death': ('Death', True, False),
    'pets': ('Pets in the list', True, None),
}
# The sound each alert plays until the player picks another from SOUNDS.
# Picker value meaning "play the player's own .wav from settings['custom_sounds']".
CUSTOM_SOUND = 'custom'
DEFAULT_SOUNDS = {
    'low': 'soft_ping',
    'critical': 'double_chirp',
    'charm_break': 'rising_chime',
    'charmer_hit': 'klaxon',
    'dropping': 'alarm_pulses',
    'death': 'low_gong',
}
# Only one sound plays at a time, so when several events start together the most urgent one is heard.
SOUND_PRIORITY = ('charmer_hit', 'charm_break', 'death', 'dropping', 'critical', 'low')
SOUND_REPEAT_SECONDS = 10.0
# 44.1 kHz keeps the bells' high partials below the Nyquist limit, so they don't alias into harsh tones.
SOUND_RATE = 44100
SOUND_PEAK = 0.6
SOUND_DIR = os.path.join(tempfile.gettempdir(), 'EQTriage-sounds')

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
charmer_hits = {}
hp_seen = {}
hp_history = {}
dropping_until = {}
member_classes = {}
raid_groups = {}
connected = set()
pipe_characters = {}
member_messages = {}
eq_started = None
verbose_missing = False
newer_release = None


def is_watched(name, now):
    broke = charm_breaks.get(name)
    if not broke:
        return False
    return now - broke[1] < WATCH_SECONDS or now - charmer_hits.get(name, -CHARMER_HIT_SECONDS) < CHARMER_HIT_SECONDS


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
            if entry.get('class') in CLASSES:
                member_classes[entry['name']] = entry['class']
            # Only raid entries carry a group: its number as text ("1" to "12"), or "Ungrouped".
            if 'group' in entry:
                raid_groups[entry['name']] = (str(entry['group']), now)
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
            history = hp_history.setdefault(name, collections.deque())
            history.append((now, current * 100 / maximum))
            while history and now - history[0][0] > DROP_WINDOW_SECONDS:
                history.popleft()
            # Compared per client: another client's view can lag, and regen then looks like damage.
            previous = hp_seen.get((pipe_name, name))
            hp_seen[(pipe_name, name)] = (current, maximum)
            if previous and previous[1] == maximum and current < previous[0] and is_watched(name, now):
                if now - charmer_hits.get(name, -CHARMER_HIT_SECONDS) >= CHARMER_HIT_SECONDS:
                    print(f'CHARMER HIT {name} took damage after a charm break ({previous[0]} -> {current} HP)')
                charmer_hits[name] = now


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


def could_be_charm(owner, pet_name):
    # A vanished pet only counts as a charm break if its owner is a class that charms at high level and the pet
    # isn't a summoned one. The Project Quarm server names summoned pets either with a generated name matching
    # SUMMONED_PET_NAME (e.g. Gabartik) or after the owner (Sebik`s pet, `s familiar, `s warder). Charmed mobs keep
    # their own name, one word or several (Quillmane, a Shissar Defiler). An unknown class or name doesn't rule it
    # out, so a real break is never missed just because that data hadn't arrived.
    with state_lock:
        owner_class = member_classes.get(owner)
    if owner_class is not None and CLASSES[owner_class] not in CHARM_CLASSES:
        return False
    name = re.sub(r'\d+$', '', pet_name.replace('_', ' ').strip())
    if not name:
        return True
    return not SUMMONED_PET_NAME.match(name) and not name.lower().startswith(f'{owner.lower()}`s ')


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
            if owner_value > 0 and pet['value'] >= self.min_break_value and could_be_charm(owner, pet['name']):
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
        print(f'CHARM BREAK? {owner} lost {pet["name"] or "pet"} at {hp:.0f}% ({self.pipe_name})')

    def clear_if_recharmed(self, owner):
        with state_lock:
            broke = charm_breaks.get(owner)
            if broke and time.monotonic() - broke[1] >= RECHARM_GRACE_SECONDS:
                del charm_breaks[owner]
                charmer_hits.pop(owner, None)

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


def hp_color(pct, red_hp):
    return CRITICAL_HP_COLOR if pct < red_hp else LOW_HP_COLOR


def limits(settings, name, pet=False):
    # (warning level, critical level) for a player's class, or for pets. Needs state_lock for member_classes.
    group = PET_GROUP if pet else CLASSES.get(member_classes.get(name), UNKNOWN_GROUP)
    threshold = settings['thresholds'][group]
    return threshold['list'], threshold['red']


def drop_rate(name):
    # HP % lost per second across the recent window, or 0 without enough history. Needs state_lock.
    history = hp_history.get(name)
    if not history:
        return 0.0
    (start, start_pct), (end, end_pct) = history[0], history[-1]
    if end - start < DROP_MIN_SPAN_SECONDS:
        return 0.0
    return (start_pct - end_pct) / (end - start)


def listed(readings, settings, now, pet=False, dropping=None):
    # (distance above their critical level, HP %, name, critical level) for each fresh reading below its warning
    # level whose band is switched on, plus anyone dropping fast even above it. Sorting by distance puts whoever is
    # closest to their own critical level first; for someone dropping fast the distance is measured from where they
    # will be a moment from now at their current rate, so a fast fall ranks above a slow low.
    dropping = dropping or {}
    entries = []
    for name, (pct, seen) in readings.items():
        list_hp, red_hp = limits(settings, name, pet)
        banded = pct < list_hp and settings['show']['critical' if pct < red_hp else 'low']
        if now - seen < STALE_SECONDS and (banded or name in dropping):
            projected = pct - dropping.get(name, 0) * DROP_PROJECT_SECONDS
            entries.append((projected - red_hp, pct, name, red_hp))
    return sorted(entries)


def status_row(name, hp, member_limits, dead, charmers_hit, breaks):
    if name in dead:
        return ('DEAD ', name, '', DEATH_COLOR, name)
    pct = hp.get(name)
    suffix = '' if pct is None else f' {int(pct)}%'
    if name in charmers_hit:
        return (CHARMER_HIT_PREFIX, name, suffix, CHARMER_COLOR, name)
    if name in breaks:
        return (CHARM_BREAK_PREFIX, name, '', CHARMER_COLOR, name)
    if pct is None:
        return ('', name, ' --', STALE_COLOR, name)
    list_hp, red_hp = member_limits[name]
    return ('', name, suffix, hp_color(pct, red_hp) if pct < list_hp else PINNED_COLOR, name)


def distance_to(name, origin, now):
    # Straight-line distance from the active EQ character, math.inf when the player is in another zone
    # (no position in that client), or None when your own position isn't known yet.
    own = own_locations.get(origin)
    if not own or now - own[1] >= STALE_SECONDS:
        return None
    theirs = member_locations.get((origin, name))
    if not theirs or now - theirs[1] >= STALE_SECONDS:
        return math.inf
    return math.dist(own[0], theirs[0])


def with_drop_marker(row):
    prefix, name, suffix, color, key = row
    return prefix, name, suffix + DROP_MARKER, color, key


def with_distance(row, distance):
    prefix, name, suffix, color, key = row
    if distance == math.inf:
        return prefix, name, suffix + ' (other zone)', color, key
    # Rounded to the nearest step so the number doesn't flicker as people move. Halves round up; Python's
    # round() would round them to even.
    rounded = math.floor(distance / DISTANCE_STEP + 0.5) * DISTANCE_STEP
    return prefix, name, f'{suffix} ({rounded} away)', color, key


def snapshot(settings, now):
    # What the overlay and the sounds both work from, with switched-off event types left out. Needs state_lock.
    show = settings['show']
    hp = {name: pct for name, (pct, seen) in members.items() if now - seen < STALE_SECONDS}
    member_limits = {name: limits(settings, name) for name in hp}
    dead = sorted(name for name, at in deaths.items() if now - at < DEATH_SECONDS) if show['death'] else []
    charmers_hit = sorted(
        (name for name, hit in charmer_hits.items() if now - hit < CHARMER_HIT_SECONDS and name not in dead),
        key=lambda n: hp.get(n, 100),
    ) if show['charmer_hit'] else []
    breaks = [
        owner for owner, (_, at) in charm_breaks.items()
        if now - at < ALERT_SECONDS and owner not in charmers_hit and owner not in dead
    ] if show['charm_break'] else []
    rates = {name: drop_rate(name) for name in hp}
    for name, rate in rates.items():
        if rate >= settings['drop_rate']:
            dropping_until[name] = now + DROP_HOLD_SECONDS
    # Name -> current rate for everyone marked as dropping fast.
    dropping = {}
    if show['dropping']:
        dropping = {name: max(rates[name], 0) for name, until in dropping_until.items() if until > now and name in hp}
    low = listed(members, settings, now, dropping=dropping)
    low_pets = listed(pet_hp, settings, now, pet=True) if show['pets'] else []
    return hp, member_limits, dead, charmers_hit, breaks, low, low_pets, dropping


def focus_filter(settings, origin, now):
    # Which players the Watch setting keeps: None keeps everyone. Raid groups only exist in a raid, so outside one
    # nothing is filtered, and a player without raid data (e.g. only in your group) is always kept. Needs state_lock.
    if settings['focus'] == FOCUS_ALL:
        return None
    groups = {name: group for name, (group, seen) in raid_groups.items() if now - seen < STALE_SECONDS}
    if not groups:
        return None
    if settings['focus'] == FOCUS_MINE:
        # Your raid group is that of the character in the active EQ window, so it follows you between boxes.
        mine = groups.get(pipe_characters.get(origin))
        if mine is None:
            return None
        wanted = {mine}
    else:
        wanted = {str(group) for group in settings['focus_groups']}
    return lambda name: name not in groups or groups[name] in wanted


def apply_focus(keep, dead, charmers_hit, breaks, low, low_pets):
    if keep is None:
        return dead, charmers_hit, breaks, low, low_pets
    return (
        [name for name in dead if keep(name)],
        [name for name in charmers_hit if keep(name)],
        [name for name in breaks if keep(name)],
        [entry for entry in low if keep(entry[2])],
        [entry for entry in low_pets if keep(entry[2])],
    )


def padded(rows, count):
    return rows[:count] + [EMPTY_ROW] * (count - len(rows))


def alert_rows(settings, pinned, origin=None):
    now = time.monotonic()
    with state_lock:
        distances = {name: distance_to(name, origin, now) for name in members}
        far = {name: d for name, d in distances.items() if d is not None and d > settings['range']}
        hp, member_limits, dead, charmers_hit, breaks, low, low_pets, dropping = snapshot(settings, now)
        keep = focus_filter(settings, origin, now)
    # Pinned players are shown whatever the Watch setting; everything else follows it.
    dead, charmers_hit, breaks, low, low_pets = apply_focus(keep, dead, charmers_hit, breaks, low, low_pets)
    # Each row is (prefix, name, suffix, color, pin key). Only the name is shortened when a row is too wide,
    # and the pin key is the player a click on the row's pin toggles (None for pets and empty rows).
    flagged = [name for name in charmers_hit + breaks + dead if name not in pinned]
    rows = [status_row(name, hp, member_limits, dead, charmers_hit, breaks) for name in pinned + flagged]
    shown = set(pinned) | set(flagged)
    players = [(margin, pct, name, '', red_hp, name) for margin, pct, name, red_hp in low if name not in shown]
    pets = [(margin, pct, owner, ' pet', red_hp, None) for margin, pct, owner, red_hp in low_pets]
    rows += [
        ('', name, f'{label} {int(pct)}%', hp_color(pct, red_hp), key)
        for _, pct, name, label, red_hp, key in sorted(players + pets, key=lambda row: row[:4])
    ]
    rows = [with_drop_marker(row) if row[4] in dropping and row[0] in DROP_MARKED_PREFIXES else row for row in rows]
    if settings['distance_warning']:
        rows = [with_distance(row, far[row[4]]) if row[4] in far and row[0] not in UNTAGGED_PREFIXES else row
                for row in rows]
    if verbose_missing:
        rows.insert(0, VERBOSE_ROW)
    return padded(rows, settings['rows'])


def limits_by_name(settings, name):
    # Warning level for an event's name; pets carry " pet" after the owner's name.
    with state_lock:
        if name.endswith(' pet'):
            return limits(settings, name[:-len(' pet')], pet=True)[0]
        return limits(settings, name)[0]


def current_events(settings, origin=None):
    # (event type, who) for everything alerting right now; sounds play when a new one appears. Showing on the
    # overlay and playing a sound are independent, so an alert type counts here if either is switched on.
    now = time.monotonic()
    audible = dict(settings, show={
        key: shown or settings['sound'].get(key, False) for key, shown in settings['show'].items()
    })
    with state_lock:
        _, _, dead, charmers_hit, breaks, low, low_pets, dropping = snapshot(audible, now)
        keep = focus_filter(settings, origin, now)
    dead, charmers_hit, breaks, low, low_pets = apply_focus(keep, dead, charmers_hit, breaks, low, low_pets)
    events = {('death', name) for name in dead}
    events |= {('dropping', name) for name in dropping if keep is None or keep(name)}
    events |= {('charmer_hit', name) for name in charmers_hit}
    events |= {('charm_break', name) for name in breaks}
    for _, pct, name, red_hp in low + [(m, pct, f'{owner} pet', red_hp) for m, pct, owner, red_hp in low_pets]:
        list_hp = limits_by_name(settings, name)
        if pct < list_hp:
            events.add(('critical' if pct < red_hp else 'low', name))
    return events


def render(seconds, voice):
    return [voice(i / SOUND_RATE) for i in range(int(seconds * SOUND_RATE))]


def mix(*parts):
    # (samples, start in seconds) pairs laid over each other.
    out = [0.0] * max(len(samples) + int(start * SOUND_RATE) for samples, start in parts)
    for samples, start in parts:
        offset = int(start * SOUND_RATE)
        for i, value in enumerate(samples):
            out[offset + i] += value
    return out


def attack(t, seconds=0.004):
    return min(1.0, t / seconds)


def bell(frequency, decay, partials=((1, 1), (2.76, 0.5), (5.40, 0.25), (8.93, 0.12))):
    # Struck-bell timbre: inharmonic partials, the higher ones fading faster.
    def voice(t):
        return attack(t) * sum(
            level * math.exp(-t * decay * ratio ** 0.5) * math.sin(2 * math.pi * frequency * ratio * t)
            for ratio, level in partials
        )
    return voice


def marimba(frequency, decay=9.0):
    # Wooden mallet: a strong fundamental plus the 4th harmonic, both dying quickly.
    def voice(t):
        wave_ = math.sin(2 * math.pi * frequency * t) + 0.35 * math.sin(2 * math.pi * frequency * 4 * t)
        return attack(t, 0.002) * math.exp(-t * decay) * wave_
    return voice


def buzz(frequency, seconds, fade=0.01):
    # Odd harmonics give a buzzy alarm tone without harsh clipping.
    def voice(t):
        envelope = min(1.0, t / fade, max(0.0, (seconds - t) / fade))
        return envelope * sum(math.sin(2 * math.pi * frequency * k * t) / k for k in (1, 3, 5, 7))
    return voice


def sweep(start, end, seconds):
    def voice(t):
        envelope = min(1.0, t / 0.01, max(0.0, (seconds - t) / 0.03))
        phase = 2 * math.pi * (start * t + (end - start) * t * t / (2 * seconds))
        return envelope * (math.sin(phase) + 0.3 * math.sin(2 * phase))
    return voice


def drop(start, end, seconds):
    def voice(t):
        phase = 2 * math.pi * (start * t + (end - start) * t * t / (2 * seconds))
        return attack(t, 0.002) * math.exp(-t * 14) * math.sin(phase)
    return voice


def horn(frequencies, seconds):
    def voice(t):
        envelope = min(1.0, t / 0.04, max(0.0, (seconds - t) / 0.08))
        return envelope * sum(
            math.sin(2 * math.pi * f * k * t) / k ** 1.3 for f in frequencies for k in range(1, 6)
        )
    return voice


C5, E5, G5, B5, C6, E6 = 523.25, 659.25, 783.99, 987.77, 1046.5, 1318.5
GONG_PARTIALS = ((1, 1), (2.1, 0.6), (3.2, 0.35), (4.6, 0.2), (6.3, 0.1))
# Sound key -> (name in the picker, function building its samples). Generated in code, so no audio files ship.
SOUNDS = {
    'soft_ping': ('Soft ping', lambda: render(0.45, bell(1568, 7, ((1, 1), (2.0, 0.15))))),
    'water_drop': ('Water drop', lambda: render(0.3, drop(1600, 500, 0.3))),
    'double_chirp': ('Double chirp', lambda: mix((render(0.09, sweep(900, 1800, 0.09)), 0),
                                                 (render(0.09, sweep(900, 1800, 0.09)), 0.14))),
    'two_note_chime': ('Two-note chime', lambda: mix((render(0.9, bell(E6, 4)), 0), (render(0.9, bell(B5, 4)), 0.16))),
    'rising_chime': ('Rising chime', lambda: mix((render(0.7, bell(C6, 5)), 0), (render(0.9, bell(E6, 5)), 0.12))),
    'bell': ('Bell', lambda: render(1.4, bell(880, 3))),
    'marimba_rising': ('Marimba rising', lambda: mix((render(0.35, marimba(C5)), 0), (render(0.35, marimba(E5)), 0.09),
                                                     (render(0.5, marimba(G5)), 0.18))),
    'marimba_falling': ('Marimba falling', lambda: mix((render(0.35, marimba(G5)), 0),
                                                       (render(0.35, marimba(E5)), 0.11),
                                                       (render(0.6, marimba(C5)), 0.22))),
    'horn_chord': ('Horn chord', lambda: render(0.55, horn((220, 330, 440), 0.55))),
    'alarm_pulses': ('Alarm pulses', lambda: mix(*[(render(0.08, buzz(1000, 0.08)), 0.13 * i) for i in range(3)])),
    'siren_sweep': ('Siren sweep', lambda: render(0.55, sweep(600, 1300, 0.55))),
    'klaxon': ('Klaxon', lambda: mix(*[(render(0.15, buzz(f, 0.15)), 0.17 * i)
                                       for i, f in enumerate((700, 520, 700, 520))])),
    'low_gong': ('Low gong', lambda: render(2.0, bell(110, 1.6, GONG_PARTIALS))),
}

# Fits the longest built-in sound name; a long custom file name is cut short, with its full path as a tooltip.
PICKER_CHARS = max(len(name) for name, _ in SOUNDS.values())


def write_sound(key):
    samples = SOUNDS[key][1]()
    peak = max(abs(value) for value in samples) or 1
    path = os.path.join(SOUND_DIR, f'{key}.wav')
    os.makedirs(SOUND_DIR, exist_ok=True)
    with wave.open(path, 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(SOUND_RATE)
        file.writeframes(b''.join(struct.pack('<h', int(SOUND_PEAK * value / peak * 32767)) for value in samples))
    return path


def play_sound(path):
    import winsound
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


class SoundAlerts:
    def __init__(self, settings):
        # Sounds are written on first use; the ones currently picked are written up front so alerts play instantly.
        self.files = {}
        for key in set(settings['sound_choice'].values()) - {CUSTOM_SOUND}:
            self.file(key)
        self.active = None
        self.last_played = {}

    def file(self, key):
        if key not in self.files:
            self.files[key] = write_sound(key)
        return self.files[key]

    def play(self, settings, event_type):
        # A custom file plays if it still exists; otherwise the alert falls back to its default built-in sound.
        choice = settings['sound_choice'][event_type]
        if choice == CUSTOM_SOUND:
            path = settings['custom_sounds'].get(event_type, '')
            if os.path.isfile(path):
                play_sound(path)
                return
            choice = DEFAULT_SOUNDS[event_type]
        play_sound(self.file(choice))

    def update(self, settings, events):
        previous, self.active = self.active, events
        # The first reading only records what is already happening, so starting EQ Triage mid-fight is silent.
        if previous is None:
            return
        # Being healed from red back into yellow is good news, not a new low-health alert.
        new = {e for e in events - previous if not (e[0] == 'low' and ('critical', e[1]) in previous)}
        now = time.monotonic()
        due = [
            e for e in new
            if settings['sound'].get(e[0])
            and now - self.last_played.get(e, -SOUND_REPEAT_SECONDS) >= SOUND_REPEAT_SECONDS
        ]
        if not due:
            return
        for event in due:
            self.last_played[event] = now
        event_type = min(due, key=lambda e: SOUND_PRIORITY.index(e[0]))[0]
        self.play(settings, event_type)


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
    return list(dict.fromkeys(name for name in pins if isinstance(name, str)))[:MAX_PINS]


def load_settings():
    saved = load_json(SETTINGS_FILE)
    saved = saved if isinstance(saved, dict) else {}
    settings = {}
    for key, (default, minimum, maximum, _, _) in SETTINGS.items():
        value = saved.get(key)
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        settings[key] = min(max(int(value), minimum), maximum) if valid else default
    settings['thresholds'] = load_thresholds(saved)
    settings['locked'] = saved.get('locked') is True
    settings['distance_warning'] = saved.get('distance_warning') is not False
    rate = saved.get('drop_rate')
    valid = isinstance(rate, (int, float)) and not isinstance(rate, bool)
    settings['drop_rate'] = min(max(int(rate), DROP_RATE_RANGE[0]), DROP_RATE_RANGE[1]) if valid else DEFAULT_DROP_RATE
    settings['focus'] = saved.get('focus') if saved.get('focus') in (FOCUS_ALL, FOCUS_MINE, FOCUS_GROUPS) else FOCUS_ALL
    groups = saved.get('focus_groups') if isinstance(saved.get('focus_groups'), list) else []
    settings['focus_groups'] = sorted({g for g in groups if isinstance(g, int) and 1 <= g <= RAID_GROUPS})
    if settings['focus'] == FOCUS_GROUPS and not settings['focus_groups']:
        settings['focus'] = FOCUS_ALL
    settings.update(event_defaults(saved))
    return settings


def valid_percent(value, default):
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    return min(max(int(value), 1), 100) if valid else default


def load_thresholds(saved):
    # Version 1.0 had one warning/critical level. If the player had changed it, it carries over to every class;
    # the untouched 1.0 values are ignored so the class defaults apply.
    legacy = (
        valid_percent(saved.get('low_hp'), LEGACY_LEVELS[0]),
        valid_percent(saved.get('critical_hp'), LEGACY_LEVELS[1]),
    )
    stored = saved.get('thresholds') if isinstance(saved.get('thresholds'), dict) else {}
    thresholds = {}
    for group in THRESHOLD_GROUPS:
        fallback_list, fallback_red = legacy if legacy != LEGACY_LEVELS else DEFAULT_LEVELS[group]
        entry = stored.get(group) if isinstance(stored.get(group), dict) else {}
        list_hp = valid_percent(entry.get('list'), fallback_list)
        # Critical is the stronger warning, so it can never start above the warning level.
        thresholds[group] = {'list': list_hp, 'red': min(valid_percent(entry.get('red'), fallback_red), list_hp)}
    return thresholds


def default_thresholds():
    return {group: {'list': list_hp, 'red': red_hp} for group, (list_hp, red_hp) in DEFAULT_LEVELS.items()}


def event_defaults(saved):
    # The per-event Enabled and Sound switches and each alert's chosen sound, taking saved values where valid.
    options = {}
    for group, index in (('show', 1), ('sound', 2)):
        stored = saved.get(group) if isinstance(saved.get(group), dict) else {}
        options[group] = {
            key: stored[key] if isinstance(stored.get(key), bool) else spec[index]
            for key, spec in EVENTS.items() if spec[index] is not None
        }
    stored = saved.get('custom_sounds') if isinstance(saved.get('custom_sounds'), dict) else {}
    options['custom_sounds'] = {
        key: path for key, path in stored.items() if key in DEFAULT_SOUNDS and isinstance(path, str)
    }
    stored = saved.get('sound_choice') if isinstance(saved.get('sound_choice'), dict) else {}
    options['sound_choice'] = {}
    for key, default in DEFAULT_SOUNDS.items():
        choice = stored.get(key)
        valid = choice in SOUNDS or (choice == CUSTOM_SOUND and key in options['custom_sounds'])
        options['sound_choice'][key] = choice if valid else default
    return options


def faded(color, opacity):
    color = QColor(color)
    color.setAlpha(round(color.alpha() * opacity))
    return color


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
        self.sounds = SoundAlerts(settings)
        self.pinned = load_pins()
        self.rows = [EMPTY_ROW] * settings['rows']
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
            self.pin_left + PIN_WIDTH + PADDING, HEADER_HEIGHT + self.settings['rows'] * self.row_height + ROW_GAP
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
        if not self.previewing():
            self.sounds.update(self.settings, current_events(self.settings, self.active_pipe()))
        cursor = self.mapFromGlobal(QCursor.pos())
        if rows != self.rows:
            self.rows = rows
            self.update()
        over_pin = self.pin_key_at(cursor) is not None
        # A locked overlay has no drag area, so its header lets clicks through like the rest of it.
        over_header = not self.settings['locked'] and self.rect().contains(cursor) and cursor.y() < HEADER_HEIGHT
        self.setCursor(Qt.PointingHandCursor if over_pin else Qt.SizeAllCursor)
        self.set_passthrough(self.drag_offset is None and not over_header and not over_pin)
        ctypes.windll.user32.SetWindowPos(
            self.hwnd(), ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )

    def pin_key_at(self, pos):
        if pos.x() < self.pin_left or pos.x() >= self.width() or pos.y() < HEADER_HEIGHT:
            return None
        index = int((pos.y() - HEADER_HEIGHT) // self.row_height)
        return self.rows[index][4] if index < len(self.rows) else None

    def set_pinned(self, names):
        self.pinned = list(dict.fromkeys(names))[:MAX_PINS]
        save_json(PINS_FILE, self.pinned)
        self.redraw()

    def toggle_pin(self, name):
        self.set_pinned([n for n in self.pinned if n != name] if name in self.pinned else self.pinned + [name])

    def redraw(self):
        self.rows = self.current_rows()
        self.update()

    def current_rows(self):
        if self.previewing():
            return padded(SAMPLE_ROWS, self.settings['rows'])
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

        # Opacity fades the frame: background, outer border and row dividers. The header strip, its title and the
        # bottom edge keep a fixed look, so the overlay can always be found and dragged by its header.
        opacity = self.settings['opacity'] / 100
        painter.save()
        painter.setClipPath(panel)
        painter.fillRect(QRectF(0, 0, width, HEADER_HEIGHT), HEADER_BACKING_COLOR)
        painter.fillRect(QRectF(0, 0, width, HEADER_HEIGHT), HEADER_COLOR)
        body = QRectF(0, HEADER_HEIGHT, width, self.height() - HEADER_HEIGHT)
        painter.fillRect(body, QColor(*PANEL_RGB, round(255 * opacity)))
        painter.restore()

        painter.setPen(QPen(faded(DIVIDER_COLOR, opacity), 1))
        for i in range(self.settings['rows']):
            y = HEADER_HEIGHT + i * self.row_height
            painter.drawLine(QPointF(PADDING / 2, y), QPointF(width - PADDING / 2, y))
        painter.setPen(QPen(faded(EDGE_COLOR, opacity), 1))
        painter.drawPath(panel)
        # The bottom edge stays at full strength, like the header, so the overlay's end is always visible.
        bottom = self.height() - 0.5
        painter.setPen(QPen(EDGE_COLOR, 1))
        painter.drawLine(QPointF(CORNER_RADIUS, bottom), QPointF(width - CORNER_RADIUS, bottom))

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
        elif event.position().y() < HEADER_HEIGHT and not self.settings['locked']:
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


def read_app_version():
    with open(os.path.join(BUNDLE_DIR, 'version_info.txt'), encoding='utf-8') as file:
        return re.search(r"ProductVersion', '([0-9.]+)'", file.read()).group(1)


APP_VERSION = read_app_version()


def version_tuple(text):
    return tuple(int(part) for part in re.findall(r'\d+', text))


def check_for_update():
    # Asks GitHub once for the latest published release. Offline or rate-limited just means no notice.
    global newer_release
    request = urllib.request.Request(LATEST_RELEASE_API, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': f'EQTriage/{APP_VERSION}',
    })
    try:
        with urllib.request.urlopen(request, timeout=UPDATE_TIMEOUT_SECONDS) as response:
            release = json.load(response)
        tag, url = release['tag_name'], release['html_url']
    except (OSError, ValueError, KeyError, TypeError):
        return
    if version_tuple(tag) > version_tuple(APP_VERSION):
        with state_lock:
            newer_release = (tag.lstrip('v'), url)


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
            f'<b>{APP_NAME}</b> {APP_VERSION}: a healer\'s overlay for Project Quarm. Low health, charm breaks, '
            'deaths and range at a glance.'
        )
        intro.setWordWrap(True)
        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.status.setWordWrap(True)
        self.update_notice = QLabel()
        self.update_notice.setTextFormat(Qt.RichText)
        self.update_notice.setOpenExternalLinks(True)
        self.update_notice.hide()

        self.spins = {}
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
        lock_box = QCheckBox('Lock position')
        lock_box.setToolTip("Stop the overlay's header from being dragged, so a stray click can't move it.")
        lock_box.setChecked(overlay.settings['locked'])
        lock_box.toggled.connect(self.set_locked)
        overlay_row = QHBoxLayout()
        overlay_row.addWidget(preview_button)
        overlay_row.addWidget(self.visibility_button)
        overlay_row.addWidget(reset_button)
        overlay_form = QFormLayout()
        self.add_spins(overlay_form, OVERLAY_SETTINGS)
        overlay_layout = QVBoxLayout(overlay_box)
        overlay_layout.addLayout(overlay_row)
        overlay_layout.addWidget(lock_box)
        overlay_layout.addLayout(overlay_form)

        alerts_box = QGroupBox('Alerts')
        alert_types_button = QPushButton('Alert types && sounds\u2026')
        alert_types_button.setToolTip('Choose which alerts show on the overlay and which play a sound.')
        alert_types_button.clicked.connect(lambda: self.open_dialog(AlertTypesDialog))
        thresholds_button = QPushButton('Health thresholds\u2026')
        thresholds_button.setToolTip('Set the warning and critical health levels for each class and for pets.')
        thresholds_button.clicked.connect(lambda: self.open_dialog(ThresholdsDialog))
        alerts_buttons = QHBoxLayout()
        alerts_buttons.addWidget(alert_types_button)
        alerts_buttons.addWidget(thresholds_button)
        alerts_form = QFormLayout()
        self.focus_picker = QComboBox()
        for text, focus in FOCUS_CHOICES:
            self.focus_picker.addItem(text, focus)
        self.focus_picker.setToolTip('In a raid, list everyone, only your own raid group (the character in the active '
                                     'EQ window), or chosen raid groups. Pinned players always show.')
        # "activated" also fires when the already-selected item is picked again, so chosen groups can be re-edited.
        self.focus_picker.activated.connect(self.pick_focus)
        alerts_form.addRow('Watch', self.focus_picker)
        self.show_focus()
        self.distance_box = QCheckBox(SETTINGS['range'][3])
        self.distance_box.setToolTip('Show how far away listed players are when they are farther than this, '
                                     'e.g. (150 away), or (other zone).')
        self.distance_box.setChecked(overlay.settings['distance_warning'])
        self.distance_box.toggled.connect(self.set_distance_warning)
        alerts_form.addRow(self.distance_box, self.make_setting_spin('range'))
        self.spins['range'].setEnabled(overlay.settings['distance_warning'])
        alerts_layout = QVBoxLayout(alerts_box)
        alerts_layout.addLayout(alerts_buttons)
        alerts_layout.addLayout(alerts_form)
        self.dialogs = {}

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

        defaults_button = QPushButton('Restore defaults')
        defaults_button.setToolTip(
            'Reset the Overlay and Alerts settings, including alert types, sounds and class thresholds. '
            'Pins, position and lock are kept.'
        )
        defaults_button.clicked.connect(self.restore_defaults)
        docs_button = QPushButton('Read the docs')
        docs_button.clicked.connect(open_docs)
        quit_button = QPushButton('Quit')
        quit_button.clicked.connect(QApplication.quit)
        buttons = QHBoxLayout()
        buttons.addWidget(defaults_button)
        buttons.addStretch()
        buttons.addWidget(docs_button)
        buttons.addWidget(quit_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        layout.addWidget(self.update_notice)
        layout.addWidget(overlay_box)
        layout.addWidget(alerts_box)
        layout.addWidget(pins_box)
        layout.addLayout(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(STATUS_MS)
        self.refresh()

    def change_setting(self, key, value):
        self.overlay.settings[key] = value
        save_json(SETTINGS_FILE, self.overlay.settings)
        if key in ('font_size', 'width', 'rows'):
            self.overlay.apply_font()
        self.overlay.redraw()

    def add_spins(self, form, keys):
        for key in keys:
            form.addRow(SETTINGS[key][3], self.make_setting_spin(key))

    def make_setting_spin(self, key):
        _, minimum, maximum, _, suffix = SETTINGS[key]
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(suffix)
        spin.setValue(self.overlay.settings[key])
        spin.valueChanged.connect(lambda value: self.change_setting(key, value))
        self.spins[key] = spin
        return spin

    def pick_focus(self):
        settings = self.overlay.settings
        focus = self.focus_picker.currentData()
        if focus == FOCUS_GROUPS:
            chooser = RaidGroupsDialog(self, settings['focus_groups'])
            if not chooser.exec() or not chooser.chosen():
                # Cancelled, or no group ticked: keep the previous choice.
                self.show_focus()
                return
            settings['focus_groups'] = chooser.chosen()
        settings['focus'] = focus
        self.save_and_redraw()
        self.show_focus()

    def show_focus(self):
        settings = self.overlay.settings
        index = self.focus_picker.findData(FOCUS_GROUPS)
        groups = settings['focus_groups']
        self.focus_picker.setItemText(index, f'Groups {", ".join(map(str, groups))}' if groups else FOCUS_GROUPS_TEXT)
        self.focus_picker.setCurrentIndex(self.focus_picker.findData(settings['focus']))

    def set_distance_warning(self, enabled):
        self.overlay.settings['distance_warning'] = enabled
        self.spins['range'].setEnabled(enabled)
        self.save_and_redraw()

    def open_dialog(self, dialog_class):
        # One instance per dialog, reused, so reopening shows it as it was left.
        if dialog_class not in self.dialogs:
            self.dialogs[dialog_class] = dialog_class(self)
        dialog = self.dialogs[dialog_class]
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def save_and_redraw(self):
        save_json(SETTINGS_FILE, self.overlay.settings)
        self.overlay.redraw()

    def set_locked(self, locked):
        self.overlay.settings['locked'] = locked
        save_json(SETTINGS_FILE, self.overlay.settings)

    def restore_defaults(self):
        for key, (default, *_) in SETTINGS.items():
            self.spins[key].setValue(default)
        self.overlay.settings['thresholds'] = default_thresholds()
        self.overlay.settings.update(event_defaults({}))
        self.distance_box.setChecked(True)
        self.overlay.settings['focus'] = FOCUS_ALL
        self.overlay.settings['focus_groups'] = []
        self.overlay.settings['drop_rate'] = DEFAULT_DROP_RATE
        self.show_focus()
        self.save_and_redraw()
        for dialog in self.dialogs.values():
            dialog.load()

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
            release = newer_release
        if release and self.update_notice.isHidden():
            version, url = release
            self.update_notice.setText(f'<span style="color:{STATUS_OK}">&#9650;</span> {APP_NAME} {version} is '
                                       f'available. <a href="{url}">Download it</a>')
            self.update_notice.show()
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


class RaidGroupsDialog(QDialog):
    # Tick the raid groups to watch. Only used while choosing, so it asks and returns rather than saving live.
    def __init__(self, parent, chosen):
        super().__init__(parent)
        self.setWindowTitle(f'{APP_NAME}: raid groups to watch')
        self.boxes = []
        grid = QGridLayout()
        for number in range(1, RAID_GROUPS + 1):
            box = QCheckBox(f'Group {number}')
            box.setChecked(number in chosen)
            grid.addWidget(box, (number - 1) // RAID_GROUP_COLUMNS, (number - 1) % RAID_GROUP_COLUMNS)
            self.boxes.append(box)
        ok_button = QPushButton('OK')
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Show players from these raid groups. Pinned players always show.'))
        layout.addLayout(grid)
        layout.addLayout(buttons)

    def chosen(self):
        return [number for number, box in enumerate(self.boxes, start=1) if box.isChecked()]


class AlertTypesDialog(QDialog):
    # For each alert type: whether it shows on the overlay, and separately whether it plays a sound and which one.
    # Changes apply and save live.
    def __init__(self, control):
        super().__init__(control)
        self.control = control
        self.setWindowTitle(f'{APP_NAME}: alert types & sounds')
        self.boxes = {'show': {}, 'sound': {}}
        self.pickers = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(GRID_SPACING)
        # Columns: alert name | divider | Show on overlay | divider | Play sound checkbox, sound picker, play button.
        grid.setColumnMinimumWidth(1, DIVIDER_COLUMN_WIDTH)
        grid.setColumnMinimumWidth(2, SHOW_COLUMN_WIDTH)
        grid.setColumnMinimumWidth(3, DIVIDER_COLUMN_WIDTH)
        grid.addWidget(QLabel('<b>Show on overlay</b>'), 0, 2, Qt.AlignCenter)
        grid.addWidget(QLabel('<b>Play sound</b>'), 0, 4, 1, 3, Qt.AlignLeft | Qt.AlignVCenter)
        # Vertical lines set the alert names apart from the settings, and split the two independent questions.
        for column in (1, 3):
            divider = QFrame()
            divider.setFrameShape(QFrame.VLine)
            divider.setFrameShadow(QFrame.Sunken)
            grid.addWidget(divider, 0, column, len(EVENTS) + 1, 1, Qt.AlignHCenter)
        self.drop_rate = QSpinBox()
        self.drop_rate.setRange(*DROP_RATE_RANGE)
        self.drop_rate.setSuffix('% HP/sec')
        self.drop_rate.setToolTip('A player losing health faster than this gets \u25bc after their health, '
                                  'and is listed even above their warning level.')
        self.drop_rate.valueChanged.connect(self.change_drop_rate)
        for row, (key, (label, _, has_sound)) in enumerate(EVENTS.items(), start=1):
            if key == 'dropping':
                # Its rate setting sits in its own row rather than apart from the grid.
                cell = QHBoxLayout()
                cell.addWidget(QLabel(f'{label}, over'))
                cell.addWidget(self.drop_rate)
                cell.addStretch()
                grid.addLayout(cell, row, 0)
            else:
                grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(self.make_box('show', key), row, 2, Qt.AlignCenter)
            if has_sound is not None:
                grid.addWidget(self.make_box('sound', key), row, 4, Qt.AlignCenter)
                grid.addWidget(self.make_picker(key), row, 5)
                test_button = QPushButton('\u25b6')
                test_button.setFixedWidth(TEST_BUTTON_WIDTH)
                test_button.setToolTip('Play this sound')
                test_button.clicked.connect(lambda _, key=key: self.play(key))
                grid.addWidget(test_button, row, 6)
        grid.setColumnStretch(0, 1)
        note = QLabel('<i>Show on overlay</i> and <i>Play sound</i> are independent: an alert can show without a '
                      'sound, or sound without showing. Sounds play when an alert starts, and only the most urgent '
                      'one when several start together.')
        note.setWordWrap(True)
        close_button = QPushButton('Close')
        close_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addSpacing(NOTE_SPACING)
        layout.addLayout(grid)
        layout.addLayout(buttons)
        self.load()

    def make_picker(self, key):
        picker = QComboBox()
        for sound, (name, _) in SOUNDS.items():
            picker.addItem(name, sound)
        picker.insertSeparator(picker.count())
        picker.addItem(CUSTOM_ITEM_TEXT, CUSTOM_SOUND)
        picker.setMinimumContentsLength(PICKER_CHARS)
        picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        picker.setToolTip('The sound this alert plays. Picking one plays it. Custom file\u2026 uses your own .wav.')
        picker.currentIndexChanged.connect(lambda: self.pick(key))
        self.pickers[key] = picker
        return picker

    def pick(self, key):
        settings = self.control.overlay.settings
        choice = self.pickers[key].currentData()
        if choice == CUSTOM_SOUND:
            start = os.path.dirname(settings['custom_sounds'].get(key, '')) or APP_DIR
            path, _ = QFileDialog.getOpenFileName(self, f'{APP_NAME}: choose a sound', start, 'WAV sounds (*.wav)')
            if not path:
                # Cancelled: put the picker back on the previous choice.
                self.load()
                return
            settings['custom_sounds'][key] = path
        settings['sound_choice'][key] = choice
        self.control.save_and_redraw()
        self.load()
        self.play(key)

    def play(self, key):
        self.control.overlay.sounds.play(self.control.overlay.settings, key)

    def make_box(self, group, key):
        box = QCheckBox()
        box.toggled.connect(lambda checked: self.change(group, key, checked))
        self.boxes[group][key] = box
        return box

    def load(self):
        settings = self.control.overlay.settings
        checks = [(box, settings[group][key]) for group, boxes in self.boxes.items() for key, box in boxes.items()]
        for box, checked in checks:
            box.blockSignals(True)
            box.setChecked(checked)
            box.blockSignals(False)
        self.drop_rate.blockSignals(True)
        self.drop_rate.setValue(settings['drop_rate'])
        self.drop_rate.blockSignals(False)
        for key, picker in self.pickers.items():
            picker.blockSignals(True)
            custom = settings['custom_sounds'].get(key)
            index = picker.findData(CUSTOM_SOUND)
            picker.setItemText(index, f'Custom: {os.path.basename(custom)}' if custom else CUSTOM_ITEM_TEXT)
            # The full path, for when a long file name is cut short in the picker.
            picker.setItemData(index, custom or None, Qt.ToolTipRole)
            picker.setCurrentIndex(picker.findData(settings['sound_choice'][key]))
            picker.blockSignals(False)

    def change(self, group, key, checked):
        self.control.overlay.settings[group][key] = checked
        self.control.save_and_redraw()

    def change_drop_rate(self, value):
        self.control.overlay.settings['drop_rate'] = value
        self.control.save_and_redraw()


class BulkSpinBox(QSpinBox):
    # A heading's box: 0 shows as a dash while the classes under it differ. Stepping from the dash starts at the
    # highest current level among them instead of at 1%, so a stray click can't set them all to 1%.
    def __init__(self):
        super().__init__()
        self.mixed_start = 0

    def stepBy(self, steps):
        if self.value() == 0:
            self.setValue(self.mixed_start)
        else:
            super().stepBy(steps)


class ThresholdsDialog(QDialog):
    # A table of warning and critical levels per class, grouped by category, plus pets and unknown classes.
    # The All classes row and each category heading set every class beneath them at once. Changes apply and save live.
    def __init__(self, control):
        super().__init__(control)
        self.control = control
        self.setWindowTitle(f'{APP_NAME}: health thresholds')
        self.spins = {}
        self.bulk_rows = []
        grid = QGridLayout()
        grid.addWidget(QLabel('<b>Warning below</b>'), 0, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('<b>Critical below</b>'), 0, 2, Qt.AlignCenter)
        self.add_bulk_row(grid, 1, 'All classes', THRESHOLD_GROUPS)
        row = 2
        for category, (groups, _) in CATEGORIES.items():
            self.add_bulk_row(grid, row, category, groups)
            row += 1
            for group in groups:
                grid.addWidget(QLabel(f'    {group}'), row, 0)
                list_spin = self.make_spin(lambda value, group=group: self.change(group, 'list', value))
                red_spin = self.make_spin(lambda value, group=group: self.change(group, 'red', value))
                grid.addWidget(list_spin, row, 1)
                grid.addWidget(red_spin, row, 2)
                self.spins[group] = (list_spin, red_spin)
                row += 1
        note = QLabel('Players show in yellow below their class\'s warning level and in red below its critical level. '
                      'A heading sets every class under it; it shows \u2014 while those classes differ. '
                      'Pets have no class in Zeal\'s data, and a class is unknown briefly while data arrives.')
        note.setWordWrap(True)
        defaults_button = QPushButton('Reset to class defaults')
        defaults_button.clicked.connect(self.reset)
        close_button = QPushButton('Close')
        close_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(defaults_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(note)
        layout.addLayout(buttons)
        self.load()

    def make_spin(self, handler, minimum=1, spin_class=QSpinBox):
        spin = spin_class()
        spin.setRange(minimum, 100)
        spin.setSuffix('% HP')
        spin.valueChanged.connect(handler)
        return spin

    def add_bulk_row(self, grid, row, label, groups):
        # 0 stands for "the classes below differ" and is shown as a dash; it is never applied.
        list_spin = self.make_spin(lambda value: self.set_bulk(groups, 'list', value), 0, BulkSpinBox)
        red_spin = self.make_spin(lambda value: self.set_bulk(groups, 'red', value), 0, BulkSpinBox)
        for spin in (list_spin, red_spin):
            spin.setSpecialValueText('\u2014')
        grid.addWidget(QLabel(f'<b>{label}</b>'), row, 0)
        grid.addWidget(list_spin, row, 1)
        grid.addWidget(red_spin, row, 2)
        self.bulk_rows.append((groups, list_spin, red_spin))

    def load(self):
        # Show the saved levels without treating it as a change.
        thresholds = self.control.overlay.settings['thresholds']
        for group, (list_spin, red_spin) in self.spins.items():
            for spin in (list_spin, red_spin):
                spin.blockSignals(True)
            list_spin.setValue(thresholds[group]['list'])
            # Critical is the stronger warning, so it can never go above the warning level.
            red_spin.setMaximum(thresholds[group]['list'])
            red_spin.setValue(thresholds[group]['red'])
            for spin in (list_spin, red_spin):
                spin.blockSignals(False)
        self.show_bulk()

    def show_bulk(self):
        thresholds = self.control.overlay.settings['thresholds']
        for groups, list_spin, red_spin in self.bulk_rows:
            for spin, level in ((list_spin, 'list'), (red_spin, 'red')):
                values = {thresholds[group][level] for group in groups}
                spin.mixed_start = max(values)
                spin.blockSignals(True)
                spin.setValue(values.pop() if len(values) == 1 else 0)
                spin.blockSignals(False)

    def change(self, group, level, value):
        self.control.overlay.settings['thresholds'][group][level] = value
        if level == 'list':
            # Lowering the warning level below the critical level pulls the critical level down with it.
            self.spins[group][1].setMaximum(value)
        self.control.save_and_redraw()
        self.show_bulk()

    def set_bulk(self, groups, level, value):
        if value == 0:
            return
        for group in groups:
            self.spins[group][0 if level == 'list' else 1].setValue(value)
        self.show_bulk()

    def reset(self):
        self.control.overlay.settings['thresholds'] = default_thresholds()
        self.load()
        self.control.save_and_redraw()


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
    parser = argparse.ArgumentParser(
        description=f'{APP_NAME}: on-screen alerts for low HP, charm breaks and charmers being hit.'
    )
    parser.add_argument('--dump', action='store_true', help='print every change to the group and pet gauges')
    args = parser.parse_args()

    threading.Thread(target=scan_pipes, args=(args,), daemon=True).start()
    threading.Thread(target=check_for_update, daemon=True).start()

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
