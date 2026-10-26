# -*- coding: utf-8 -*-
"""CG 解锁指令闸（产物 vs Steam 基线 vs 原版）。

口径（按用户 2026-10-19 指示）：**不处理 CG 鉴赏页**，只保证解锁指令被保留：
  1. 产物每一处 CG 显示都必须紧跟固有解锁对 `0x0b <A> 01 0x0b <B> 01`；
     唯一白名单是 `FDSDEV14_02B/S`（原版与 Steam 两侧都没有该对，属水印 CG）。
  2. 成就钩子 `04 CG_ACHIEVEMENT 00` 总数与逐脚本数必须等于 Steam 基线（本作 723）
     ＋ 变体共存搬运体自带钩子（`variants.body_hook_counts`；分支体各带各的位点，
     **不做跨分支重放** —— 选原版分支的玩家没看过 Steam 分支的 CG，不该解锁它）。
  3. 信息项：列出 Steam 有、产物无的 B 编号（鉴赏页按 Steam 编号索引），
     以及原版显示点在产物中完全消失的 CG 名。

退出码：1 = 第 1/2 项失败；第 3 项只报告。
用法：工程根目录 `python script/checks/cg_unlock_check.py`
"""
import collections
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tool import arcbuild, variants, ws2, ws2dis, paths  # noqa: E402

CG_RX = re.compile(
    rb'^(?:(?:CSEV|AFT|BEF|HOT|HUS|KAN|NOV|AGS|KOT|AMA|HUT)_\d{2,4}_\d{2,4}[A-Z]?'
    rb'|FDSDEV\d{2,4}_\d{2,4}[A-Z]?)\.PNG$', re.I)
DISP = re.compile(rb'\x33([A-Za-z0-9_]{2,12})\x00([A-Za-z0-9_]+\.PNG)\x00\x01\x01', re.I)
PAIR = re.compile(rb'\x0b(..)\x01\x0b(..)\x01', re.S)
HOOK = b'\x04CG_ACHIEVEMENT\x00'
PAIR_WHITELIST = {'FDSDEV14_02B.PNG', 'FDSDEV14_02S.PNG'}
EXPECT_HOOKS = 723


def members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def scan(src):
    """-> sites[(script, name, A, B)], nopair[(script, name)], hooks{script: n}

    用**指令流**判定解锁对：显示之后、下一条 `0x14` 之前出现两条 `0x0b` 即算——
    允许中间夹图层伴生指令（长转场块会把对推到几十条指令之后）。
    """
    sites, nopair, hooks = [], [], {}
    for n, raw in sorted(src.items()):
        if not n.lower().endswith('.ws2'):
            continue
        dec = ws2.decode(raw)
        hooks[n[:-4]] = dec.count(HOOK)
        try:
            ins = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)[0]
        except Exception:
            # 少数脚本（CG_PAGE09 等）线性解析会失步 ⇒ 退回字节扫描（大窗口）
            for m in DISP.finditer(dec):
                name = m.group(2).decode('ascii', 'replace').upper()
                if not CG_RX.match(m.group(2).upper()):
                    continue
                pm = PAIR.search(dec, m.end(), m.end() + 512)
                if pm:
                    sites.append((n[:-4], name,
                                  struct.unpack('<H', pm.group(1)[:2])[0],
                                  struct.unpack('<H', pm.group(2)[:2])[0]))
                else:
                    nopair.append((n[:-4], name))
            continue
        for i, (off, op, sz, ops) in enumerate(ins):
            if op != 0x33:
                continue
            parts = [x for x in ops.split(b'\x00') if x]
            if len(parts) < 2:
                continue
            name = parts[1].decode('ascii', 'replace').upper()
            if not CG_RX.match(name.encode()):
                continue
            pair = []
            for j in range(i + 1, min(len(ins), i + 120)):
                o2, x2 = ins[j][1], ins[j][3]
                if o2 == 0x14 or o2 == 0x33:
                    break
                if o2 == 0x0b:
                    pair.append(struct.unpack('<H', x2[:2])[0])
                    if len(pair) == 2:
                        break
            if len(pair) == 2:
                sites.append((n[:-4], name, pair[0], pair[1]))
            else:
                nopair.append((n[:-4], name))
    return sites, nopair, hooks


def _steam_pair_sigs(steam):
    """Steam 基线显示锚定的画廊解锁对签名集合（与产物同构口径）。"""
    return {(a, b) for _sc, _nm, a, b in scan(steam)[0]}


def triads(src, sigs):
    """**保留的 Steam 解锁对必须带 CG 解锁指令**：每个 Steam 画廊对实例，
    同一拍点（到下一个 `0x14` 之前）内必须有 `04 CG_ACHIEVEMENT 00`。

    → [(脚本, 偏移, 对)]（缺钩子的）。还原替换时 writer 把 Steam 的 `0b` 对原位保留，
    钩子必须跟着留——只留对不留钩子 = 成就点静默丢失（画廊点亮了、成就没弹）。
    """
    bad = []
    for n, raw in sorted(src.items()):
        if not n.lower().endswith('.ws2'):
            continue
        dec = ws2.decode(raw)
        ins = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)[0]
        starts = {x[0]: i for i, x in enumerate(ins)}
        for i in range(len(ins) - 1):
            a, b = ins[i], ins[i + 1]
            if not (a[1] == 0x0b and b[1] == 0x0b
                    and a[3][2:3] == b'\x01' and b[3][2:3] == b'\x01'):
                continue
            pair = (struct.unpack('<H', a[3][:2])[0], struct.unpack('<H', b[3][:2])[0])
            if pair not in sigs:
                continue
            j = starts[a[0]]
            ok = False
            for k in range(j + 2, len(ins)):
                if ins[k][1] == 0x14:
                    break
                if ins[k][1] == 0x04 and ins[k][3].startswith(b'CG_ACHIEVEMENT'):
                    ok = True
                    break
            if not ok:
                bad.append((n[:-4], a[0], pair))
    return bad


def main():
    prod = members(os.path.join(ROOT, 'asset', 'Rio.arc'))
    steam = members(os.path.join(ROOT, 'backup', 'Rio.arc'))
    orig = members(os.path.join(paths.orig_dir(), 'Rio.arc'))

    ps, pn, ph = scan(prod)
    ss, sn, sh = scan(steam)
    os_, on, oh = scan(orig)

    fails = []
    # 1. 解锁对
    bad_pair = [(sc, nm) for sc, nm in pn if nm not in PAIR_WHITELIST]
    for sc, nm in bad_pair:
        fails.append('缺解锁对: %s %s' % (sc, nm))
    # 1b. 保留的 Steam 解锁对必须带 CG 解锁指令（替换时只能「整组留」：对 + `04`）
    bad_triad = triads(prod, _steam_pair_sigs(steam))
    for sc, off, pair in bad_triad:
        fails.append('解锁对 %s @%s 缺 `04 CG_ACHIEVEMENT`（对留了、成就点丢了）' % (pair, hex(off)))
    # 2. 成就钩子：期望 = Steam 基线；变体共存脚本（resource/variant_routes.json）把
    #    Steam 体**原字节**接回产物 ⇒ 期望 = 基线 + 搬运体自带的钩子数（双版本各带各的，
    #    不丢基线钩子，也不判多余为缺陷）。
    vt_steam = {}
    _vtp = os.path.join(ROOT, 'resource', 'variant_routes.json')
    if os.path.exists(_vtp):
        vt_steam = {k: v for k, v in steam.items() if k.endswith('.ws2')}
    body_hooks = variants.body_hook_counts(vt_steam) if vt_steam else {}
    removed = variants.ach_removed_counts()      # 原版分支（A 体）剔除的 Steam 钩子
    expect_total = EXPECT_HOOKS + sum(body_hooks.values()) - sum(removed.values())
    total = sum(ph.values())
    if total != expect_total:
        fails.append('成就钩子总数 %d != 期望 %d（基线 %d + 变体体 %d − 原版分支剔除 %d）'
                     % (total, expect_total, EXPECT_HOOKS, sum(body_hooks.values()),
                        sum(removed.values())))
    for sc, n in sorted(sh.items()):
        want = n + body_hooks.get(sc + '.ws2', 0) - removed.get(sc + '.ws2', 0)
        if sc in ph and ph[sc] != want:
            fails.append('%s 成就钩子 %d != 期望 %d（基线 %d + 变体体 %d − 剔除 %d）'
                         % (sc, ph[sc], want, n, body_hooks.get(sc + '.ws2', 0),
                            removed.get(sc + '.ws2', 0)))

    # 3. 信息项
    pb = {b for _, _, _, b in ps}
    sb = {b for _, _, _, b in ss}
    ob = {b for _, _, _, b in os_}
    sb_missing = sorted(sb - pb)
    steam_names = collections.defaultdict(set)
    for sc, nm, a, b in ss:
        if b in sb_missing:
            steam_names[b].add(nm)
    prod_names = {nm for _, nm, _, _ in ps}
    lost_sites = [s for s in os_ if s[3] not in pb]
    lost_names = sorted({s[1] for s in lost_sites if s[1] not in prod_names})

    print('CG 显示点：产物 %d（有解锁对 %d）｜Steam %d｜原版 %d'
          % (len(ps) + len(pn), len(ps), len(ss) + len(sn), len(os_) + len(on)))
    print('解锁对缺失：%d（白名单 %s）' % (len(pn), sorted(PAIR_WHITELIST)))
    print('成就钩子：产物 %d / Steam %d / 原版 %d（原版本就没有）' % (total, sum(sh.values()), sum(oh.values())))
    print('B 编号：产物 %d｜Steam %d（产物缺 %d）｜原版 %d' % (len(pb), len(sb), len(sb_missing), len(ob)))
    print('原版显示点未进产物：%d 处，其中 CG 名完全消失 %d 个 %s'
          % (len(lost_sites), len(lost_names), lost_names))
    if sb_missing:
        print('\nSteam 有、产物无的 B（鉴赏页按 Steam 编号索引，属鉴赏面）：')
        for b in sb_missing:
            print('  B=%-5d %s' % (b, sorted(steam_names[b])))
    if fails:
        print('\n闸门失败 %d 条:' % len(fails))
        for f in fails[:20]:
            print('  ', f)
        return 1
    print('\n✅ 解锁指令保留：CG 显示点全部带解锁对（白名单除外），成就钩子逐脚本与 Steam 一致')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
