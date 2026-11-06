[简体中文](README.md) | English

# If My Heart Had Wings -Flight Diary- Content Restoration Patch

Restores the story content that was removed from the Steam release of
[*If My Heart Had Wings -Flight Diary-*](https://store.steampowered.com/app/923810/), including the
two entirely deleted **Himegimi sister routes** (Ayahane `AGS_*` / Hotaru `HOT_*`), while keeping the
Steam-only **Julie route** and the **achievement system** fully intact.

**This patch does no localization.** Everything it restores carries the **original Japanese** text of
the source scripts; everything else keeps the **official English** text of the Steam release.

For personal use with a legitimately purchased copy. This repository contains no game assets.

> **Current version: v0.0.4** — content restoration, all route entries wired up, both performance
> variants preserved; awaiting full play-through verification.

![Beamer](https://shared.steamstatic.com/store_item_assets/steam/apps/923810/library_hero.jpg?t=1573643900)

---

## Installation

Download `IMHHFD_Content_Restoration_Patch_Installer_vX.X.X.exe` from [Releases](../../releases) and
run it.

The installer goes through these steps:

1. Locate the game folder (auto-detected from the Steam library; you can type the path manually)
2. List the files that will be modified and wait for confirmation
3. Merge the resources and overwrite the scripts in place
4. Hash-verify every written file by reading it back

The game folder is usually
`<Steam library>\steamapps\common\IF MY HEART HAD WINGS FLIGHT DIARY`. You can delete the installer
once it finishes.

On non-Windows systems you can build `payload/` yourself and run `tool/install.py` (it needs
`arcbuild.py`, `payload/` and the script side by side).

## Uninstall & restore

The patch keeps no backups — restoring the original files is Steam's job:

1. Steam library → right-click the game → Properties
2. Installed Files → Verify integrity of game files

Steam detects the modified archives, downloads them again, and the game is back to vanilla.

## Updating

Verify the game files first (see above), then install the new version the same way.

## Files that are modified

| File | Action | Content |
|---|---|---|
| `Rio.arc` | overwrite | 113 → 114 members: 24 host scripts rebuilt in place, new `AGS_001.ws2`, `NameTable.txt` |
| `zh-CN/Rio.arc` | overwrite | 50 → 51 members: 24 host `.lng` files rebuilt + new `AGS_001.lng` (Chinese localization — see the Chinese README) |
| `Script.arc` | overwrite | 14 members: `LegacyGame.lua` button table / slide-in animation / character-highlight branch |
| `Graphic.arc` | merge | 275 → 323: 48 added, 61 same-name members replaced (incl. 3 in-layer PNA repairs) |
| `Chip1.arc` | merge | 258 → 270: 12 added (backgrounds and sprites referenced by the restored blocks) |
| `Chip2.arc` | merge | 61 → 73: 12 added, 2 same-name members replaced |
| `Chip7.arc` | merge | 164 → 344: 180 added, 3 same-name members replaced |
| `Chip8.arc` | merge | 65 → 238: 173 added |
| `Chip9.arc` | merge | 74 → 257: 183 added, 11 same-name members replaced |
| `Se.arc` | merge | 223 → 242: 19 added |
| `Voice.arc` | merge | 10,265 → 12,152: 1,887 original voice clips added |
| `SysGraphic.arc` | merge | 28 members: 1 same-name member replaced (base UI 8th entry + Cast, taken from the original) |
| `zh-CN/SysGraphic.arc` | merge | 21 members: 1 same-name member replaced (Chinese UI 8th entry — see the Chinese README) |

These archives are **left untouched**: `Rio1.arc`, `Chip3/4/5/6.arc`, `Chip10.arc`, `Bgm.arc`,
`zh-CN/Rio1.arc`.

---

## How it works

The game runs on the same engine as *A Sky Full of Stars* (`AdvHD.exe`), but the Steam release did
three things to it: **every story script was renamed and one was deleted outright** (`AGS_001`),
**the all-ages rewrite was implemented with newly added replacement scripts** (e.g. `KAN_3002_2` →
`_E` plus a new `3002_3_E`), and **same-name assets were redrawn or had members deleted**. The
patch's strategy is to **leave Steam's call-chain skeleton alone** and only add at the original
positions:

### 1. Content restoration

- **Whole script put back**: `AGS_001.ws2` is converted across versions (original WS2 → Steam's WS2
  format table) and written into `Rio.arc` as a new member; `mainmenu`'s entry jump stays exactly as
  Steam ships it.
- **In-place insertion**: the 24 host scripts take Steam's `*_E.ws2` as their base, drop the
  censorship-replaced Steam cells and insert the corresponding original cells at the original
  positions; jumps and the `0x01`/`0x02`/`0x06` offsets are re-based uniformly, while exits and
  achievement calls are preserved **byte for byte**.
- **Performance sync**: when a kept slot's own sprite / background / CG / screen-clear does not match
  the original line, the whole block is swapped back to the original line according to the
  `perf_sync` decision table; `0x0b` unlock pairs and `CG_ACHIEVEMENT` calls are neither duplicated
  nor lost.
- **Sprite record table**: where Steam deleted sentinels, added layers or reordered a same-name
  `.pna`, the patch does **not** overwrite the whole name; it goes through
  `resource/pna_id_map.json` — the `0x39` record numbers of the original source blocks are
  re-mapped, and the 3 redrawn sub-images that Steam's added segments do not reuse get an in-layer
  repair (only the sub-image/box is swapped; record count, order and canvas are untouched).

### 2. Achievements

Steam's achievement calls are not modified and no script's exit set is changed: when cells are
deleted, `0xF0`, the `0b` unlock pairs and the `SCENETITLE` / gallery hooks all stay at their
original byte positions. Machine-checked: `CG_ACHIEVEMENT` 723, `0xF0` 33, identical per script to
`backup/`.

### 3. Divergent content kept as optional branches

The Steam release rewrote this game's H scenes into all-ages passages, and recorded new voices and
drew new CGs for them. Those newly written passages and the deleted original scenes are **mutually
exclusive**, so the patch adds **new choices at the branch points** and lets the player decide which
version to watch; **the choice carries over into the scenes that follow**, so the narrative never
ends up contradicting itself.

**Preserved scope**: 13 segments, roughly 1,950 lines, 480 newly recorded voice clips, 30 newly
drawn CGs (the "HD for the story / low-res for the gallery" pair of the same image counts once).

| Route | Scene | Length | New voices | New CGs |
|---|---|---|---|---|
| Kanako | Lap pillow + ear cleaning (first night over) | 223 lines | 73 | 2 |
| Kanako | Waking up on her arm + sleep talk + morning kiss | 164 lines | 55 | 6 |
| Kanako | Morning teasing + a long talk about how things are | 106 lines | 6 | 1 (reuses the previous scene) |
| Kanako | The all-ages night (walk home + the next day) | 361 lines | 147 | 3 |
| Kanako | Love consultation (the kouhai turns the questions around) | 384 lines | 30 | — |
| Kanako | A kiss in the classroom, and holding back | 34 lines | 10 | — |
| Kotori | Nail clipping + a deep kiss after making up | 38 lines | 4 | 2 |
| Kotori | The starry night (before the last flight) | 50 lines | 21 | 3 |
| Amane | A necktie kiss in the classroom | 53 lines | 11 | — |
| Amane | Comfort after a quarrel + yakiniku to close it out | 44 lines | 15 | 2 |
| Hotaru | An embrace after the glide + a confession | 59 lines | 11 | 3 |
| Hotaru | A deep kiss + holding each other | 67 lines | 6 | 5 |
| Asa & Iru | Three-person shower in swimsuits | 366 lines | 94 | 6 |

**What is not preserved**: one remaining class of Steam edits only **softened the dialogue**,
without forming a standalone scene and without new voice or CG work — about 80 lines in total.
Those get no choice and are **always restored to the original**.

**Choices added by the patch**: **8** in total (Kanako 2, Kotori 2, Amane 2, Hotaru 1, Asa & Iru 1),
located at the start of each segment in the table above. The prompt is a short description of the
two versions; like the restored scenes, these prompts and options were written in **Japanese**. For
example:

```
Prompt: さて、この星空の夜をどうする？     ("So how shall we spend this starry night?")

  ▸ 夜空の下で、彼女を求める              → original
     ("Under the night sky, take her")
  ▸ 星空を眺めながら、静かに寄り添う        → Steam version
     ("Watch the stars, stay close in silence")
```

Note: the original CGs do not enter the gallery and do not count toward Steam's all-CG achievement.

---

## Text in this patch & contributing an English localization

**This patch does not localize the game.** It only restores content:

- **Restored scenes** carry their **original Japanese** lines — that is the text of the source
  scripts, and it is what you see for those scenes.
- **The 8 added choices** are **newly written in Japanese** (matching the language of the restored
  scenes).
- **The 8th story-menu entry** (the Himegimi sisters route button) is a **graphic taken directly from
  the original release**, so it reads **Japanese** in the base (English) UI; the Cast highlight image
  shown for that route is original too.
- **Everything else** keeps the **official English** text of the Steam release, untouched.

So if you want an **English** version of the restored content, what you have to translate is the
Japanese of the restored scenes and of the 8 added choices; no existing English text needs to be
touched, and no script or asset work is involved other than **that one button graphic**. The text
layer is data-only: **5,348 rows across 25 script members** (24 rebuilt hosts + `AGS_001`), which is
roughly the volume a pass would cover, plus the speaker-name table. Two constraints apply:

- **Position matching**: `.lng` has no ids. Entry count must equal the script's `0x14` slot count
  (including every `0x0f` choice entry) — adding or dropping a line shifts the whole file.
- **Display names**: names come from `NameTable.txt` (UTF-16LE), keyed by the `%LC<name>` markers
  already present in the scripts.

A **localization PR is very welcome**: see the Chinese README for the exact file layout, or open an
issue and we will point you at the relevant parts.

---

## Known behaviour

### Restoration scope

- The Himegimi sisters routes (Ayahane `AGS_*` / Hotaru `HOT_*`, including the whole-script
  `AGS_001`) are complete; the Julie route (`AKA_*` / `Rio1.arc` / `Chip10.arc`) stays exactly as
  Steam ships it.
- `KAN_3002_2`'s H scene is restored to the original; Steam's all-ages replacement chain
  (`3002_2_E` + `3002_3_E`) is kept as an **optional** performance — picking "ask her for a lap
  pillow" in `KAN_3001_2` makes the whole Kanako route follow the Steam version.
- The Julie route's 2 added sprite layers (`H朱莉_01*`, i.e. the "H-Julie" sprite) are only used
  on that route; original source slots are content-mapped to the original costume records instead of
  replacing the whole PNA.
- The `*_W` series keeps Steam's canvas cropping; after gravity-centre alignment there is no
  visible difference from the original.

### Text layer status

- The `.lng` position equation passes in full: produced entry count == `0x14` slot count (including
  `0x0f` entries).
- All 5,348 rows keep the control markers (`%K%P` / `%P` / `\n` / `\d`) of their Japanese line, with
  no empty rows.

### Visual verification status

- `perf_consistency_check`: 14,001 slots consistent, 0 CG / sprite differences.
- `pna_id_check`: 21 record-table members that are not equivalent, 839 mappings, 3 in-layer repairs,
  0 out-of-range or unrepaired references.
- The Julie route's 72 slots and the `*_W` cropped variants are known version differences, registered
  in `resource/perf_waivers.json`.

---

## Repository layout

```
├── AGENTS.md           project conventions
├── README.md           Chinese README (the main one)
├── VERSION             version number (single source of truth)
├── asset/              full deliverable files used for testing (build output, not in Git)
├── backup/             vanilla Steam baseline (read-only, not in Git)
├── doc/                technical documentation (index in doc/README.md)
├── tool/               shared libraries and the installer
│   ├── install.py      installer logic
│   ├── arcbuild.py     Arc reader/writer
│   ├── ws2.py          WS2 codec
│   ├── ws2dis.py       WS2 disassembler
│   ├── writer.py       host-script writer
│   ├── pna.py          PNA layer container
│   ├── pnaids.py       0x39 record-number mapping
│   ├── lng.py          .lng / NameTable codec
│   ├── pnglite.py      stdlib-only PNG decoder
│   └── ...
├── script/
│   ├── build/          build pipeline (S2 plan → S2b sprite map → S3 write-out → S3b/c/d visuals → S4 text)
│   ├── checks/         acceptance gates (content / performance / CG / PNA / corpus)
│   ├── scan/           survey scripts (development only, not part of the pipeline)
│   ├── scope/          restoration-scope calibration (development only, produces resource/restore_scope.json)
│   ├── corpus/         corpus alignment / one-off text fixes
│   ├── generate_payload.py  builds the incremental patch
│   ├── final_verification.py  full acceptance run
│   └── pack.sh         packages the installer
├── resource/           checked-in input tables (decision tables, plans, corpus, final assets)
├── payload/            incremental patch output (generated, not in Git)
├── releases/           installer output (generated, not in Git)
└── tmp/                scratch area (not in Git)
```

## Building from source

```bash
# Requirements: Python 3.11+; original release folder (IFMH_ORIG_DIR); GalRev library (GALREV_DIR)
python script/build/build_restore_plan.py     # S2 restoration plan
python script/build/build_pna_id_map.py --write  # S2b sprite record map / repair table
python script/build/build_patch.py            # S3 Rio.arc
python script/build/build_l3.py --write-asset # S3b same-name visual overlay
python script/build/build_l4_extra.py         # S3c missing assets added
python script/build/build_pna_repair.py       # S3d in-layer sprite repair
python script/build/build_lng.py              # S4 text layer (.lng)
python script/final_verification.py           # acceptance run
python script/generate_payload.py             # incremental payload
bash script/pack.sh                            # installer exe
```

`backup/` is read-only; `asset/`, `payload/` and `releases/` are rebuilt by the scripts. The build
reads only `backup/` + `resource/`; the original release folder is used solely to rebuild the assets
that were checked into `resource/`.

## Test status

- [x] Route entry: the 8th button is clickable, the slide-in animation works, the character-highlight
      Cast works (both UI languages)
- [ ] Main restored segments sampled in-game: `AFT_003`, `BEF_006`, `HOT_003`, `KAN_1004`,
      `KAN_2001`, `KAN_3002_1`, `KAN_3004_2` and others
- [ ] **B-path adaptive images**: picking the Steam branch in `BEF_003` / `KAN_2001` must show
      Steam's images (original names), the A path the 9XX original images
- [ ] **8 variant coexistence choice points**: the Kanako group (one choice spanning 5 scripts plus
      reviving `3002_3_E`), the Hotaru group (`HOT_004` has no choice frame and can only follow), the
      whole-script performance of `KAN_2001`, the new merge point in `AFT_003` (S#386), the Kotori
      and Amane groups (item by item in `doc/acceptance-criteria.md`)
- [x] Speaker name boxes and dialogue render correctly; UI layers display correctly
- [x] Static integrity of the achievement hooks (723 / 33)
- [ ] Full playthrough
- [ ] Full regression of the Julie route
- [ ] 12 Steam re-recorded voice clips swapped back to the original recordings
- [ ] `BEF_005` O#1116 line insertion

## Feedback

Please use [Issues](../../issues) and include:

- the patch version
- the scene where it happens (route + rough progress; a save file helps)
- any error log the game produced
- what exactly goes wrong

## Credits

- Engine reverse-engineering knowledge, toolchain and engineering experience from
  [GalRev](https://github.com/Madao-1639/GalRev) and the
  [A Sky Full of Stars Content Restoration Patch](https://github.com/Madao-1639/A_Sky_Full_of_Stars_Content_Restoration_Patch)

## To-Do

- [ ] In-game acceptance of the 8 variant coexistence choice points (including gallery/achievement
      regression on the Steam performance paths)
- [ ] Full playthrough and full CG / all-achievement regression
- [ ] Full regression of the Julie route (confirming the added sprites/voices are unaffected)
- [ ] 12 `V*` voice replacements
- [ ] `BEF_005` O#1116 line insertion (needs a new restoration range + translation)
