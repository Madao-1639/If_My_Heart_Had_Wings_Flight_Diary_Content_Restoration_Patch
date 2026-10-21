# -*- coding: utf-8 -*-
"""回想守卫/出口一致性闸（产物 vs Steam 基线 vs `resource/replay_guards.json`）。

判据（2026-10-21 定案，见 doc/route-mechanics.md「回想：入口/出口必须成对」）
--------------------------------------------------------------------------
原版每个可回想脚本在场景末尾带「回想出口三连」：`01 flag[127]==1` + `01 var[110]==k`
+ `07 NextFile "EVRET"`，并在**脚本头部**配有成对的「回想入口分派」（同两条 `01` +
`06 Jump <场景起点>`）。正常播放时条件不成立 ⇒ 跳过出口；回想重播时才从头部直跳场景、
末尾经 EVRET 回主菜单。

Steam 把头部那一簇删掉了（多数宿主脚本 `01(127)` 为 0 处），因此**只搬出口、不搬入口**时
那三条就是孤儿：只要 `flag[127]=1` 且 `var[110]==k`（上次回想重播的正是一个吃 k 的脚本），
正常播放也会在场景末尾 `NextFile EVRET` → 主菜单，把它后面的场景整段吃掉。

本闸判据：
1. `action=drop` 的脚本：产物里 `07 NextFile EVRET` 处数 = 0，且 `01(127)` 处数 = Steam 基线。
2. `action=keep` 的脚本：产物 `07 EVRET` 处数 == Steam 基线处数（入口/出口成对，不得凭空增减）。
3. 全局：任何宿主脚本都不得比 Steam 基线多出 `07 EVRET`（= 不得出现孤立的回想出口）。

退出码：1 = 存在违规。报告写 `tmp/replay_guard_check.md`。
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis  # noqa: E402

STEAM = os.path.join(ROOT, 'backup', 'Rio.arc')
ASSET = os.path.join(ROOT, 'asset', 'Rio.arc')
TABLE = os.path.join(ROOT, 'resource', 'replay_guards.json')
REPORT = os.path.join(ROOT, 'tmp', 'replay_guard_check.md')


def cond_id(ops):
    return struct.unpack_from('<H', ops, 1)[0] if len(ops) >= 3 else None


def stats(dec):
    """(01(127) 处数, 01(110) 处数, 07 EVRET 处数)。"""
    ins, ok = ws2dis.disassemble(dec)
    g127 = sum(1 for _o, op, _s, ops in ins if op == 0x01 and cond_id(ops) == 127)
    g110 = sum(1 for _o, op, _s, ops in ins if op == 0x01 and cond_id(ops) == 110)
    evr = sum(1 for _o, op, _s, ops in ins if op == 0x07 and ops.split(b'\x00')[0] == b'EVRET')
    return g127, g110, evr, ok


def main():
    spec = json.load(open(TABLE, encoding='utf-8'))
    declared = spec['scripts']
    steam = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(STEAM)}
    asset = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(ASSET)}

    rows, bad = [], []
    for sc, decl in sorted(declared.items()):
        member = sc + '_E.ws2'
        if member not in asset:
            bad.append('%s: 产物里找不到 %s' % (sc, member))
            continue
        s_stat = stats(ws2.decode(steam[member])) if member in steam else (0, 0, 0, True)
        a_stat = stats(ws2.decode(asset[member]))
        if not a_stat[3]:
            bad.append('%s: 产物线性解析不自洽' % sc)
        if decl['action'] == 'drop':
            if a_stat[2] != 0:
                bad.append('%s: action=drop 但产物仍有 %d 处 07 EVRET' % (sc, a_stat[2]))
            if a_stat[0] != s_stat[0]:
                bad.append('%s: action=drop 但 01(127) %d != Steam %d' % (sc, a_stat[0], s_stat[0]))
        elif decl['action'] == 'keep':
            if a_stat[2] != s_stat[2]:
                bad.append('%s: action=keep 但 07 EVRET %d != Steam %d' % (sc, a_stat[2], s_stat[2]))
        else:
            bad.append('%s: 未知 action=%r' % (sc, decl['action']))
        rows.append('| %s | %s | %d/%d/%d | %d/%d/%d | %s |'
                    % (sc, decl['action'], s_stat[0], s_stat[1], s_stat[2],
                       a_stat[0], a_stat[1], a_stat[2],
                       '✅' if not any(x.startswith(sc + ':') for x in bad) else '❌'))

    # 全局：宿主不得凭空多出 EVRET
    for member in sorted(asset):
        if not member.lower().endswith('.ws2') or member not in steam:
            continue
        a_evr = stats(ws2.decode(asset[member]))[2]
        s_evr = stats(ws2.decode(steam[member]))[2]
        if a_evr > s_evr:
            bad.append('%s: 产物多了 %d 处 07 EVRET（孤立回想出口）' % (member, a_evr - s_evr))

    lines = ['# 回想守卫/出口一致性闸（产物 vs Steam 基线 vs resource/replay_guards.json）', '',
             '| 脚本 | action | Steam 01(127)/01(110)/EVRET | 产物 01(127)/01(110)/EVRET | 判定 |',
             '|---|---|---|---|---|'] + rows + ['']
    lines.append('结论：%s' % ('✅ 通过（%d 条声明）' % len(declared) if not bad else '❌ %d 项违规' % len(bad)))
    if bad:
        lines += [''] + ['- ' + x for x in bad]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
