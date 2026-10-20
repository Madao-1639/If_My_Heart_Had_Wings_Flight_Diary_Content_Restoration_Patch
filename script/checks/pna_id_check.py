# -*- coding: utf-8 -*-
"""PNA 记录号 / 层内修复 一致性闸（产物 vs 表）。

判据（2026-10-20 全量演出评审定案）
----------------------------------
1. **记录号必须落在产物 PNA 的记录表内**：`asset/Graphic.arc` 里同名 PNA 若仍是
   Steam 字节（`censor_map keep`），`0x39` 的记录号必须 `< layer_count`；
   原版来源块必须按 `resource/pna_id_map.json` 的 `map` 换算过。
2. **层内修复记录 = 原版记录**：`repair` 清单里的 Steam 记录，其子图字节与 box
   必须等于原版记录；非修复记录必须与 Steam 基线逐字节一致。
3. **不得修复被 Steam 新增段/未还原段复用的记录**：表的 `repair` 清单已由生产者
   做过引用核对；本闸复核 `waive` 记录里没有混入 `repair`。

退出码：1 = 存在违规。报告写 `tmp/pna_id_check.md`。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, paths, pna, pnaids, ws2, ws2dis  # noqa: E402

MAP_PATH = os.path.join(ROOT, 'resource', 'pna_id_map.json')
ARCH = 'Graphic.arc'


def arch_members(path):
    return {nb.decode('utf-16le', 'replace').upper(): d for nb, d in arcbuild.read_raw(path)}


def scan_039(raw):
    """脚本 → [(row, chan, ids, member, head3)]（显示态按前缀继承）。"""
    ins = ws2dis.disassemble(ws2.decode(raw), formats=ws2dis.FORMATS)[0]
    disp, row, out = {}, -1, []
    for _off, op, _sz, ops in ins:
        if op == 0x14:
            row += 1
            continue
        if op in (0x33, 0x34):
            parts = [x for x in ops.split(b'\x00') if x]
            if len(parts) >= 2:
                try:
                    disp[parts[0].decode('cp932')] = parts[1].decode('cp932').upper()
                except UnicodeDecodeError:
                    pass
            continue
        if op == 0x37:
            parts = [x for x in ops.split(b'\x00') if x]
            if parts:
                try:
                    c = parts[0].decode('cp932')
                except UnicodeDecodeError:
                    c = ''
                for k in [k for k in disp if k.startswith(c)]:
                    disp.pop(k, None)
            continue
        if op == 0x39:
            p = pnaids.parse_039(ops)
            if not p:
                continue
            chan, head3, ids = p
            out.append((row, chan, ids, disp.get(chan), head3))
    return out


def main():
    mp = json.load(open(MAP_PATH, encoding='utf-8'))
    members = mp.get('members') or {}
    keep = {n.upper() for n, r in members.items()}
    prod = arch_members(os.path.join(ROOT, 'asset', ARCH))
    steam = arch_members(os.path.join(paths.STEAM, ARCH))
    orig = arch_members(os.path.join(paths.orig_dir(), ARCH))
    prod_rio = arch_members(os.path.join(ROOT, 'asset', 'Rio.arc'))
    rr = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    pw_path = os.path.join(ROOT, 'resource', 'perf_waivers.json')
    member_waivers = {}
    if os.path.exists(pw_path):
        for w in json.load(open(pw_path, encoding='utf-8')).get('members') or []:
            member_waivers[w['name'].upper()] = w

    bad, notes = [], []
    # 1) repair 记录 == 原版；非 repair 记录 == backup
    n_rep = 0
    for name, rec in sorted(members.items()):
        key = name.upper()
        if key not in prod or key not in steam or key not in orig:
            bad.append('%s: asset/backup/orig 缺成员' % name)
            continue
        p, s, o = pna.load(prod[key]), pna.load(steam[key]), pna.load(orig[key])
        reps = {int(r['steam']): int(r['orig']) for r in (rec.get('repair') or [])}
        if len(p['entries']) != len(s['entries']):
            bad.append('%s: asset 记录数 %d != backup %d（层内修复不得改记录数）'
                       % (name, len(p['entries']), len(s['entries'])))
            continue
        for i in range(len(p['entries'])):
            if i in reps:
                n_rep += 1
                oi = reps[i]
                if p['images'][i] != o['images'][oi]:
                    bad.append('%s: repair 记录 %d 子图 != 原版记录 %d' % (name, i, oi))
                if p['entries'][i][2:6] != o['entries'][oi][2:6]:
                    bad.append('%s: repair 记录 %d box != 原版记录 %d' % (name, i, oi))
            else:
                if p['images'][i] != s['images'][i]:
                    bad.append('%s: 非 repair 记录 %d 子图被改动' % (name, i))
                if p['entries'][i][2:6] != s['entries'][i][2:6]:
                    bad.append('%s: 非 repair 记录 %d box 被改动' % (name, i))
        # repair 不得与 waive 重叠
        waive_ids = {int(w['steam']) for w in (rec.get('waive') or [])}
        overlap = set(reps) & waive_ids
        if overlap:
            bad.append('%s: repair 与 waive 重叠 %s' % (name, sorted(overlap)))
        if key in member_waivers and reps:
            bad.append('%s: 成员已登记 perf_waivers，不得再层内修复' % name)
        elif key in member_waivers:
            notes.append('%s: 已知版本差异（%s）' % (name, member_waivers[key].get('kind')))

    # 2) 产物脚本的 0x39 号必须在产物 PNA 记录数内（仅判 keep 成员）
    counts = {k: pna.load(prod[k])['layer_count'] for k in keep if k in prod}
    # 记录级内容状态：same / repair / changed / fallback。产物里任何 0x39 引用到
    # changed/fallback 且未 repair 的记录 ⇒ 画面不会等于原版（除非成员已登记豁免）。
    status = {}
    for name, rec in members.items():
        reps = {int(r['steam']) for r in (rec.get('repair') or [])}
        for d in rec.get('detail') or []:
            st = int(d['steam'])
            ok = bool(d.get('same')) and d.get('size_eq', True)
            status[(name.upper(), st)] = 'repair' if st in reps else ('same' if ok else
                                                                     ('fallback' if d.get('fallback') else 'changed'))
    for sc, p in sorted(rr['scripts'].items()):
        sf = p.get('steam_file') or p.get('target_member')
        if not sf or sf not in prod_rio:
            continue
        for row, chan, ids, mem, _h in scan_039(prod_rio[sf]):
            if not mem or mem not in counts:
                continue
            out = [i for i in ids if i >= counts[mem]]
            if out:
                bad.append('%s 槽 %d %s=%s: 记录号越界 %s（层数 %d）'
                           % (sc, row, chan, mem, out, counts[mem]))
            if mem in member_waivers:
                continue
            cold = [i for i in ids
                    if status.get((mem, i)) in ('changed', 'fallback')]
            if cold:
                bad.append('%s 槽 %d %s=%s: 引用未修复的改画记录 %s'
                           % (sc, row, chan, mem, cold))
    # 3) 原版来源槽的号已换算（抽查：映射表里存在原版号被直接使用的数量）
    for sc, info in sorted(slots.items()):
        p = rr['scripts'].get(sc)
        if not p or p.get('kind') != 'host':
            continue
        sf = p.get('steam_file')
        if sf not in prod_rio:
            continue
        maps = {k: v for k, v in members.items() if v.get('map')}
        hit = 0
        for row, chan, ids, mem, _h in scan_039(prod_rio[sf]):
            if not mem or mem not in maps:
                continue
            rev = {int(v) for v in maps[mem]['map'].values()}
            src = info['slots'][row][0] if row < len(info['slots']) else None
            if src == 'orig':
                # 原版来源块：号应已是 Steam 记录号（取值域 ⊆ map.values()）
                if any(i not in rev for i in ids):
                    hit += 1
        notes.append('%s: 原版来源块记录号不在 Steam 映射值域的行 %d' % (sc, hit))

    lines = ['# PNA 记录号 / 层内修复 一致性闸', '',
             '| 项 | 值 |', '|---|---|',
             '| keep 成员 | %d |' % len(members),
             '| repair 记录 | %d |' % n_rep,
             '| 成员豁免 | %d |' % len(member_waivers),
             '| 违规 | %d |' % len(bad), '']
    if bad:
        lines += ['## 违规', ''] + ['- %s' % x for x in bad[:200]]
    if notes:
        lines += ['', '## 说明', ''] + ['- %s' % x for x in notes[:80]]
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with open(os.path.join(ROOT, 'tmp', 'pna_id_check.md'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('PNA 记录号闸：keep %d、repair %d、违规 %d（报告 tmp/pna_id_check.md）'
          % (len(members), n_rep, len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
