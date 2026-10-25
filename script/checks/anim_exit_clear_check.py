# -*- coding: utf-8 -*-
"""动画离场清屏闸（入库表逐条落地 + 位置正确）。

背景（2026-10-25 实机定案）：搬入块的 09/45/47/48/57 动画组在 Steam 引擎上的终点
与原版不一致（`AFT_007_3` 原版行 226 的离场动画把 st02 从 (317,421) 移到屏内
(178,297) 而非退场——存档快照 Save005 vs Save008 实证）⇒ 立绘压在后续 CG 上。
处置＝人工定案入库 `resource/anim_exit_clears.json`（{脚本: {原版行: [通道]}}），
写盘器在产物中该原版行的**第一条 33/34 显示指令之前**发 `37 <通道>`。
本闸断言：入库表的每一条都在产物中落地——该行前缀区内、第一条 33/34 之前存在
对应 `37 <通道>`（位置与通道都必须精确）。
退出码：1 = 有条目未落地或位置/通道不符。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis  # noqa: E402


def main():
    clears = json.load(open(os.path.join(ROOT, 'resource', 'anim_exit_clears.json'), encoding='utf-8'))
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    prod = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(os.path.join(ROOT, 'asset', 'Rio.arc'))}

    bad = []
    n_entries = 0
    for sc, rows in sorted(clears.items()):
        if sc.startswith('_'):
            continue
        p = plan['scripts'].get(sc)
        assert p and p['kind'] == 'host', '%s 不在还原计划或非 host' % sc
        pin, ok = ws2dis.disassemble(ws2.decode(prod[p['steam_file']]))
        assert ok, '%s 产物线性解析不自洽' % sc
        slots = [tuple(x) for x in slots_all[sc]['slots']]
        for row_s, chans in sorted(rows.items(), key=lambda kv: int(kv[0])):
            row = int(row_s)
            n_entries += len(chans)
            # 产物槽号 = 该 orig 行在槽表中的位置
            ki = next((i for i, s in enumerate(slots) if s == ('orig', row)), None)
            assert ki is not None, '%s 原版行 %d 不在产物槽表' % (sc, row)
            # 该槽前缀区（上一条 14 之后 → 本槽 14 之前）：清屏落点在这里
            p14 = [k for k, x in enumerate(pin) if x[1] == 0x14]
            k0 = p14[ki - 1] if ki > 0 else 0
            k1 = p14[ki]
            seq = []
            for k in range(k0, k1):
                op, ops = pin[k][1], pin[k][3]
                t = ops.split(b'\x00')[0].decode('cp932', 'replace')
                seq.append((op, t))
            first_disp = next((i for i, (op, t) in enumerate(seq) if op in (0x33, 0x34)), None)
            assert first_disp is not None, \
                '%s 行 %d 前缀区内无 33/34 显示指令（入库表行号填错？）' % (sc, row)
            for chan in chans:
                before = seq[:first_disp]
                hit = any(op == 0x37 and t == chan for op, t in before)
                if not hit:
                    bad.append('%s 行 %d 通道 %s：第一条显示指令前无清屏' % (sc, row, chan))
    print('动画离场清屏：条目 %d 条，未落地 %d' % (n_entries, len(bad)))
    for b in bad:
        print('  ❌ ' + b)
    if bad:
        sys.exit(1)
    print('全部落地 ✅')


if __name__ == '__main__':
    main()
