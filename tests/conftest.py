"""Test setup: runs triage.py's logic without Windows, EverQuest or a sound card.

Names in tests are only Sebik and Mera.
"""

import ctypes
import os
import sys
import types

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class WinCalls:
    # Stands in for user32/kernel32/shell32: every call succeeds and returns 0.
    def __getattr__(self, name):
        return lambda *args, **kwargs: 0


if not hasattr(ctypes, 'windll'):
    ctypes.windll = types.SimpleNamespace(user32=WinCalls(), kernel32=WinCalls(), shell32=WinCalls())

import triage  # noqa: E402

REAL_WRITE_SOUND = triage.write_sound
STATE = ('members', 'pet_hp', 'charm_breaks', 'deaths', 'own_locations', 'member_locations', 'charmer_hits',
         'hp_seen', 'hp_history', 'dropping_until', 'member_classes', 'raid_groups', 'pipe_characters',
         'member_messages')


class Clock:
    # Replaces the time module inside triage, so tests move time instead of sleeping.
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for name in STATE:
        getattr(triage, name).clear()
    triage.connected.clear()
    monkeypatch.setattr(triage, 'eq_started', None)
    monkeypatch.setattr(triage, 'verbose_missing', False)
    monkeypatch.setattr(triage, 'newer_release', None)
    monkeypatch.setattr(triage, 'PINS_FILE', str(tmp_path / 'pins.json'))
    monkeypatch.setattr(triage, 'SETTINGS_FILE', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(triage, 'POSITION_FILE', str(tmp_path / 'position.json'))
    monkeypatch.setattr(triage, 'SOUND_DIR', str(tmp_path / 'sounds'))
    # No rendering and no winsound: sounds are recorded as the paths that would have played.
    played = []
    monkeypatch.setattr(triage, 'write_sound', lambda key: f'{key}.wav')
    monkeypatch.setattr(triage, 'play_sound', played.append)
    triage.played = played
    yield


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(triage, 'time', clock)
    return clock


@pytest.fixture
def settings():
    return triage.load_settings()


@pytest.fixture(scope='session')
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
