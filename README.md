# EQ Triage

A healer's overlay for Project Quarm · v1.0.0 · by Sebik &lt;Europa&gt;

EQ Triage sits on top of EverQuest and lists the people who need attention: players and pets at low health, charm breaks, charmers being hit, deaths, and anyone too far away to heal. It only reads game data and draws on screen. It never presses keys or clicks for you.

## Setup

1. **Install Zeal.** EQ Triage gets its data from Zeal's named pipe, so the Project Quarm client must be running with Zeal (`Zeal.asi` in your EverQuest folder). The pipe is on by default.
2. **Turn on detailed data, once.** In game, type `/pipeverbose on`. Without it, Zeal doesn't send player health. Zeal remembers the setting (`PipeVerbose=TRUE` in `zeal.ini`), so you only do this once. If the overlay shows a grey **Type /pipeverbose on** row, this step is missing.
3. **Install EQ Triage.** Download `EQTriage-vX.Y.Z.zip` from the [latest release](https://github.com/CopperGlade/EQTriage/releases/latest) and extract it into your EverQuest folder, next to `eqgame.exe`, so you end up with, for example, `C:\QUARM\EQTriage\EQTriage.exe`.

   Unlike Zeal, EQ Triage is a separate program rather than a plugin, so it works from any folder. Keeping it in its own folder inside EverQuest just keeps everything together. The folder must be one you can write to, because EQ Triage saves its settings there, so avoid `Program Files`.
4. **Start EQ Triage.** Run `EQTriage.exe`. A desktop shortcut to it is handy. It can start before or after EverQuest, and it connects to every EverQuest window you have open, so multiboxing needs no extra setup.
5. **Place the overlay.** Click **Preview** in the EQ Triage window to fill the overlay with sample rows for 10 seconds, then drag it by the *Triage* header to wherever you want it. The position is remembered. Tick **Lock position** once it's where you want it, so a stray click can't move it.

> [!NOTE]
> Windows may show a SmartScreen warning the first time, because the program isn't signed. Choose **More info → Run anyway**.

## Reading the overlay

The overlay has 10 rows by default (adjustable from 3 to 25 in the Overlay settings). Rows appear in this order:

1. **Pinned players**, in the order you pinned them.
2. **Charmer alerts** (`CHARMER HIT`, then `CHARM BREAK`).
3. **Deaths.**
4. **Everyone else below their warning level** (set per class; 40–75% by default) or **dropping fast**, players and pets together, most urgent first.

| Row | Color | Meaning |
|---|---|---|
| `Sebik 45%` | Yellow | A player below their class's warning level (40% melee, 50% hybrid casters, 75% pure casters by default). |
| `Sebik 20%` | Red | A player below their class's critical level (25% melee, 30% hybrid casters, 50% pure casters by default). |
| `Sebik pet 40%` | Yellow | Sebik's pet below the pets' warning level, 50% by default (red below the 30% critical level). |
| `CHARM BREAK Sebik` | Red | Sebik's charmed pet just broke free. Shown for 6 seconds. |
| `CHARMER HIT Sebik 80%` | Red | Sebik is taking damage after a charm break, probably from the freed pet. This is the most urgent row. |
| `DEAD Sebik` | Purple | Sebik died. Shown for 10 seconds. |
| `Sebik 70% ▼` | Yellow | Sebik is losing health fast (more than 10% per second by default), listed even above their warning level. |
| `Sebik 38% (150 away)` | Yellow | A distance warning: 150 units from you, farther than the distance warning setting (70 units by default). |
| `Sebik 38% (other zone)` | Yellow | A distance warning for someone in a different zone. |
| `Sebik 95%` | White | A pinned player at healthy HP. |
| `Sebik --` | Grey | A pinned player with no data right now (zoned, or not in your group or raid). |

Long names are shortened with … so the health and tags always stay visible.

## Features

### Warning and critical health

Group and raid members show in yellow once they drop below their class's warning level and in red below its critical level: 40% / 25% for melee, 50% / 30% for hybrid casters and 75% / 50% for pure casters by default, since they die very fast. Both levels can be changed per class under **Health thresholds…**. Your own pets and your group members' pets are included, sorted in with the players by health. Raid members' pets aren't, because Zeal doesn't send them.

### Dropping fast

A player losing health quickly gets ▼ after their health, e.g. `Sebik 70% ▼`, and is listed even while still above their warning level. A tank at 90% taking a rampage is in more danger than a caster sitting at 45%, and the marker catches that before the health number does. By default, "fast" means losing more than 10% of their health per second; change it on the Dropping fast row of **Alert types & sounds…**. The marker stays for a moment after the drop slows, so it doesn't flicker between hits.

Someone dropping fast is sorted by where they will be in a couple of seconds at that rate, so a fast fall ranks above a steady low. Pets don't get the marker.

### Raid focus

In a raid, the **Watch** setting in the Alerts section decides whose alerts show:

- **Whole raid** (default): everyone.
- **My group**: only your own raid group. It follows the character in the active EverQuest window, so it switches with you between boxes.
- **Chosen groups…**: pick any of the 12 raid groups, for example the tank groups you're assigned to heal. The setting then shows the chosen groups, e.g. *Groups 1, 3*. Pick it again to change them.

Pinned players always show, whatever the setting. Outside a raid nothing is filtered, and anyone EQ Triage has no raid group for yet is shown rather than hidden.

### Charm breaks

When a group member's pet health bar disappears while the pet still had more than 10% health, EQ Triage reports `CHARM BREAK name`. A bar that vanishes at low health counts as the pet dying and is ignored. This works for your group only, not the whole raid.

To avoid false alarms, a lost pet only counts as a charm break when:

- the owner is an **Enchanter, Necromancer or Bard**, the classes that charm at high level. A magician dismissing a pet, for example, is ignored.
- the pet isn't a **summoned pet**. Project Quarm names summoned pets either after their owner (*Sebik`s pet*, *familiar* or *warder*) or with a name from a fixed generator pattern (*Gabartik*, *Jobaner*, *Xebekn* and so on). EQ Triage recognizes every name that generator can produce, so a charmed mob is still spotted even when it has a one-word name (*Quillmane*), as well as the usual *a Shissar Defiler* or *Fippy Darkpaw*. This keeps a necromancer's or enchanter's own summoned pet from counting.

If the owner's class or the pet's name isn't known yet, EQ Triage reports the break anyway rather than risk missing one. A charmed pet that is dismissed at high health, or whose charmer dies, still looks like a charm break. When a charmer dies, the pet really does turn on you.

### Charmer hit

For 30 seconds after a charm break, any drop in the charmer's health turns their row into `CHARMER HIT name 80%` at the top of the overlay. Every break turns the pet hostile, so this row is about what matters next: the charmer is actually taking damage. It stays for 6 seconds after the last hit and keeps watching as long as the hits continue. If the charmer gets a pet back (re-charms), the alert clears.

Any health drop counts, including ones the charmer causes, such as a necromancer's Lich spells.

### Deaths

When the game reports a group or raid member slain (or *You have been slain* / *You died* on one of your own characters), a purple `DEAD name` row shows for 10 seconds. It replaces that player's other rows. Deaths only register if one of your EverQuest windows saw the message.

### Distance warnings

Listed players farther from your character than the **Distance warning beyond** setting (70 units by default) show how far away they are, e.g. `Sebik 38% (150 away)`, or `(other zone)`. That tells you before you start a long heal whether it can land, and whether they need to take a step closer or are across the zone. The distance is rounded to the nearest 10 so it doesn't flicker as people move.

Distance is measured from whichever EverQuest window is active, so it follows you when you switch characters. The 70-unit default warns a little before the edge of the main cleric heals:

| Spell | Range |
|---|---|
| Complete Healing, Divine Light, Ethereal Light | 100 |
| Remedy, Ethereal Remedy | 200 |
| Word of Redemption (group) | 70 around you |

Pets, `DEAD` rows and `CHARM BREAK` rows never show a distance. To turn distance warnings off, untick **Distance warning beyond** in the Alerts section.

### Pinning

Pinned players (for example, your main tank) stay at the top of the overlay and are always shown, even at full health. You can pin up to 25 players, and pins are remembered between sessions. If you pin more players than the overlay has rows, only the first ones fit. There are two ways to pin:

- **From the EQ Triage window:** type a name under *Pinned players* (the box suggests everyone in your group and raid) and click **Add**. Select a name and click **Remove** to unpin it. This works for anyone, even at full health.
- **From the overlay:** every player row has a small pin at its right edge. Click it to pin that player, and click the bright pin again to unpin. This only works for players currently on the overlay.

Pet rows can't be pinned.

> [!NOTE]
> Clicking a pin is a real mouse click, and EverQuest may also register it. If a mob is directly behind the pin, EverQuest could target it.

## Controls

The **EQ Triage window** opens on the desktop where you started EQ Triage and has the taskbar button. Its status line shows which characters are connected.

- **Move:** drag the *Triage* header of the overlay.
- **Preview:** under *Overlay*, fills the overlay with one of each row type for 10 seconds, so you can check its size, width and position without waiting for someone to get hurt.
- **Hide / Show:** under *Overlay*, hides the overlay without quitting, for example while trading or AFK.
- **Recenter:** under *Overlay*, moves the overlay back to the top center of the screen if it ever ends up off-screen. It works even when the position is locked.
- **Lock position:** under *Overlay*, stops the header from being dragged. While locked, clicks on the header go straight through to the game like the rest of the overlay; the pins still work. The lock is remembered between sessions.
- **Pin / unpin:** click the pin at the right of a player row, or use *Pinned players* in the EQ Triage window.
- **This page:** click **Read the docs**.
- **Close:** click **Quit**, or just close the EQ Triage window.
- **Virtual desktops:** the overlay floats over EverQuest on every Windows desktop, like NAG's overlays, so you can keep EverQuest fullscreen on one desktop and your other tools on another.

Everything else on the overlay lets your mouse clicks through to the game.

## Settings

The EQ Triage window groups its settings by what they control. Changes apply to the overlay immediately and are remembered between sessions.

**Overlay**: how the overlay looks.

| Setting | Default | What it does |
|---|---|---|
| Text size | 10 pt | Text size of the rows. The overlay resizes to match. |
| Overlay width | 26 characters | How wide the overlay is, counted in characters of text so it grows with the text size. Widen it if long names get shortened with …. |
| Background opacity | 70% | How visible the overlay's frame is, from 0% (fully clear) to 100% (solid): the dark background, the outer border and the lines between rows. The text, alert colors, pins, the *Triage* header and the bottom edge always stay fully visible, so at 0% you see just the rows between the header and a thin bottom line. |
| Number of rows | 10 | How many rows the overlay has, from 3 to 25. The overlay grows or shrinks to match. |

**Alerts**: what gets listed, what makes a sound, and at what health. The Alerts section has two buttons that open their own windows, plus the distance warning.

**Alert types & sounds…** asks two separate questions for each alert type. **Show on overlay** controls whether its rows appear on the overlay. **Play sound** controls whether it makes a sound, and which one. The two are independent: an alert can show silently, or sound without cluttering the overlay (for example, hear deaths without a `DEAD` row). Each alert with a sound also has a **sound picker**: choose from 13 built-in sounds (soft ping, water drop, double chirp, two-note chime, rising chime, bell, marimba rising and falling, horn chord, alarm pulses, siren sweep, klaxon and low gong). Picking a sound plays it, and ▶ plays the current choice again.

To use your own sound, pick **Custom file…** at the bottom of the list and choose a `.wav` file; the picker then shows its name, e.g. *Custom: tell.wav*. Only WAV files are supported, since that's what Windows' built-in sound player plays. If the file is later moved or deleted, that alert plays its default built-in sound instead. Restore defaults clears custom files.

The **Dropping fast (▼)** row also sets how fast is fast: 10% HP per second by default, from 3 to 50.

| Alert | Shown by default | Sound on by default | Default sound |
|---|---|---|---|
| Warning health (yellow) | Yes | No | Soft ping |
| Critical health (red) | Yes | No | Double chirp |
| Charm break | Yes | **Yes** | Rising chime |
| Charmer hit | Yes | **Yes** | Klaxon |
| Death | Yes | No | Low gong |
| Dropping fast (▼) | Yes | No | Alarm pulses |
| Pets in the list | Yes | — | — |

Sounds play when an alert starts, not continuously. When several start at once, only the most urgent is heard (charmer hit, then charm break, death, dropping fast, critical, warning). The same alert for the same player won't sound again within 10 seconds, and being healed from red back into yellow is silent. Starting EQ Triage mid-fight doesn't sound for alerts that were already happening. Volume follows your Windows volume. The sounds are generated by EQ Triage itself, so there are no audio files to install.

**Health thresholds…** sets two levels for every class, plus pets and "Unknown class":

- **Warning below:** players below this health are listed, in yellow.
- **Critical below:** players below this health turn red. It can't be set higher than *Warning below*.

The defaults depend on how much punishment a class can take, so sturdy classes are flagged later and soft ones earlier:

| Category | Classes | Warning below | Critical below |
|---|---|---|---|
| Melee | Bard, Monk, Paladin, Ranger, Rogue, Shadow Knight, Warrior | 40% | 25% |
| Hybrid casters | Beastlord, Cleric, Druid, Shaman | 50% | 30% |
| Pure casters | Enchanter, Magician, Necromancer, Wizard | 75% | 50% |
| Other | Pets, Unknown class | 50% | 30% |

The window lists the classes under these headings. Each heading, and the **All classes** row at the top, sets every class beneath it at once; it shows — while those classes have different levels. **Reset to class defaults** puts the table above back. Pets have their own row because Zeal doesn't report a class for them, and *Unknown class* covers the moment before a player's class arrives.

The list is sorted by how close each person is to their own critical level, so a caster just above 50% comes before a warrior at 30%, who still has a comfortable margin above their 25%. Someone dropping fast is sorted by where they're heading instead.

| Setting | Default | What it does |
|---|---|---|
| Watch | Whole raid | In a raid, whose alerts show: the whole raid, only your group, or chosen raid groups. See [Raid focus](#raid-focus). |
| Distance warning beyond | On, 70 units | Listed players farther away than this show their distance, e.g. `(150 away)`. Untick it to turn distance warnings off. |

Click **Preview** while you adjust the Overlay settings to see the effect. **Restore defaults**, at the bottom of the window, puts every setting back to its default, including the alert types, sounds and class thresholds; it doesn't touch your pinned players, the overlay's position or the lock.

## Files

Everything lives in the `EQTriage` folder:

- `EQTriage.exe`: the program.
- `position.json`: where you last dragged the overlay. Created the first time you move it.
- `pins.json`: your pinned players. Created the first time you pin someone.
- `settings.json`: your settings. Created the first time you change one.

The EQ Triage window shows the version you're running next to its name. Each time it starts, it asks GitHub whether there's a newer release, and if so a line appears under the status: *EQ Triage 1.1.0 is available. Download it*. That request is the only thing EQ Triage sends over the internet, and it sends nothing about you or your characters. Without an internet connection the check is simply skipped.

To update EQ Triage, quit it, download the [latest release](https://github.com/CopperGlade/EQTriage/releases/latest) and extract it over the old folder. Only `EQTriage.exe` is replaced; your `.json` files are kept. To uninstall, delete the folder.

## Troubleshooting

Start with the status line at the top of the EQ Triage window. It checks the connection to Zeal for you:

| Status | What to do |
|---|---|
| ⚪ Waiting for EverQuest to start. | Nothing. EQ Triage connects on its own within a few seconds of EverQuest starting. |
| ⚪ EverQuest is starting. Waiting for Zeal's feed... | Nothing. Zeal takes a moment to start while the game loads. |
| 🟠 EverQuest is running, but Zeal's feed wasn't found. | Zeal isn't loaded. Check that `Zeal.asi` is in your EverQuest folder and restart EverQuest. When Zeal is loaded, its commands (such as `/pipe`) work in game. With several EverQuest windows open, the message says how many are missing it. |
| ⚪ Connected. Waiting for you to enter Norrath. | Nothing. You're at character select; data starts when you log in. |
| 🟠 Health data is off. Type /pipeverbose on in game. | Type `/pipeverbose on` in game (once; Zeal remembers it). The overlay also shows a grey reminder row. |
| 🟢 Receiving data from Sebik. Join a group or raid to see other players. | Working. Only you and your pets can show until you group or raid. |
| 🟢 Receiving data from Sebik. | Everything is working. Every connected character is listed by name; if one of your boxes is missing, its EverQuest window isn't connected yet. |

- **Overlay is empty while the status is green:** that's normal when nobody is hurt. Click **Preview** to check it's on screen, or set **All classes** to warning below 100% under **Health thresholds…** for a moment to see real data flowing.
- **Can't see the overlay at all:** check it isn't hidden (the button under *Overlay* says **Show**), then click **Recenter**.
- **Can't drag the overlay:** untick **Lock position** under *Overlay*.
