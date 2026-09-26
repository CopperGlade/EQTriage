# EQ Triage

A healer's overlay for Project Quarm · v1.2.0 · by Sebik &lt;Europa&gt;

EQ Triage sits on top of EverQuest and lists the people who need attention: players and pets at low health, charm breaks, charmers being hit, deaths, and anyone too far away to heal. It only reads game data and draws on screen. It never presses keys or clicks for you.

## Setup

1. **Install Zeal 1.4.6 or later.** EQ Triage gets its data from Zeal's named pipe, so the Project Quarm client must be running with Zeal (`Zeal.asi` in your EverQuest folder). The pipe is on by default. Get the [latest Zeal release](https://github.com/CoastalRedwood/Zeal/releases/latest) if yours is older: 1.4.6 added the spawn ids that the Distance overlay and the `/pipeverbose` reminder need. With an older Zeal the Triage overlay still lists health, but the Distance overlay stays empty.
2. **Turn on detailed data, once.** In game, type `/pipeverbose on`. Without it, Zeal doesn't send player health. Zeal remembers the setting (`PipeVerbose=TRUE` in `zeal.ini`), so you only do this once. If the overlay shows a grey **Type /pipeverbose on** row, this step is missing.
3. **Install EQ Triage.** Download `EQTriage-vX.Y.Z.zip` from the [latest release](https://github.com/CopperGlade/EQTriage/releases/latest) and extract it into your EverQuest folder, next to `eqgame.exe`, so you end up with, for example, `C:\QUARM\EQTriage\EQTriage.exe`.

   Unlike Zeal, EQ Triage is a separate program rather than a plugin, so it works from any folder. Keeping it in its own folder inside EverQuest just keeps everything together. The folder must be one you can write to, because EQ Triage saves its settings there, so avoid `Program Files`.
4. **Start EQ Triage.** Run `EQTriage.exe`. A desktop shortcut to it is handy. It can start before or after EverQuest, and it connects to the game on its own.
5. **Place the overlay.** Click **Preview** in the EQ Triage window to fill the overlay with sample rows for 15 seconds, then drag it by the *Triage* header to wherever you want it. The position is remembered. Tick **Lock position** once it's where you want it, so a stray click can't move it.

> [!NOTE]
> Windows may show a SmartScreen warning the first time, because the program isn't signed. Choose **More info → Run anyway**.

## Reading the overlay

The overlay has 8 rows by default (adjustable from 3 to 25 under **Other settings** in the *Triage overlay* section). Rows appear in this order:

1. **Pinned players**, in the order you pinned them.
2. **Charmer alerts** (`CHARMER HIT`, then `CHARM BREAK`), each followed by the name of the pet that broke free on an indented row.
3. **Deaths.**
4. **Everyone else below their warning level** (set per class; 40–75% by default) or **dropping fast**, players and pets together, most urgent first.

| Row | Color | Meaning |
|---|---|---|
| `Sebik 45%` | Yellow | A player below their class's warning level (40% melee, 60% hybrid casters, 75% pure casters by default). |
| `Sebik 20%` | Red | A player below their class's critical level (25% melee, 40% hybrid casters, 50% pure casters by default). |
| `Sebik pet 40%` | Yellow | Sebik's pet below the pets' warning level, 40% by default (red below the 25% critical level). |
| `CHARM BREAK Sebik` | Red | Sebik's charmed pet just broke free. Shown for 6 seconds. |
| `CHARMER HIT Sebik 80%` | Red | Sebik is taking damage after a charm break, probably from the freed pet. This is the most urgent row. |
| `A Soriz Slave`, indented | Red | The pet that broke free, on the row under each `CHARM BREAK` and `CHARMER HIT`: the mob to stun or re-charm. It takes up one of the overlay's rows. |
| `DEAD Sebik` | Purple | Sebik died. Shown for 10 seconds. |
| `Sebik 70% ▼` | Yellow | Sebik is losing health fast (more than 15% per second over at least two hits by default), listed even above their warning level. |
| `Sebik 38% (150 away)` | Yellow | A distance warning: 150 units from you, farther than the distance warning setting (70 units by default). |
| `Sebik 95%` | White | A pinned player at healthy HP. |
| `Sebik --` | Grey | A pinned player with no data right now (zoned, or not in your group or raid). |

Long names are shortened with … so the health and tags always stay visible.

## Features

### Warning and critical health

Group and raid members show in yellow once they drop below their class's warning level and in red below its critical level: 40% / 25% for melee, 60% / 40% for hybrid casters and 75% / 50% for pure casters by default, since they die very fast. Both levels can be changed per class under **Configure health thresholds**. Your own pets and your group members' pets are included, sorted in with the players by health. Raid members' pets aren't, because Zeal doesn't send them.

Your own character is listed like any other player: low and critical health, dropping fast, death and charm alerts, with their sounds. Its health comes from your own HP bar, so it works solo, in a group and in a raid, even without `/pipeverbose`. Your class is read from the game too, so your own character uses its class's levels wherever you are. It never gets a distance tag. Since you can see your own health bar, you can untick **Include your own character** in the Alerts section to leave it off; your pets still show, and you can pin your own character to see its health anyway.

### Dropping fast

A player losing health quickly gets ▼ after their health, e.g. `Sebik 70% ▼`, and is listed even while still above their warning level. A tank at 90% taking a rampage is in more danger than a caster sitting at 45%, and the marker catches that before the health number does. By default, "fast" means losing more than 15% of their health per second; change it on the Dropping fast row of **Configure alert types**. The loss has to come from at least two separate hits within that second: one big hit, or a caster's own mana-conversion spell, is a spike rather than a fall and doesn't count, while a rampage or a pet turning on its charmer does. The marker stays for a moment after the drop slows, so it doesn't flicker between hits. Each time it fires, `triage.log` gets a line with the name and the rate, so you can check afterwards why someone was listed.

Someone dropping fast is sorted by where they will be in a couple of seconds at that rate, so a fast fall ranks above a steady low. Pets don't get the marker.

### Raid focus

In a raid, the **Scope** setting in the Alerts section decides whose alerts show. By default it's **Entire raid**, so everyone shows. Click it to select the groups you want to monitor. All 12 are selected to begin with, so untick any you don't need, for example groups another healer covers. The setting then reads e.g. *All but groups 7, 8*.

Your own raid group always shows, even when its number is unticked, so you keep your group's alerts if the raid leader moves you into a group you hid. Untick every group to monitor only your own (*Your group only*).

Pinned players always show, whatever the setting, and so do ungrouped raid members and anyone EQ Triage has no raid group for yet. Nothing is hidden outside a raid, or until EQ Triage knows your own group.

### Charm breaks

When a group member's pet health bar disappears while the pet still had more than 10% health, EQ Triage reports `CHARM BREAK name`. A bar that vanishes at low health counts as the pet dying and is ignored. This works for your group only, not the entire raid.

The row under it, indented, names the pet that broke free, so an enchanter knows which mob to stun:

```
CHARM BREAK Sebik
  A Soriz Slave
```

The pet's row stays under the charmer's row when it turns into `CHARMER HIT`, since that pet is usually the one doing the hitting.

To avoid false alarms, a lost pet only counts as a charm break when:

- the owner is an **Enchanter, Necromancer or Bard**, the classes that charm at high level. A magician dismissing a pet, for example, is ignored.
- the pet isn't a **summoned pet**. Project Quarm names summoned pets either after their owner (*Sebik`s pet*, *familiar* or *warder*) or with a name from a fixed generator pattern (*Gabartik*, *Jobaner*, *Xebekn* and so on). EQ Triage recognizes every name that generator can produce, so a charmed mob is still spotted even when it has a one-word name (*Quillmane*), as well as the usual *a Shissar Defiler* or *Fippy Darkpaw*. This keeps a necromancer's or enchanter's own summoned pet from counting.

If the owner's class or the pet's name isn't known yet, EQ Triage reports the break anyway rather than risk missing one. A charmed pet that is dismissed at high health, or whose charmer dies, still looks like a charm break. When a charmer dies, the pet really does turn on you.

### Charmer hit

For 30 seconds after a charm break, any drop in the charmer's health turns their row into `CHARMER HIT name 80%` at the top of the overlay. Every break turns the pet hostile, so this row is about what matters next: the charmer is actually taking damage. It stays for 6 seconds after the last hit and keeps watching as long as the hits continue. If the charmer gets a pet back (re-charms), the alert clears.

Any health drop counts, including ones the charmer causes, such as a necromancer's Lich spells.

### Deaths

When the game reports a group or raid member slain (or *You have been slain* / *You died* for your own character), a purple `DEAD name` row shows for 10 seconds. It replaces that player's other rows. Deaths only register if the message shows in your chat.

### Distance warnings

Listed players farther from your character than the **Show distance beyond** setting (70 units by default) show how far away they are, e.g. `Sebik 38% (150 away)`. That tells you before you start a long heal whether it can land, and whether they need to take a step closer or are across the zone. The distance is rounded to the nearest 10 so it doesn't flicker as people move.

Distance is measured from your character. The 70-unit default warns a little before the edge of the main cleric heals:

| Spell | Range |
|---|---|
| Complete Healing, Divine Light, Ethereal Light | 100 |
| Remedy, Ethereal Remedy | 200 |
| Word of Redemption (group) | 70 around you |

Pets, the rows naming a loose pet, `DEAD` rows and `CHARM BREAK` rows never show a distance. To turn distance warnings off, untick **Show distance beyond** in the Alerts section.

### Target distance window

EQ Triage has two overlays: the **Triage overlay**, the list described above, and the **Distance overlay**, a tiny one-row window with the *Distance* header. It's on by default; **Show window** under *Distance overlay* turns it off and on. It shows one thing: the exact distance to your target, just the number (e.g. `45`), whenever the target is a member of your group or raid. It's small on purpose, meant to sit right beside EverQuest's own target window, which already shows the name. The color tells you which heals can reach them:

| Distance | Color | By default |
|---|---|---|
| up to *Display yellow farther than* | White | 100 units, the range of Complete Healing, Divine Light and the other main heals |
| up to *Display red farther than* | Yellow | 200 units, where only Remedy still reaches |
| beyond that | Red | nothing reaches; one of you has to move |

Both cutoffs are set in the *Distance overlay* section, so other classes can match their own spells.

> [!IMPORTANT]
> The Distance overlay needs **Zeal 1.4.6 or later**, the first version that says what you're targeting. With an older Zeal it stays empty.
>
> The distance is only known for **player characters in your group or raid**. Zeal sends positions for nobody else, so a mob, any pet (including your own) or a player outside your group and raid shows `--` instead of a distance, and no target leaves the row empty. The section in the EQ Triage window says the same. The Distance overlay is dragged by its own header, with its own **Re-center**, **Lock position**, **Show header bar**, text size, background opacity and **Preview**, so it can be tuned for its spot beside the target window without touching the list. Nothing is shared between the two overlays.

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
- **Preview:** the last button in each overlay section. It fills that overlay with sample rows for 15 seconds, even while it is switched off, so you can check its size, width and position without waiting for someone to get hurt.
- **Show window:** under *Triage overlay*, turns the list itself on or off. Untick it to run only the Distance overlay. It's remembered between sessions, and sounds still play while the list is off.
- **Show window:** under *Distance overlay*, shows or hides the second overlay described in [Target distance window](#target-distance-window). It's remembered between sessions, has its own position and its own **Re-center**.
- **Other settings:** under each overlay section, opens a small window with that overlay's look settings (text size, background opacity and so on, listed under [Settings](#settings)). Changes apply as you make them; there is nothing to save.
- **Re-center:** under *Triage overlay*, moves the overlay back to the top center of the screen if it ever ends up off-screen. It works even when the position is locked. EQ Triage also re-centers on its own at startup when the saved position is on no screen, for example after unplugging a monitor.
- **Lock position:** under *Triage overlay*, stops the header from being dragged. While locked, clicks on the header go straight through to the game like the rest of the overlay; the pins still work. The lock is remembered between sessions.
- **Show header bar:** under *Triage overlay*, on by default. Untick it to hide the *Triage* header and the bottom edge, so nothing but the rows sits over the game. The rows stay exactly where they were. With no header there is nothing to drag, so **Preview** brings the header back for its 15 seconds whenever you need to move the overlay. *Background opacity* still applies to what's left (the rows' background, border and dividers); set it to 0% for text alone.
- **Pin / unpin:** click the pin at the right of a player row, or use *Pinned players* in the EQ Triage window.
- **This page:** click **Read the docs**.
- **Close:** click **Quit**, or just close the EQ Triage window.
- **Virtual desktops:** the overlay floats over EverQuest on every Windows desktop, like NAG's overlays, so you can keep EverQuest fullscreen on one desktop and your other tools on another.

Everything else on the overlay lets your mouse clicks through to the game.

## Settings

The EQ Triage window groups its settings by what they control. Changes apply to the overlay immediately and are remembered between sessions.

The sections run top to bottom: *Triage overlay*, *Alerts* and *Pinned players*, which all concern the list, then *Distance overlay*.

**Triage overlay**: how the list overlay looks. Show window, Re-center, Lock position, Show header bar and Preview sit in the section itself (see [Controls](#controls)); the settings below are behind **Other settings**.

| Setting | Default | What it does |
|---|---|---|
| Text size | 10 pt | Text size of the rows. The overlay resizes to match. |
| Overlay width | 28 characters | How wide the overlay is, counted in characters of text so it grows with the text size. Widen it if long names get shortened with …. |
| Background opacity | 70% | How visible the overlay's frame is, from 0% (fully clear) to 100% (solid): the dark background, the outer border and the lines between rows. The text, alert colors, pins, the *Triage* header and the bottom edge always stay fully visible, so at 0% you see just the rows between the header and a thin bottom line. Untick **Show header bar** to drop the header and bottom edge too. |
| Number of rows | 8 | How many rows the overlay has, from 3 to 25. The overlay grows or shrinks to match. |

**Distance overlay**: the second overlay, see [Target distance window](#target-distance-window). Show window, Re-center, Lock position, Show header bar and its own Preview sit in the section itself; the last four settings are behind **Other settings**.

| Setting | Default | What it does |
|---|---|---|
| Show window | On | Shows the Distance overlay. The same checkbox under *Triage overlay* (also on by default) does the same for the list, so either overlay can run alone. |
| Lock position | Off | Stops the Distance overlay's header from being dragged, independently of the Triage overlay's lock. |
| Show header bar | On | Untick it to show just the distance, without the *Distance* header or the bottom edge. The overlay keeps its size, just the width of the word *Distance*. As with the Triage overlay, Preview brings the header back for a moment so you can drag it. |
| Text size | 10 pt | Text size of the number, independent of the Triage overlay's. |
| Background opacity | 70% | How visible its frame is, independent of the Triage overlay's. |
| Display yellow farther than | 100 units | The distance shows in white up to here and in yellow beyond. |
| Display red farther than | 200 units | The distance shows in red beyond here. It can't be set below *Display yellow farther than*. |

**Alerts**: what gets listed, what makes a sound, and at what health. The Alerts section has two buttons that open their own windows, plus the distance warning.

**Configure alert types** asks two separate questions for each alert type. **Show on overlay** controls whether its rows appear on the overlay. **Play sound** controls whether it makes a sound, and which one. The two are independent: an alert can show silently, or sound without cluttering the overlay (for example, hear deaths without a `DEAD` row). Each alert with a sound also has a **sound picker**: choose from 13 built-in sounds (soft ping, water drop, double chirp, two-note chime, rising chime, bell, marimba rising and falling, horn chord, alarm pulses, siren sweep, klaxon and low gong). Picking a sound plays it, and ▶ plays the current choice again.

To use your own sound, pick **Custom file…** at the bottom of the list and choose a `.wav` file; the picker then shows its name, e.g. *Custom: tell.wav*. Only WAV files are supported, since that's what Windows' built-in sound player plays. If the file is later moved or deleted, that alert plays its default built-in sound instead. Restore defaults clears custom files.

The **Dropping fast (▼)** row also sets how fast is fast: 15% HP per second by default, from 3 to 50, always over at least two hits. If you set up EQ Triage before this default changed, your saved 10% stays until you press **Restore defaults** or change it here.

| Alert | Shown by default | Sound on by default | Default sound |
|---|---|---|---|
| Warning health (yellow) | Yes | No | Soft ping |
| Critical health (red) | Yes | **Yes** | Double chirp |
| Charm break | Yes | **Yes** | Rising chime |
| Charmer hit | Yes | **Yes** | Klaxon |
| Death | Yes | No | Low gong |
| Dropping fast (▼) | Yes | **Yes** | Alarm pulses |
| Pets | Yes | — | — |

If you set up EQ Triage before version 1.3.0, your saved sound switches stay as they were, so Critical health and Dropping fast stay silent until you tick them here or press **Restore defaults**.

Pets have no sound of their own: a pet at low health sounds through the Warning or Critical health sound when that one is on, like a player would.

Sounds play when an alert starts, not continuously. When several start at once, only the most urgent is heard (charmer hit, then charm break, death, dropping fast, critical, warning). The same alert for the same player won't sound again within 10 seconds, and being healed from red back into yellow is silent. Starting EQ Triage mid-fight doesn't sound for alerts that were already happening. Volume follows your Windows volume. The sounds are generated by EQ Triage itself, so there are no audio files to install.

**Configure health thresholds** sets two levels for every class, plus pets and "Unknown class":

- **Warning below:** players below this health are listed, in yellow.
- **Critical below:** players below this health turn red. It can't be set higher than *Warning below*.

The defaults depend on how much punishment a class can take, so sturdy classes are flagged later and soft ones earlier:

| Category | Classes | Warning below | Critical below |
|---|---|---|---|
| Melee | Bard, Beastlord, Monk, Paladin, Ranger, Rogue, Shadow Knight, Warrior | 40% | 25% |
| Hybrid casters | Cleric, Druid, Shaman | 60% | 40% |
| Pure casters | Enchanter, Magician, Necromancer, Wizard | 75% | 50% |
| Other | Pets | 40% | 25% |
| Other | Unknown class | 50% | 30% |

The window lists the classes under these headings. Each heading, and the **All classes** row at the top, sets every class beneath it at once; it shows — while those classes have different levels. **Reset to class defaults** puts the table above back. Pets have their own row because Zeal doesn't report a class for them, and *Unknown class* covers the moment before a player's class arrives.

The list is sorted by how close each person is to their own critical level, so a caster just above 50% comes before a warrior at 30%, who still has a comfortable margin above their 25%. Someone dropping fast is sorted by where they're heading instead.

| Setting | Default | What it does |
|---|---|---|
| Scope | Entire raid | In a raid, which raid groups' alerts show. Untick groups to hide them; your own group always shows. See [Raid focus](#raid-focus). |
| Include your own character | On | Lists your own character like any other player, with its alerts and sounds. Untick it to leave your own character off. See [Warning and critical health](#warning-and-critical-health). |
| Show distance beyond | On, 70 units | Listed players farther away than this show their distance, e.g. `(150 away)`. Untick it to turn distance warnings off. |

Click an overlay's **Preview** while you adjust its **Other settings** to see the effect. **Restore defaults**, at the bottom of the window, asks you to confirm and then resets everything: every setting, including the alert types, sounds, class thresholds and both overlays' looks, plus both overlays' positions and locks, and it removes all pinned players.

## Files

Everything lives in the `EQTriage` folder:

- `EQTriage.exe`: the program.
- `position.json`: where you last dragged the Triage overlay and the Distance overlay. Created the first time you move one.
- `pins.json`: your pinned players. Created the first time you pin someone.
- `settings.json`: your settings. Created the first time you change one.
- `triage.log`: a short log of connections, charm breaks, charmer hits, deaths, dropping-fast triggers and any errors, for troubleshooting. It's kept small (one older copy, `triage.log.1`, is retained) and contains only what EQ Triage saw: character names, alerts and technical messages.

Only one EQ Triage runs at a time. Starting it again while it's running just shows a note and leaves the first one alone.

The EQ Triage window shows the version you're running next to its name. Each time it starts, it asks GitHub whether there's a newer release, and if so a line appears under the status: *EQ Triage 1.3.0 is available. Download it*. That request is the only thing EQ Triage sends over the internet, and it sends nothing about you or your characters. Without an internet connection the check is simply skipped.

To update EQ Triage, quit it, download the [latest release](https://github.com/CopperGlade/EQTriage/releases/latest) and extract it over the old folder. Only `EQTriage.exe` is replaced; your `.json` files are kept. To uninstall, delete the folder.

## Troubleshooting

Start with the status line at the top of the EQ Triage window. It checks the connection to Zeal for you:

| Status | What to do |
|---|---|
| ⚪ Waiting for EverQuest to start. | Nothing. EQ Triage connects on its own within a few seconds of EverQuest starting. |
| ⚪ EverQuest is starting. Waiting for Zeal's feed... | Nothing. Zeal takes a moment to start while the game loads. |
| 🟠 EverQuest is running, but Zeal's feed wasn't found. | Zeal isn't loaded. Check that `Zeal.asi` is in your EverQuest folder and restart EverQuest. When Zeal is loaded, its commands (such as `/pipe`) work in game. |
| ⚪ Connected. Waiting for you to enter Norrath. | Nothing. You're at character select; data starts when you log in. |
| 🟠 Health data is off. Type /pipeverbose on in game. | Type `/pipeverbose on` in game (once; Zeal remembers it). The overlay also shows a grey reminder row. |
| 🟢 Receiving data from Sebik. Join a group or raid to see other players. | Working. Only you and your pets can show until you group or raid. |
| 🟢 Receiving data from Sebik. | Everything is working. |

- **Overlay is empty while the status is green:** that's normal when nobody is hurt. Click **Preview** to check it's on screen, or set **All classes** to warning below 100% under **Configure health thresholds** for a moment to see real data flowing.
- **Can't see the overlay at all:** check **Show window** is ticked under *Triage overlay*, then click **Re-center**.
- **Can't drag an overlay:** untick its **Lock position** (each overlay has its own). With **Show header bar** unticked there is no header to grab: click **Preview** and drag while the header shows.
- **Distance overlay stays empty with a group member targeted:** your Zeal is older than 1.4.6. Install the [latest Zeal release](https://github.com/CoastalRedwood/Zeal/releases/latest) and restart EverQuest. A mob, a pet or a player outside your group and raid shows `--`, which is expected.
- **Hurt group members never show up:** type `/pipeverbose on` in game. EQ Triage normally reminds you with a grey row and in the status line, but it can only tell that health is missing with Zeal 1.4.6 or later.
- **Rows blink on and off:** EQ Triage treats data older than 2 seconds as gone. If you raised Zeal's `/pipedelay` above about 1500 ms, set it back down (the default is 100).
- **Something else is wrong:** look at `triage.log` in the EQ Triage folder; the last lines usually say what happened.
