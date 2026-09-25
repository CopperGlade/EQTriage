"""Tests for EQ Triage's decision logic. Run with: python -m pytest tests"""

import json
import logging
import types

import pytest
from PySide6.QtCore import Qt

import triage
from conftest import REAL_WRITE_SOUND

PIPE = 'zeal_1'
OTHER_PIPE = 'zeal_2'
ENCHANTER = 14
WARRIOR = 1
WIZARD = 12


def message(kind, data, character='Sebik'):
    return json.dumps({'type': kind, 'data': json.dumps(data), 'character': character}).encode()


def member(name, hp, class_number=WARRIOR, **extra):
    return {'name': name, 'spawn_id': 1, 'hp_current': hp, 'hp_max': 100, 'class': class_number, **extra}


def gauge(kind, text, value):
    return {'type': kind, 'text': text, 'value': value}


class FakePipe:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, size):
        return self.chunks.pop(0) if self.chunks else b''

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def names(rows):
    return [(prefix, name, suffix) for prefix, name, suffix, _, _ in rows if name]


# Stream parsing and the pipe reader


def test_messages_are_parsed_across_chunk_boundaries():
    first = message(triage.GROUP_TYPE, [member('Mera', 50)])
    second = message(triage.PLAYER_TYPE, {'location': {'x': 1, 'y': 2, 'z': 3}})
    stream = first + b'  ' + second
    chunks = [stream[:20], stream[20:len(first) + 5], stream[len(first) + 5:]]
    parsed = list(triage.read_messages(FakePipe(chunks)))
    assert [m['type'] for m in parsed] == [triage.GROUP_TYPE, triage.PLAYER_TYPE]


def test_a_bad_message_is_skipped_and_the_feed_continues(monkeypatch, caplog):
    broken = json.dumps({'type': triage.GAUGE_TYPE, 'data': 5, 'character': 'Sebik'}).encode()
    good = message(triage.GROUP_TYPE, [member('Mera', 40)])
    monkeypatch.setattr(triage, 'open', lambda *a, **k: FakePipe([broken, broken, good]), raising=False)
    triage.connected.add(PIPE)
    with caplog.at_level(logging.ERROR, logger='triage'):
        triage.read_pipe(PIPE, types.SimpleNamespace(dump=False))
    assert 'Mera' in triage.members
    assert PIPE not in triage.connected
    assert sum(record.levelno == logging.ERROR for record in caplog.records) == 1


def test_handle_message_records_the_character_and_dispatches():
    watcher = triage.PetWatcher(PIPE, False)
    triage.handle_message(json.loads(message(triage.GROUP_TYPE, [member('Mera', 30)])), PIPE, watcher)
    assert triage.pipe_characters[PIPE] == 'Sebik'
    assert triage.members['Mera'][0] == 30
    assert triage.member_classes['Mera'] == WARRIOR


# Members, health history and dropping fast


def test_missing_hp_in_zone_means_pipeverbose_is_off():
    triage.handle_members([{'name': 'Mera', 'spawn_id': 3}], PIPE)
    assert triage.verbose_missing
    triage.handle_members([member('Mera', 90)], PIPE)
    assert not triage.verbose_missing


def test_raid_member_out_of_zone_is_not_a_pipeverbose_problem():
    triage.handle_members([{'name': 'Mera', 'group': '2'}], PIPE)
    assert not triage.verbose_missing
    assert triage.raid_groups['Mera'][0] == '2'


def test_drop_rate_is_measured_per_client(clock):
    triage.handle_members([member('Mera', 100)], PIPE)
    triage.handle_members([member('Mera', 100)], OTHER_PIPE)
    clock.advance(0.5)
    triage.handle_members([member('Mera', 85)], PIPE)
    triage.handle_members([member('Mera', 100)], OTHER_PIPE)
    clock.advance(0.5)
    triage.handle_members([member('Mera', 70)], PIPE)
    assert triage.drop_rate('Mera') == pytest.approx(30)
    assert triage.history_rate(triage.hp_history['Mera'][OTHER_PIPE]) == 0


def fall(name, readings, clock, step=0.5):
    # Feeds readings step seconds apart, e.g. (100, 90, 80) is two drops over one second.
    for index, hp in enumerate(readings):
        if index:
            clock.advance(step)
        triage.handle_members([member(name, hp)], PIPE)


def test_dropping_fast_is_listed_above_warning_and_held(clock, settings, caplog):
    with caplog.at_level(logging.INFO, logger='triage'):
        fall('Mera', (100, 90, 80), clock)
        triage.update_dropping(settings)
    rows = triage.alert_rows(settings, [])
    assert names(rows)[0] == ('', 'Mera', ' 80%' + triage.DROP_MARKER)
    assert [r.getMessage() for r in caplog.records] == ['DROPPING Mera at 80% losing 20% per second']
    triage.update_dropping(settings)
    assert len(caplog.records) == 1, 'a held marker is logged once'
    # The hold keeps the marker for a moment once the fall stops.
    clock.advance(1.0)
    triage.handle_members([member('Mera', 80)], PIPE)
    assert names(triage.alert_rows(settings, []))[0][2].endswith(triage.DROP_MARKER)
    clock.advance(1.0)
    triage.handle_members([member('Mera', 80)], PIPE)
    assert names(triage.alert_rows(settings, [])) == []


def test_a_single_spike_is_not_dropping_fast(clock, settings):
    fall('Mera', (100, 100, 70), clock)
    triage.update_dropping(settings)
    assert triage.drop_rate('Mera') == 0
    assert names(triage.alert_rows(settings, [])) == []


def test_a_slow_loss_over_two_hits_is_not_dropping_fast(clock, settings):
    fall('Mera', (100, 95, 90), clock)
    triage.update_dropping(settings)
    assert triage.drop_rate('Mera') == pytest.approx(10)
    assert names(triage.alert_rows(settings, [])) == []


def test_a_fast_fall_ranks_above_a_steady_low(clock, settings):
    triage.handle_members([member('Mera', 35)], PIPE)
    fall('Sebik', (100, 88, 75), clock)
    triage.handle_members([member('Mera', 35)], PIPE)
    triage.update_dropping(settings)
    assert [name for _, name, _ in names(triage.alert_rows(settings, []))] == ['Sebik', 'Mera']


# Rows


def test_rows_follow_the_documented_order(clock, settings):
    triage.handle_members([member('Sebik', 20), member('Mera', 90)], PIPE)
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    triage.deaths['Sebik'] = clock.now
    rows = names(triage.alert_rows(settings, []))
    assert rows == [
        (triage.CHARM_BREAK_PREFIX, 'Mera', ''), (triage.PET_ROW_PREFIX, 'Quillmane', ''), ('DEAD ', 'Sebik', ''),
    ]


def test_charmer_hit_shows_before_charm_break_and_carries_health(clock, settings):
    triage.handle_members([member('Mera', 80)], PIPE)
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    triage.charmer_hits['Mera'] = clock.now
    assert names(triage.alert_rows(settings, [])) == [
        (triage.CHARMER_HIT_PREFIX, 'Mera', ' 80%'), (triage.PET_ROW_PREFIX, 'Quillmane', ''),
    ]


def test_loose_pet_row_follows_every_charm_row_including_pinned(clock, settings):
    triage.handle_members([member('Mera', 80), member('Sebik', 90)], PIPE)
    triage.charm_breaks['Mera'] = ('a_Soriz_Slave00', clock.now)
    triage.charm_breaks['Sebik'] = ('Quillmane', clock.now)
    rows = [row for row in triage.alert_rows(settings, ['Sebik']) if row[1]]
    assert rows == [
        (triage.CHARM_BREAK_PREFIX, 'Sebik', '', triage.CHARMER_COLOR, 'Sebik'),
        (triage.PET_ROW_PREFIX, 'Quillmane', '', triage.CHARMER_COLOR, None),
        (triage.CHARM_BREAK_PREFIX, 'Mera', '', triage.CHARMER_COLOR, 'Mera'),
        (triage.PET_ROW_PREFIX, 'a Soriz Slave', '', triage.CHARMER_COLOR, None),
    ]


def test_no_pet_row_without_a_pet_name(clock, settings):
    triage.handle_members([member('Mera', 80)], PIPE)
    triage.charm_breaks['Mera'] = ('', clock.now)
    assert names(triage.alert_rows(settings, [])) == [(triage.CHARM_BREAK_PREFIX, 'Mera', '')]


def test_pet_rows_count_toward_the_row_limit(clock, settings):
    settings['rows'] = 3
    triage.handle_members([member('Mera', 80), member('Sebik', 80)], PIPE)
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    triage.charm_breaks['Sebik'] = ('a Soriz Slave', clock.now)
    assert names(triage.alert_rows(settings, [])) == [
        (triage.CHARM_BREAK_PREFIX, 'Mera', ''), (triage.PET_ROW_PREFIX, 'Quillmane', ''),
        (triage.CHARM_BREAK_PREFIX, 'Sebik', ''),
    ]


@pytest.mark.parametrize('raw, shown', [
    ('A Soriz Slave', 'A Soriz Slave'),
    ('a_Shissar_Defiler00', 'a Shissar Defiler'),
    (' Quillmane ', 'Quillmane'),
    ('', ''),
])
def test_clean_pet_name(raw, shown):
    assert triage.clean_pet_name(raw) == shown


def test_low_health_sorts_by_distance_to_each_own_critical_level(settings):
    # A wizard at 55% is 5 points above its 50% critical level; a warrior at 35% is 10 above its 25%.
    triage.handle_members([member('Sebik', 35, WARRIOR), member('Mera', 55, WIZARD)], PIPE)
    rows = names(triage.alert_rows(settings, []))
    assert rows == [('', 'Mera', ' 55%'), ('', 'Sebik', ' 35%')]
    colors = [row[3] for row in triage.alert_rows(settings, []) if row[1]]
    assert colors == [triage.LOW_HP_COLOR, triage.LOW_HP_COLOR]


def test_critical_is_red_and_healthy_pinned_is_white(settings):
    triage.handle_members([member('Sebik', 10), member('Mera', 100)], PIPE)
    rows = [row for row in triage.alert_rows(settings, ['Mera']) if row[1]]
    assert rows[0][:4] == ('', 'Mera', ' 100%', triage.PINNED_COLOR)
    assert rows[1][:4] == ('', 'Sebik', ' 10%', triage.CRITICAL_HP_COLOR)


def test_pinned_player_without_data_shows_dashes(settings):
    rows = names(triage.alert_rows(settings, ['Mera']))
    assert rows == [('', 'Mera', ' --')]


def test_pets_are_listed_with_players_and_cannot_be_pinned(settings):
    triage.handle_members([member('Mera', 100)], PIPE)
    triage.pet_hp['Mera'] = (30, triage.time.monotonic())
    rows = [row for row in triage.alert_rows(settings, []) if row[1]]
    assert rows[0][:3] == ('', 'Mera', ' pet 30%')
    assert rows[0][4] is None


def test_own_characters_are_never_listed_unless_pinned(clock, settings):
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.handle_members([member('Mera', 15)], PIPE)
    triage.handle_own_hp([gauge(triage.PLAYER_HP_GAUGE, '', 150)], 'Sebik', PIPE)
    triage.deaths['Sebik'] = clock.now
    assert names(triage.alert_rows(settings, [])) == [('', 'Mera', ' 15%')]
    assert names(triage.alert_rows(settings, ['Sebik']))[0] == ('', 'Sebik', ' 15%')
    assert triage.current_events(settings) == {('critical', 'Mera')}


def test_include_your_own_character_lists_and_sounds_it(clock, settings):
    settings['include_self'] = True
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.handle_own_hp([gauge(triage.PLAYER_HP_GAUGE, '', 150)], 'Sebik', PIPE)
    assert names(triage.alert_rows(settings, [])) == [('', 'Sebik', ' 15%')]
    assert triage.current_events(settings) == {('critical', 'Sebik')}
    triage.deaths['Sebik'] = clock.now
    assert names(triage.alert_rows(settings, [])) == [('DEAD ', 'Sebik', '')]


def test_own_health_comes_from_the_hp_bar_not_the_raid_entry():
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.handle_members([member('Sebik', 90, group='1'), member('Mera', 90, group='1')], PIPE)
    assert 'Sebik' not in triage.members and triage.members['Mera'][0] == 90
    assert not triage.verbose_missing
    triage.handle_own_hp([gauge(triage.PLAYER_HP_GAUGE, '', 300), gauge(11, 'Mera', 900)], 'Sebik', PIPE)
    assert triage.members['Sebik'][0] == 30


def test_own_hp_bar_arrives_with_the_gauges_in_a_group(settings):
    watcher = triage.PetWatcher(PIPE, False)
    triage.handle_message(json.loads(message(triage.GAUGE_TYPE, [gauge(triage.PLAYER_HP_GAUGE, '', 450)])), PIPE,
                          watcher)
    assert triage.members['Sebik'][0] == 45
    assert names(triage.alert_rows(settings, ['Sebik'])) == [('', 'Sebik', ' 45%')]


def test_no_own_health_without_a_character_or_hp_bar():
    triage.handle_own_hp([gauge(triage.PLAYER_HP_GAUGE, '', 300)], '', PIPE)
    triage.handle_own_hp([gauge(11, 'Mera', 900)], 'Sebik', PIPE)
    assert triage.members == {}


def label(kind, value):
    return {'type': kind, 'value': value, 'meta': {}}


def test_own_class_comes_from_the_class_label(settings):
    # Outside a raid only the Class label knows your class: a Necromancer at 60% is in the pure caster warning band,
    # where the Unknown class levels (50/30) would not list it at all.
    settings['include_self'] = True
    triage.pipe_characters[PIPE] = 'Sebik'
    labels = [label(1, 'Sebik'), label(triage.CLASS_LABEL, 'Necromancer')]
    triage.handle_message(json.loads(message(triage.LABEL_TYPE, labels)), PIPE, triage.PetWatcher(PIPE, False))
    assert triage.member_classes['Sebik'] == 11
    triage.handle_own_hp([gauge(triage.PLAYER_HP_GAUGE, '', 600)], 'Sebik', PIPE)
    rows = triage.alert_rows(settings, [])
    assert names(rows) == [('', 'Sebik', ' 60%')] and rows[0][3] == triage.LOW_HP_COLOR


def test_class_label_ignores_case_and_spaces_and_logs_other_text_once(caplog):
    triage.handle_labels([label(triage.CLASS_LABEL, 'Shadowknight')], 'Sebik')
    assert triage.member_classes['Sebik'] == 5
    with caplog.at_level(logging.WARNING, logger='triage'):
        for _ in range(3):
            triage.handle_labels([label(triage.CLASS_LABEL, 'Warlock')], 'Sebik')
        triage.handle_labels([label(triage.CLASS_LABEL, '')], 'Sebik')
        triage.handle_labels([label(triage.CLASS_LABEL, 'Wizard')], '')
    assert triage.member_classes == {'Sebik': 5}, 'other text keeps the class already known'
    assert len(caplog.records) == 1


def test_own_pet_still_shows(settings):
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.pet_hp['Sebik'] = (20, triage.time.monotonic())
    assert names(triage.alert_rows(settings, [])) == [('', 'Sebik', ' pet 20%')]


def test_rows_are_padded_to_the_row_count(settings):
    rows = triage.alert_rows(settings, [])
    assert len(rows) == settings['rows']
    assert rows == [triage.EMPTY_ROW] * settings['rows']


def test_pipeverbose_reminder_row_comes_first(monkeypatch, settings):
    monkeypatch.setattr(triage, 'verbose_missing', True)
    assert triage.alert_rows(settings, [])[0] == triage.VERBOSE_ROW


# Distance


def test_distance_tags_far_players_only(settings):
    now = triage.time.monotonic()
    triage.own_locations[PIPE] = ((0, 0, 0), now)
    triage.member_locations[(PIPE, 'Mera')] = ((145, 0, 0), now)
    triage.handle_members([member('Mera', 30), member('Sebik', 30)], PIPE)
    rows = names(triage.alert_rows(settings, [], PIPE))
    assert ('', 'Mera', ' 30% (150 away)') in rows
    assert ('', 'Sebik', ' 30%') in rows, 'no position means no distance, never another zone'


def test_own_character_has_no_distance_solo_or_in_a_group(settings):
    # Zeal's group list leaves you out, so your own character never has a member position.
    settings['include_self'] = True
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.handle_player({'location': {'x': 0, 'y': 0, 'z': 0}}, PIPE)
    triage.handle_own_hp([gauge(triage.PLAYER_HP_GAUGE, '', 300)], 'Sebik', PIPE)
    assert names(triage.alert_rows(settings, [], PIPE)) == [('', 'Sebik', ' 30%')]
    triage.handle_members([member('Mera', 90, loc={'x': 500, 'y': 0, 'z': 0})], PIPE)
    assert names(triage.alert_rows(settings, [], PIPE)) == [('', 'Sebik', ' 30%')]


def test_no_distance_without_own_position_or_when_switched_off(settings):
    now = triage.time.monotonic()
    triage.member_locations[(PIPE, 'Mera')] = ((500, 0, 0), now)
    triage.handle_members([member('Mera', 30)], PIPE)
    assert names(triage.alert_rows(settings, [], PIPE)) == [('', 'Mera', ' 30%')]
    triage.own_locations[PIPE] = ((0, 0, 0), now)
    settings['distance_warning'] = False
    assert names(triage.alert_rows(settings, [], PIPE)) == [('', 'Mera', ' 30%')]


def test_dead_and_charm_break_rows_are_never_tagged(clock, settings):
    triage.own_locations[PIPE] = ((0, 0, 0), clock.now)
    triage.member_locations[(PIPE, 'Mera')] = ((900, 0, 0), clock.now)
    triage.handle_members([member('Mera', 30)], PIPE)
    triage.deaths['Mera'] = clock.now
    assert names(triage.alert_rows(settings, [], PIPE)) == [('DEAD ', 'Mera', '')]
    del triage.deaths['Mera']
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    assert names(triage.alert_rows(settings, [], PIPE)) == [
        (triage.CHARM_BREAK_PREFIX, 'Mera', ''), (triage.PET_ROW_PREFIX, 'Quillmane', ''),
    ]


def test_pet_row_is_bare_while_its_charmer_hit_row_is_marked_and_tagged(clock, settings):
    triage.own_locations[PIPE] = ((0, 0, 0), clock.now)
    triage.member_locations[(PIPE, 'Mera')] = ((145, 0, 0), clock.now)
    fall('Mera', (100, 90, 80), clock)
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    triage.charmer_hits['Mera'] = clock.now
    triage.update_dropping(settings)
    # The marker comes before the distance, the same order as the preview's sample row.
    assert names(triage.alert_rows(settings, [], PIPE)) == [
        (triage.CHARMER_HIT_PREFIX, 'Mera', f' 80%{triage.DROP_MARKER} (150 away)'),
        (triage.PET_ROW_PREFIX, 'Quillmane', ''),
    ]


def test_with_distance_rounds_halves_up():
    row = ('', 'Mera', ' 30%', triage.LOW_HP_COLOR, 'Mera')
    assert triage.with_distance(row, 74.9)[2] == ' 30% (70 away)'
    assert triage.with_distance(row, 75)[2] == ' 30% (80 away)'


# Target distance


def target(spawn_id, own=(0, 0, 0)):
    triage.handle_player({'location': {'x': own[0], 'y': own[1], 'z': own[2]}, 'target_id': spawn_id}, PIPE)


def test_target_in_group_shows_its_distance(settings):
    triage.handle_members([{'name': 'Mera', 'spawn_id': 42, 'loc': {'x': 30, 'y': 40, 'z': 0}}], PIPE)
    target(42)
    with triage.state_lock:
        row = triage.target_row(settings, PIPE, triage.time.monotonic())
    assert row[:4] == ('', '50', '', triage.PINNED_COLOR)
    for x, y, text, color in ((60, 80, '100', triage.PINNED_COLOR), (90, 120, '150', triage.LOW_HP_COLOR),
                              (300, 400, '500', triage.CRITICAL_HP_COLOR)):
        triage.handle_members([{'name': 'Mera', 'spawn_id': 42, 'loc': {'x': x, 'y': y, 'z': 0}}], PIPE)
        with triage.state_lock:
            row = triage.target_row(settings, PIPE, triage.time.monotonic())
        assert row[:4] == ('', text, '', color)


def test_distance_overlay_has_its_own_look_settings(qapp, settings):
    assert (settings['target_font_size'], settings['target_opacity'], settings['target_show_header']) == (10, 70, True)
    window = triage.TargetWindow(settings)
    before = window.text_width
    settings['font_size'] = 20
    window.apply_font()
    assert window.text_width == before, 'the Triage overlay text size leaves it alone'
    settings['target_font_size'] = 20
    window.apply_font()
    assert window.text_width > before
    settings['show_header'] = False
    assert window.frame_shown()
    settings['target_show_header'] = False
    assert not window.frame_shown()
    settings['target_opacity'] = 0
    assert window.opacity() == 0 and triage.TriageWindow(settings).opacity() == 70
    assert settings['target_locked'] is False
    settings['locked'] = True
    assert not window.locked() and triage.TriageWindow(settings).locked()
    settings['target_locked'] = True
    assert window.locked()


def test_each_overlay_has_its_own_show_switch(tmp_path, settings):
    assert settings['triage_window'] is True and settings['target_window'] is True
    (tmp_path / 'settings.json').write_text(json.dumps({'triage_window': False, 'target_window': False}))
    settings = triage.load_settings()
    assert settings['triage_window'] is False and settings['target_window'] is False
    (tmp_path / 'settings.json').write_text(json.dumps({'triage_window': 'no'}))
    assert triage.load_settings()['triage_window'] is True, 'anything but False keeps the list'


def test_distance_cutoffs_load_in_order(tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({'target_near': 300, 'target_far': 150}))
    settings = triage.load_settings()
    assert (settings['target_near'], settings['target_far']) == (150, 150)
    (tmp_path / 'settings.json').write_text('{}')
    settings = triage.load_settings()
    assert (settings['target_near'], settings['target_far']) == (100, 200)


def test_target_member_without_a_position_has_no_distance(clock, settings):
    # Zeal sends a spawn id and a position together, so a member without a fresh position has no distance.
    triage.handle_members([{'name': 'Mera', 'spawn_id': 42, 'loc': {'x': 30, 'y': 40, 'z': 0}}], PIPE)
    clock.advance(triage.STALE_SECONDS)
    triage.handle_members([{'name': 'Mera', 'spawn_id': 42}], PIPE)
    target(42)
    with triage.state_lock:
        assert triage.target_row(settings, PIPE, clock.now) == triage.NO_DISTANCE_ROW


def test_target_outside_the_group_shows_dashes(settings):
    triage.handle_members([{'name': 'Mera', 'spawn_id': 42, 'loc': {'x': 30, 'y': 40, 'z': 0}}], PIPE)
    target(99)
    with triage.state_lock:
        row = triage.target_row(settings, PIPE, triage.time.monotonic())
    assert row == triage.NO_DISTANCE_ROW


def test_no_target_or_stale_target_gives_an_empty_row(clock, settings):
    with triage.state_lock:
        assert triage.target_row(settings, PIPE, clock.now) == triage.EMPTY_ROW
    triage.handle_player({'location': {'x': 0, 'y': 0, 'z': 0}}, PIPE)
    with triage.state_lock:
        assert triage.target_row(settings, PIPE, clock.now) == triage.EMPTY_ROW
    target(42)
    clock.advance(triage.STALE_SECONDS)
    with triage.state_lock:
        assert triage.target_row(settings, PIPE, clock.now) == triage.EMPTY_ROW


def test_position_file_keeps_both_windows(tmp_path):
    triage.save_position(10, 20)
    triage.save_position(30, 40, triage.TARGET_POSITION_KEY)
    triage.save_position(11, 21)
    assert triage.load_position() == (11, 21)
    assert triage.load_position(triage.TARGET_POSITION_KEY) == (30, 40)
    assert triage.load_position('other') is None


def test_target_window_is_one_row_without_pins(qapp, settings):
    window = triage.TargetWindow(settings)
    assert window.height() == triage.HEADER_HEIGHT + window.row_height + triage.ROW_GAP
    assert window.width() == 2 * triage.PADDING + window.text_width
    assert window.text_width < triage.TriageWindow(settings).text_width
    settings['font_size'] = 7
    window.apply_font()
    from PySide6.QtGui import QFontMetrics
    assert window.text_width >= QFontMetrics(window.title_font).horizontalAdvance(window.TITLE)
    assert window.sounds is None and window.TITLE == 'Distance'
    window.preview_until = triage.time.monotonic() + 10
    assert window.current_rows() == [triage.TARGET_SAMPLE_ROW]
    window.preview_until = 0
    assert window.current_rows() == [triage.EMPTY_ROW]
    assert settings['target_window'] is True


def test_distance_overlay_is_the_same_with_or_without_its_header(qapp, settings):
    from PySide6.QtGui import QFontMetrics
    window = triage.TargetWindow(settings)
    window.active_pipe = lambda: PIPE
    triage.handle_members([{'name': 'Mera', 'spawn_id': 42, 'loc': {'x': 30, 'y': 40, 'z': 0}}], PIPE)
    target(42)
    title_width = QFontMetrics(window.title_font).horizontalAdvance('Distance')
    assert window.text_width == max(title_width, window.metrics.horizontalAdvance('0') * triage.TARGET_WIDTH)
    shown = (window.width(), window.current_rows())
    assert shown[1][0][:2] == ('', '50')
    settings['target_show_header'] = False
    window.apply_font()
    assert (window.width(), window.current_rows()) == shown, 'just the number, at the same width'
    target(99)
    assert window.current_rows() == [triage.NO_DISTANCE_ROW]
    window.start_preview()
    assert window.current_rows() == [triage.TARGET_SAMPLE_ROW] and triage.TARGET_SAMPLE_ROW[1] == '45'
    assert window.title_text() == 'Distance', '(preview) is left off where it does not fit'
    triage_window = triage.TriageWindow(settings)
    triage_window.start_preview()
    assert triage_window.title_text() == 'Triage (preview)'
    assert window.fit('', '1234', '') == '1234', 'the width fits the longest distance in any zone'
    settings['target_font_size'] = 20
    window.apply_font()
    assert window.fit('', '1234', '') == '1234', 'large text keeps the number whole even though the title stays small'


# Charm breaks


@pytest.mark.parametrize('owner_class, pet, expected', [
    (ENCHANTER, 'Quillmane', True),
    (ENCHANTER, 'a Shissar Defiler', True),
    (ENCHANTER, 'a_Shissar_Defiler00', True),
    (ENCHANTER, 'Gabartik', False),
    (ENCHANTER, 'Xebekn', False),
    (ENCHANTER, 'Sebik`s pet', False),
    (ENCHANTER, 'Sebik`s familiar', False),
    (WARRIOR, 'Quillmane', False),
    (None, 'Quillmane', True),
    (None, '', True),
])
def test_could_be_charm(owner_class, pet, expected):
    if owner_class is not None:
        triage.member_classes['Sebik'] = owner_class
    assert triage.could_be_charm('Sebik', pet) is expected


def test_every_generated_pet_name_is_recognized():
    for first in 'GJKLVXZ':
        for middle in ('', 'ab', 'on', 'ib', 'as', 'ar', 'ob', 'eb', 'en'):
            for third in ('', 'ar', 'an', 'ek', 'ob'):
                for last in ('tik', 'er', 'n', 'ab'):
                    assert triage.SUMMONED_PET_NAME.match(first + middle + third + last)
    assert not triage.SUMMONED_PET_NAME.match('Quillmane')


def test_pet_bar_vanishing_at_health_is_a_charm_break():
    triage.member_classes['Mera'] = ENCHANTER
    watcher = triage.PetWatcher(PIPE, False)
    with_pet = [gauge(11, 'Mera', 900), gauge(17, 'Quillmane', 800)]
    without = [gauge(11, 'Mera', 900), gauge(17, '', 0)]
    watcher.handle_gauges(with_pet, 'Sebik')
    assert triage.pet_hp['Mera'][0] == 80
    watcher.handle_gauges(without, 'Sebik')
    assert 'Mera' not in triage.charm_breaks, 'one missing frame is a flicker, not a break'
    watcher.handle_gauges(without, 'Sebik')
    assert triage.charm_breaks['Mera'][0] == 'Quillmane'


def test_pet_dying_or_a_summoned_pet_is_not_a_charm_break():
    triage.member_classes['Mera'] = ENCHANTER
    watcher = triage.PetWatcher(PIPE, False)
    for pet, value in (('Quillmane', 50), ('Gabartik', 900)):
        watcher.handle_gauges([gauge(11, 'Mera', 900), gauge(17, pet, value)], 'Sebik')
        for _ in range(triage.MISSING_FRAMES):
            watcher.handle_gauges([gauge(11, 'Mera', 900), gauge(17, '', 0)], 'Sebik')
    assert triage.charm_breaks == {}


def test_charmer_taking_damage_after_a_break_is_a_charmer_hit(clock):
    triage.handle_members([member('Mera', 100)], PIPE)
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    triage.handle_members([member('Mera', 100)], PIPE)
    assert 'Mera' not in triage.charmer_hits
    triage.handle_members([member('Mera', 90)], PIPE)
    assert triage.charmer_hits['Mera'] == clock.now


def test_recharm_clears_the_alerts(clock):
    triage.member_classes['Mera'] = ENCHANTER
    triage.charm_breaks['Mera'] = ('Quillmane', clock.now)
    triage.charmer_hits['Mera'] = clock.now
    watcher = triage.PetWatcher(PIPE, False)
    clock.advance(triage.RECHARM_GRACE_SECONDS)
    watcher.handle_gauges([gauge(11, 'Mera', 900), gauge(17, 'Quillmane', 1000)], 'Sebik')
    assert triage.charm_breaks == {} and triage.charmer_hits == {}


# Deaths


@pytest.mark.parametrize('text, who', [
    ('Mera has been slain by a gnoll!', 'Mera'),
    ('[Mon Sep 22 20:00:00 2025] Mera died.', 'Mera'),
    ('You have been slain by a gnoll!', 'Sebik'),
    ('You died.', 'Sebik'),
    ('Gabartik died.', None),
    ('Mera tells you, Mera has been slain by a gnoll!', None),
])
def test_death_lines(text, who):
    triage.handle_members([member('Mera', 100)], PIPE)
    triage.handle_log({'text': text}, 'Sebik')
    assert list(triage.deaths) == ([who] if who else [])


# Sounds


def make_sounds(settings):
    sounds = triage.SoundAlerts(settings)
    sounds.update(settings, set())
    return sounds


def test_first_reading_is_silent(settings):
    sounds = triage.SoundAlerts(settings)
    sounds.update(settings, {('charm_break', 'Mera')})
    assert triage.played == []


def test_the_most_urgent_new_event_plays(settings):
    settings['sound']['low'] = True
    sounds = make_sounds(settings)
    sounds.update(settings, {('low', 'Mera'), ('charmer_hit', 'Sebik')})
    assert triage.played == ['klaxon.wav']


def test_events_with_sound_off_are_silent(settings):
    sounds = make_sounds(settings)
    sounds.update(settings, {('low', 'Mera'), ('death', 'Sebik')})
    assert triage.played == []


def test_same_event_does_not_repeat_within_the_window(clock, settings):
    sounds = make_sounds(settings)
    sounds.update(settings, {('charm_break', 'Mera')})
    sounds.update(settings, set())
    clock.advance(triage.SOUND_REPEAT_SECONDS - 1)
    sounds.update(settings, {('charm_break', 'Mera')})
    assert triage.played == ['rising_chime.wav']
    sounds.update(settings, set())
    clock.advance(2)
    sounds.update(settings, {('charm_break', 'Mera')})
    assert triage.played == ['rising_chime.wav'] * 2


def test_healing_back_from_critical_to_low_is_silent(settings):
    settings['sound']['low'] = settings['sound']['critical'] = True
    sounds = make_sounds(settings)
    sounds.update(settings, {('critical', 'Mera')})
    sounds.update(settings, {('low', 'Mera')})
    assert triage.played == ['double_chirp.wav']


def test_custom_sound_plays_when_present_else_the_default(settings, tmp_path):
    custom = tmp_path / 'tell.wav'
    custom.write_bytes(b'')
    settings['sound_choice']['death'] = triage.CUSTOM_SOUND
    settings['custom_sounds']['death'] = str(custom)
    sounds = make_sounds(settings)
    sounds.play(settings, 'death')
    custom.unlink()
    sounds.play(settings, 'death')
    assert triage.played == [str(custom), 'low_gong.wav']


def test_hidden_alert_types_still_sound(settings):
    triage.handle_members([member('Mera', 20)], PIPE)
    settings['show']['critical'] = False
    settings['sound']['critical'] = True
    assert triage.current_events(settings) == {('critical', 'Mera')}
    assert names(triage.alert_rows(settings, [])) == []


def test_pets_and_dropping_events(clock, settings):
    triage.pet_hp['Mera'] = (30, clock.now)
    fall('Sebik', (100, 85, 70), clock)
    triage.pet_hp['Mera'] = (30, clock.now)
    triage.update_dropping(settings)
    assert triage.current_events(settings) == {('low', 'Mera pet'), ('dropping', 'Sebik')}


def test_rendered_sounds_are_cached_between_runs(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setitem(triage.SOUNDS, 'water_drop', ('Water drop', lambda: calls.append(1) or [0.0, 0.5, -0.5]))
    path = REAL_WRITE_SOUND('water_drop')
    assert path == REAL_WRITE_SOUND('water_drop')
    assert path.endswith(f'water_drop-{triage.SOUND_VERSION}.wav') and calls == [1]


# Settings


def test_defaults_when_nothing_is_saved(settings):
    for key, (default, *_) in triage.SETTINGS.items():
        assert settings[key] == default
    assert settings['thresholds']['Wizard'] == {'list': 75, 'red': 50}
    assert settings['thresholds']['Pets'] == {'list': 40, 'red': 25}
    assert settings['drop_rate'] == 15
    assert settings['hidden_groups'] == [] and not settings['locked'] and settings['distance_warning']
    assert settings['include_self'] is False


def test_saved_values_are_clamped_and_bad_types_ignored(tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({
        'font_size': 99, 'width': True, 'opacity': -5, 'rows': 'ten', 'drop_rate': 1,
        'hidden_groups': [3, 13, 'x', 1], 'locked': 1,
        'thresholds': {'Warrior': {'list': 30, 'red': 60}},
        'sound_choice': {'death': 'nope', 'low': 'bell'},
        'custom_sounds': {'charm_break': 7},
    }))
    settings = triage.load_settings()
    assert settings['font_size'] == 20 and settings['width'] == 28 and settings['opacity'] == 0
    assert settings['rows'] == 8 and settings['drop_rate'] == triage.DROP_RATE_RANGE[0]
    assert settings['hidden_groups'] == [1, 3] and settings['locked'] is False
    assert settings['thresholds']['Warrior'] == {'list': 30, 'red': 30}
    assert settings['sound_choice']['death'] == 'low_gong' and settings['sound_choice']['low'] == 'bell'
    assert settings['custom_sounds'] == {}


def test_changed_legacy_levels_carry_over_to_every_class(tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({'low_hp': 65, 'critical_hp': 20}))
    thresholds = triage.load_settings()['thresholds']
    assert all(levels == {'list': 65, 'red': 20} for levels in thresholds.values())


def test_untouched_legacy_levels_give_way_to_class_defaults(tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({'low_hp': 50, 'critical_hp': 30}))
    assert triage.load_settings()['thresholds'] == triage.default_thresholds()


def test_custom_sound_choice_needs_its_path(tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({'sound_choice': {'death': 'custom'}}))
    assert triage.load_settings()['sound_choice']['death'] == 'low_gong'


# Raid focus


def test_nothing_is_hidden_outside_a_raid_or_before_own_group_is_known(settings):
    now = triage.time.monotonic()
    assert triage.focus_filter(settings, PIPE, now) is None
    settings['hidden_groups'] = [2]
    assert triage.focus_filter(settings, PIPE, now) is None, 'no raid data'
    triage.raid_groups['Mera'] = ('2', now)
    assert triage.focus_filter(settings, PIPE, now) is None, 'own group unknown'


def test_unticked_groups_are_hidden_but_never_your_own(settings):
    now = triage.time.monotonic()
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.raid_groups['Sebik'] = ('1', now)
    triage.raid_groups['Mera'] = ('2', now)
    settings['hidden_groups'] = [1, 2]
    keep = triage.focus_filter(settings, PIPE, now)
    assert keep('Sebik') and not keep('Mera')
    # Ungrouped raid members and players without raid data are kept.
    triage.raid_groups['Mera'] = ('0', now)
    assert triage.focus_filter(settings, PIPE, now)('Mera')
    del triage.raid_groups['Mera']
    assert triage.focus_filter(settings, PIPE, now)('Mera')


def test_scope_hides_rows_and_sounds_but_not_pins(settings):
    now = triage.time.monotonic()
    triage.pipe_characters[PIPE] = 'Sebik'
    triage.raid_groups['Sebik'] = ('1', now)
    triage.raid_groups['Mera'] = ('2', now)
    triage.handle_members([member('Mera', 10)], PIPE)
    settings['hidden_groups'] = [2]
    assert names(triage.alert_rows(settings, [], PIPE)) == []
    assert names(triage.alert_rows(settings, ['Mera'], PIPE)) == [('', 'Mera', ' 10%')]
    assert triage.current_events(settings, PIPE) == set()
    settings['hidden_groups'] = [3]
    assert names(triage.alert_rows(settings, [], PIPE)) == [('', 'Mera', ' 10%')]
    assert triage.current_events(settings, PIPE) == {('critical', 'Mera')}


@pytest.mark.parametrize('hidden, text', [
    ([], 'Entire raid'),
    ([7], 'All but group 7'),
    ([7, 8], 'All but groups 7, 8'),
    (list(range(1, 8)), 'Groups 8, 9, 10, 11, 12 and your own'),
    (list(range(1, 13)), 'Your group only'),
])
def test_scope_text(hidden, text):
    assert triage.scope_text(hidden) == text


# Version and update check


def test_version_tuple_orders_releases():
    assert triage.version_tuple('v1.10.0') > triage.version_tuple('1.9.2')
    assert triage.version_tuple('v1.0.0') == (1, 0, 0)


def test_missing_version_file_gives_the_unknown_version(monkeypatch, tmp_path):
    monkeypatch.setattr(triage, 'BUNDLE_DIR', str(tmp_path))
    assert triage.read_app_version() == triage.UNKNOWN_VERSION
    (tmp_path / 'version_info.txt').write_text('nothing useful')
    assert triage.read_app_version() == triage.UNKNOWN_VERSION


def test_real_version_file_is_read():
    assert triage.APP_VERSION != triage.UNKNOWN_VERSION


# Feed status


def test_feed_status_messages(clock, monkeypatch):
    assert triage.feed_status()[1] == 'Waiting for EverQuest to start.'
    monkeypatch.setattr(triage, 'eq_started', {7: clock.now})
    assert triage.feed_status()[1].startswith('EverQuest is starting')
    clock.advance(triage.ZEAL_GRACE_SECONDS)
    assert "Zeal's feed wasn't found" in triage.feed_status()[1]
    triage.connected.add('zeal_7')
    assert triage.feed_status()[1] == 'Connected. Waiting for you to enter Norrath.'
    triage.own_locations['zeal_7'] = ((0, 0, 0), clock.now)
    triage.pipe_characters['zeal_7'] = 'Sebik'
    assert triage.feed_status()[1] == 'Receiving data from Sebik. Join a group or raid to see other players.'
    triage.handle_members([member('Mera', 100)], 'zeal_7')
    assert triage.feed_status() == (triage.STATUS_OK, 'Receiving data from Sebik.')


# Overlay


def test_preview_shows_one_row_of_each_kind():
    suffixes = [suffix for _, _, suffix, _, _ in triage.SAMPLE_ROWS]
    assert f'{triage.DROP_MARKER} (150 away)' in ''.join(suffixes)
    assert any('pet' in suffix for suffix in suffixes)
    assert [prefix for prefix, _, _, _, _ in triage.SAMPLE_ROWS].count(triage.PET_ROW_PREFIX) == 1
    assert all(name == 'Sebik' for prefix, name, _, _, _ in triage.SAMPLE_ROWS if prefix != triage.PET_ROW_PREFIX)
    assert len(triage.SAMPLE_ROWS) == triage.SETTINGS['rows'][0], 'the preview fills the default row count'


def test_overlay_size_follows_the_settings_and_renders(qapp, settings):
    window = triage.TriageWindow(settings)
    assert window.height() == triage.HEADER_HEIGHT + settings['rows'] * window.row_height + triage.ROW_GAP
    window.rows = triage.padded(triage.SAMPLE_ROWS, settings['rows'])
    image = window.grab().toImage()
    assert not image.isNull() and image.size() == window.size()
    assert window.on_screen(0, 0) and not window.on_screen(100_000, 100_000)


def test_unticking_show_header_hides_the_header_and_bottom_edge_except_in_preview(qapp, settings):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    settings['opacity'] = 0
    window = triage.TriageWindow(settings)
    window.rows = triage.padded(triage.SAMPLE_ROWS, settings['rows'])
    mid = window.width() // 2
    header, bottom = triage.HEADER_HEIGHT // 2, window.height() - 1

    def alpha(y):
        return window.grab().toImage().pixelColor(mid, y).alpha()

    def press_header():
        window.drag_offset = None
        event = QMouseEvent(QEvent.MouseButtonPress, QPointF(mid, header), QPointF(mid, header),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        window.mousePressEvent(event)
        return window.drag_offset is not None

    assert alpha(header) > 0 and alpha(bottom) > 0 and press_header()
    settings['show_header'] = False
    assert alpha(header) == 0 and alpha(bottom) == 0 and not press_header()
    assert window.height() == triage.HEADER_HEIGHT + settings['rows'] * window.row_height + triage.ROW_GAP
    window.preview_until = triage.time.monotonic() + 10
    assert alpha(header) > 0 and alpha(bottom) > 0 and press_header()


def test_show_header_setting_is_saved_and_on_by_default(tmp_path, settings):
    assert settings['show_header'] is True and settings['target_show_header'] is True
    (tmp_path / 'settings.json').write_text(json.dumps({'show_header': False, 'target_show_header': 'x'}))
    loaded = triage.load_settings()
    assert loaded['show_header'] is False and loaded['target_show_header'] is True


def make_control(settings):
    return triage.ControlWindow(triage.TriageWindow(settings), triage.TargetWindow(settings))


def test_include_your_own_character_is_saved_off_by_default_and_restored(qapp, settings, tmp_path):
    control = make_control(settings)
    assert not control.self_box.isChecked()
    control.self_box.setChecked(True)
    assert settings['include_self'] is True and triage.load_settings()['include_self'] is True
    (tmp_path / 'settings.json').write_text(json.dumps({'include_self': 'yes'}))
    assert triage.load_settings()['include_self'] is False
    control.apply_defaults()
    assert settings['include_self'] is False and not control.self_box.isChecked()


def test_configure_windows_hold_the_spins_and_apply_live(qapp, settings):
    control = make_control(settings)
    assert not control.spins.keys() & set(triage.OVERLAY_SETTINGS + triage.DISTANCE_SETTINGS)
    control.open_dialog('triage', lambda: triage.OverlayDialog(control, 'triage overlay', triage.OVERLAY_SETTINGS))
    control.open_dialog('distance', lambda: triage.OverlayDialog(control, 'distance overlay', triage.DISTANCE_SETTINGS))
    assert set(triage.OVERLAY_SETTINGS + triage.DISTANCE_SETTINGS) <= control.spins.keys()
    control.spins['target_font_size'].setValue(14)
    assert settings['target_font_size'] == 14 and control.target.font_size() == 14
    # The white cutoff can't pass the yellow one.
    control.spins['target_far'].setValue(120)
    assert control.spins['target_near'].maximum() == 120
    assert control.dialogs['triage'].windowTitle().endswith('triage overlay')


def test_restore_defaults_works_before_any_configure_window_opened(qapp, settings):
    settings['target_font_size'] = 14
    settings['rows'] = 5
    settings['target_show_header'] = False
    control = make_control(settings)
    control.apply_defaults()
    assert settings['target_font_size'] == 10 and settings['rows'] == 8
    assert settings['target_show_header'] is True and settings['target_window'] is True
    assert control.overlay.height() == triage.HEADER_HEIGHT + 8 * control.overlay.row_height + triage.ROW_GAP


def test_restore_defaults_also_resets_positions_locks_and_pins(qapp, settings, tmp_path):
    settings['locked'] = settings['target_locked'] = True
    control = make_control(settings)
    control.overlay.set_pinned(['Mera'])
    for window in control.windows():
        window.move(5, 5)
        assert (window.x(), window.y()) != window.default_position()
    control.apply_defaults()
    assert settings['locked'] is False and settings['target_locked'] is False
    assert control.overlay.pinned == [] and triage.load_pins() == []
    for window in control.windows():
        assert (window.x(), window.y()) == window.default_position()
    assert triage.load_position() == control.overlay.default_position()
    assert triage.load_position(triage.TARGET_POSITION_KEY) == control.target.default_position()


def test_every_dialog_is_sized_to_its_content(qapp, settings):
    control = make_control(settings)
    dialogs = [
        triage.AlertTypesDialog(control), triage.ThresholdsDialog(control), triage.RaidGroupsDialog(control, []),
        triage.OverlayDialog(control, 'triage overlay', triage.OVERLAY_SETTINGS),
    ]
    for dialog in dialogs:
        dialog.show()
        qapp.processEvents()
        layout = dialog.layout()
        needed = layout.heightForWidth(dialog.width()) if layout.hasHeightForWidth() else layout.sizeHint().height()
        assert dialog.height() == needed, type(dialog).__name__


def test_long_names_are_elided_but_tags_stay(qapp, settings):
    window = triage.TriageWindow(settings)
    text = window.fit('', 'Sebik' * 10, ' 38% (150 away)')
    assert text.endswith(' 38% (150 away)') and '…' in text
