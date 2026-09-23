# EQ Triage

A healer's overlay for Project Quarm · v1.0.0 · by Sebik &lt;Europa&gt;

EQ Triage sits on top of EverQuest and lists the people who need attention: players and pets at low health, charm breaks, charmers under attack, deaths, and anyone out of healing range. It only reads game data and draws on screen. It never presses keys or clicks for you.

## Setup

1. **Install Zeal.** EQ Triage gets its data from Zeal's named pipe, so the Project Quarm client must be running with Zeal (`Zeal.asi` in your EverQuest folder). The pipe is on by default.
2. **Turn on detailed data, once.** In game, type `/pipeverbose on`. Without it, Zeal doesn't send player health. Zeal remembers the setting (`PipeVerbose=TRUE` in `zeal.ini`), so you only do this once. If the overlay shows a grey **Type /pipeverbose on** row, this step is missing.
3. **Install EQ Triage.** Copy the `EQTriage` folder into your EverQuest folder, next to `eqgame.exe`, so you end up with, for example, `C:\QUARM\EQTriage\EQTriage.exe`.

   Unlike Zeal, EQ Triage is a separate program rather than a plugin, so it works from any folder. Keeping it in its own folder inside EverQuest just keeps everything together. The folder must be one you can write to, because EQ Triage saves its settings there, so avoid `Program Files`.
4. **Start EQ Triage.** Run `EQTriage.exe`. A desktop shortcut to it is handy. It can start before or after EverQuest, and it connects to every EverQuest window you have open, so multiboxing needs no extra setup.
5. **Place the overlay.** Click **Preview** in the EQ Triage window to fill the overlay with sample rows for 10 seconds, then drag it by the *Triage* header to wherever you want it. The position is remembered. Tick **Lock position** once it's where you want it, so a stray click can't move it.

> [!NOTE]
> Windows may show a SmartScreen warning the first time, because the program isn't signed. Choose **More info → Run anyway**.

## Reading the overlay

The overlay has 10 rows. Rows appear in this order:

1. **Pinned players**, in the order you pinned them.
2. **Charmer alerts** (`!!`, then `PET BREAK`).
3. **Deaths.**
4. **Everyone else below 50% health** (adjustable under Alerts), players and pets together, lowest first.

| Row | Color | Meaning |
|---|---|---|
| `Sebik 45%` | Yellow | A player below 50% health. |
| `Sebik 20%` | Red | A player below 30% health. |
| `Sebik pet 40%` | Yellow | Sebik's pet below 50% (red below 30%). |
| `PET BREAK Sebik` | Red | Sebik's charmed pet just broke free. Shown for 6 seconds. |
| `!! Sebik 80%` | Red | Sebik is taking damage after a charm break, probably from the freed pet. This is the most urgent row. |
| `DEAD Sebik` | Purple | Sebik died. Shown for 10 seconds. |
| `Sebik 38% (OOR)` | Yellow | Out of Complete Heal range: more than 100 units away from you, or in another zone. |
| `Sebik 95%` | White | A pinned player at healthy HP. |
| `Sebik --` | Grey | A pinned player with no data right now (zoned, or not in your group or raid). |

Long names are shortened with … so the health and tags always stay visible.

## Features

### Low health

Group and raid members below 50% show in yellow, and in red below 30%. Both levels can be changed under Alerts. Your own pets and your group members' pets are included, sorted in with the players by health. Raid members' pets aren't, because Zeal doesn't send them.

### Charm breaks

When a group member's pet health bar disappears while the pet still had more than 10% health, EQ Triage reports `PET BREAK name`. A bar that vanishes at low health counts as the pet dying and is ignored. This works for your group only, not the whole raid.

A pet that is dismissed at high health, or whose charmer dies, looks the same as a charm break. When a charmer dies, the pet really does turn on you.

### Charmer under attack

For 30 seconds after a charm break, any drop in the charmer's health turns their row into `!! name 80%` at the top of the overlay. It stays for 6 seconds after the last hit and keeps watching as long as the hits continue. If the charmer gets a pet back (re-charms), the alert clears.

Any health drop counts, including ones the charmer causes, such as a necromancer's Lich spells.

### Deaths

When the game reports a group or raid member slain (or *You have been slain* / *You died* on one of your own characters), a purple `DEAD name` row shows for 10 seconds. It replaces that player's other rows. Deaths only register if one of your EverQuest windows saw the message.

### Out of range

By default, players outside **Complete Heal range** (100 units, adjustable under Alerts) of your character, or in a different zone, get an `(OOR)` tag, so you know before you start a 10-second CH that it won't land. Range is measured from whichever EverQuest window is active, so it follows you when you switch characters. Divine Light and Ethereal Light share the same 100 range; the Remedy line reaches farther:

| Spell | Range |
|---|---|
| Complete Healing, Divine Light, Ethereal Light | 100 |
| Remedy, Ethereal Remedy | 200 |
| Word of Redemption (group) | 70 around you |

Pets, `DEAD` rows and `PET BREAK` rows never get the tag.

### Pinning

Pinned players (for example, your main tank) stay at the top of the overlay and are always shown, even at full health. You can pin up to 10 players, and pins are remembered between sessions. There are two ways to pin:

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
| Overlay width | 19 characters | How wide the overlay is, counted in characters of text so it grows with the text size. Widen it if long names get shortened with …. |
| Background opacity | 70% | How solid the dark background behind the rows is, from 10% (almost clear) to 100% (solid). The text and alert colors always stay fully visible. |

**Alerts**: who gets listed and how.

| Setting | Default | What it does |
|---|---|---|
| List players below | 50% HP | Players and pets below this health are listed. |
| Show in red below | 30% HP | Listed players and pets below this health turn red instead of yellow. It can't be set higher than *List players below*. |
| Out of range beyond | 100 units | Players farther away than this are tagged (OOR). The default is Complete Heal range. |

Click **Preview** while you adjust the Overlay settings to see the effect. **Restore defaults**, at the bottom of the window, puts every setting in both groups back to the values above; it doesn't touch your pinned players, the overlay's position or the lock.

## Files

Everything lives in the `EQTriage` folder:

- `EQTriage.exe`: the program.
- `position.json`: where you last dragged the overlay. Created the first time you move it.
- `pins.json`: your pinned players. Created the first time you pin someone.
- `settings.json`: your settings. Created the first time you change one.

To update EQ Triage, replace `EQTriage.exe` and keep the `.json` files. To uninstall, delete the folder.

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

- **Overlay is empty while the status is green:** that's normal when nobody is hurt. Click **Preview** to check it's on screen, or set *List players below* to 100% for a moment to see real data flowing.
- **Can't see the overlay at all:** check it isn't hidden (the button under *Overlay* says **Show**), then click **Recenter**.
- **Can't drag the overlay:** untick **Lock position** under *Overlay*.
