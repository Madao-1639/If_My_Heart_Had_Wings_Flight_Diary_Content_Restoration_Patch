# -*- coding: utf-8 -*-
"""CG 解锁指令闸（产物 vs Steam 基线 vs 原版）。

口径（用户 2026-10-28 定案：**ASF 解锁指令保存方式**，见 `doc/file-formats.md`
「CG 显示的固有 id 对」与 `tool/cgunlock.py`）：

  1. HARD **禁止原版编号的解锁对**：产物里出现的每个 `0b A 01 0b B 01` 都必须是
     Steam 原生对。原版编号在 `CG_PAGE*` / `CG_ACHIEVEMENT` 里不存在（置位是空操作），
     但原版 B 值与 Steam 画廊条目号（1170..1488）**有重叠** ⇒ 会凭空点亮没看过的缩略图、
     虚增 CG 完成度。
  2. HARD **Steam 原生对守恒**：Steam 基线每个显示点（CG 名 → 解锁对）在产物**同名脚本**
     里仍存在同一对。删格时组会被**提前到该删格之前的存活格入口**（位置变了，对不变）；
     被替换区间里 Steam 专属的组同样前移 —— 所以这里**只比存在性，不比位置**。
  3. HARD **画廊条目可达**：`CG_PAGE01..09` 的每个条目号 B 必须在产物全库被置位
     （否则该缩略图永久锁死）；`CG_ACHIEVEMENT` 的最高阈值必须 ≤ 可置位条目数。
  4. HARD 成就钩子 `04 CG_ACHIEVEMENT 00` 总数与逐脚本数必须等于 Steam 基线（本作 723）
     ＋ 变体共存搬运体自带钩子（`variants.body_hook_counts`）− 原版分支剔除
     （`variants.ach_removed_counts`）。
  5. 信息项：列出 Steam 有、产物无的 B 编号，以及原版显示点在产物中完全消失的 CG 名。

退出码：1 = HARD 项失败；第 5 项只报告。
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

from tool import arcbuild, cgunlock, variants, ws2, ws2dis, paths  # noqa: E402

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


def hooked_pair_counts(src, sigs):
    """→ {脚本: n}：**带同拍点 `04 CG_ACHIEVEMENT` 的解锁对实例**数（指令流口径）。

    为什么按**计数**而不是按「某个对必须带钩子」：同名反查会把**原版还原块**里的解锁对
    换成 Steam 编号（同一张画面两版各一套编号），那块**不得**补钩子
    （`doc/engine-mechanics.md` §成就触发点契约 保留纪律 2「不新增任何成就触发指令」）。
    按「对 → 必须带钩子」判会把这类正确位点误报成丢失；按计数则只看
    「Steam 基线本来带钩子的那 N 个位点是否还在」（对留了钩子丢了 = 画廊亮而成就静默）。
    """
    out = {}
    for n, raw in sorted(src.items()):
        if not n.lower().endswith('.ws2'):
            continue
        ins = ws2dis.disassemble(ws2.decode(raw), formats=ws2dis.FORMATS)[0]
        got = 0
        for i in range(len(ins) - 1):
            a, b = ins[i], ins[i + 1]
            if not (a[1] == 0x0B and b[1] == 0x0B
                    and len(a[3]) >= 3 and len(b[3]) >= 3
                    and a[3][2:3] == bytes((1,)) and b[3][2:3] == bytes((1,))):
                continue
            pair = (struct.unpack('<H', a[3][:2])[0], struct.unpack('<H', b[3][:2])[0])
            if pair not in sigs:
                continue
            for k in range(i + 2, len(ins)):
                if ins[k][1] == 0x14:
                    break
                if ins[k][1] == 0x04 and ins[k][3].startswith(b'CG_ACHIEVEMENT'):
                    got += 1
                    break
        out[n[:-4]] = got
    return out


def gallery_entries(steam):
    """`CG_PAGE01..09` 的画廊条目号（`0x01 mode=2 id=B val=1.0`）→ {B}。"""
    out = set()
    for n, raw in sorted(steam.items()):
        if not n.upper().startswith('CG_PAGE'):
            continue
        ins = ws2dis.disassemble(ws2.decode(raw), formats=ws2dis.FORMATS)[0]
        for _off, op, sz, ops in ins:
            if op != 0x01 or sz < 7 or ops[0] != 2:
                continue
            if struct.unpack('<f', ops[3:7])[0] == 1.0:
                out.add(struct.unpack('<H', ops[1:3])[0])
    return out


def ach_threshold(steam):
    """`CG_ACHIEVEMENT` 对计数旗标（55）的最大阈值；找不到返回 None。"""
    name = next((k for k in steam if k.upper().startswith('CG_ACHIEVEMENT')), None)
    if name is None:
        return None
    ins = ws2dis.disassemble(ws2.decode(steam[name]), formats=ws2dis.FORMATS)[0]
    top = None
    for _off, op, sz, ops in ins:
        if op != 0x01 or sz < 7 or ops[0] != 0x80:
            continue
        if struct.unpack('<H', ops[1:3])[0] != 55:
            continue
        val = struct.unpack('<f', ops[3:7])[0]
        top = val if top is None else max(top, val)
    return top


def _orig_members():
    """原版发行目录的 Rio.arc 成员；目录不可用时返回 `None`（只跳过原版侧信息项）。"""
    try:
        return members(os.path.join(paths.orig_dir(), 'Rio.arc'))
    except RuntimeError:
        return None


def pairs_by_script(src):
    """{脚本: {(A, B)}}：每个脚本写过的**相邻**解锁对（指令流口径）。"""
    out = {}
    for n, raw in sorted(src.items()):
        if not n.lower().endswith('.ws2'):
            continue
        ins = ws2dis.disassemble(ws2.decode(raw), formats=ws2dis.FORMATS)[0]
        got = set()
        for k in range(len(ins) - 1):
            a, b = ins[k], ins[k + 1]
            if (a[1] == 0x0B and b[1] == 0x0B
                    and len(a[3]) >= 3 and len(b[3]) >= 3
                    and a[3][2:3] == bytes((1,)) and b[3][2:3] == bytes((1,))):
                got.add((struct.unpack('<H', a[3][:2])[0],
                         struct.unpack('<H', b[3][:2])[0]))
        out[n[:-4]] = got
    return out


def main():
    prod = members(os.path.join(ROOT, 'asset', 'Rio.arc'))
    steam = members(os.path.join(ROOT, 'backup', 'Rio.arc'))
    orig = _orig_members()

    ps, pn, ph = scan(prod)
    ss, sn, sh = scan(steam)
    os_, on, oh = scan(orig) if orig else ([], [], {})

    fails = []
    idx, native = cgunlock.steam_index(
        {k: v for k, v in steam.items() if k.lower().endswith('.ws2')})
    # 1. 解锁对的内容判据：每处 CG 显示**必须在同一格内**点亮自己的画廊条目——
    #    即本格（前缀区 + 该显示之后到下一个 `0x14`）内出现「显示名 → Steam 解锁对」
    #    里的那个 B。位置不限（ASF 口径允许把组**提前**到删格之前的存活格入口，
    #    也允许原版还原的显示点不带组——那类由「抛弃原版独有 / 同名反查」兜住）。
    #    白名单 = 两侧都没有该对的水印 CG。
    ins_by_script = {}
    for n, raw in sorted(prod.items()):
        if n.lower().endswith('.ws2'):
            ins_by_script[n[:-4]] = ws2dis.disassemble(
                ws2.decode(raw), formats=ws2dis.FORMATS)[0]
    for sc, nm in pn:
        if nm in PAIR_WHITELIST:
            continue
        want = idx.get(nm)
        if want is None:
            continue                     # Steam 自己就没给这张图登记条目
        ins = ins_by_script.get(sc) or []
        ok = False
        for k, (_off, op, _sz, ops) in enumerate(ins):
            if op != 0x33:
                continue
            parts = [x for x in ops.split(bytes((0,))) if x]
            if len(parts) < 2 or parts[1].decode('ascii', 'replace').upper() != nm:
                continue
            beat = []
            for j in range(k + 1, len(ins)):
                if ins[j][1] == 0x14:
                    break
                beat.append(ins[j])
            ids = set()
            for j in range(len(beat) - 1):
                a, b = beat[j], beat[j + 1]
                if (a[1] == 0x0B and b[1] == 0x0B
                        and a[3][2:3] == bytes((1,)) and b[3][2:3] == bytes((1,))):
                    ids.add(struct.unpack('<H', b[3][:2])[0])
            if want[1] in ids:
                ok = True
                break
        if not ok:
            fails.append('缺解锁对（同格未点亮 B=%d）: %s %s' % (want[1], sc, nm))
    # 1b. 禁止**原版编号**的解锁对：Steam 画廊/计数表里没有这些 id，但原版 B 值域
    #     （1180..1922）与 Steam 条目号（1170..1488）重叠 ⇒ 会误点亮没看过的缩略图。
    cg_spec = cgunlock.scan(
        {k: v for k, v in prod.items() if k.lower().endswith('.ws2')}, idx, native)
    for sc, spec in sorted(cg_spec.items()):
        if spec['drop']:
            for off, a, b in spec['drop'][:3]:
                fails.append('%s 仍有原版编号解锁对 (%d, %d) @%s（应抛弃，见 tool/cgunlock.py）'
                             % (sc, a, b, hex(off)))
        if spec['repoint']:
            for off, a, b, a2, b2 in spec['repoint'][:3]:
                fails.append('%s 同名解锁对未反查 (%d,%d) → (%d,%d) @%s'
                             % (sc, a, b, a2, b2, hex(off)))
    # 1c. 保留的 Steam 解锁对必须带 CG 解锁指令（替换时只能「整组留」：对 + `04`）
    vt_steam = {}
    _vtp = os.path.join(ROOT, 'resource', 'variant_routes.json')
    if os.path.exists(_vtp):
        vt_steam = {k: v for k, v in steam.items() if k.endswith('.ws2')}
    body_hooks = variants.body_hook_counts(vt_steam) if vt_steam else {}
    removed = variants.ach_removed_counts()      # 原版分支（A 体）剔除的 Steam 钩子

    _sig = _steam_pair_sigs(steam)
    _w_s = hooked_pair_counts(steam, _sig)
    _w_p = hooked_pair_counts(prod, _sig)
    for _sc, _n in sorted(_w_s.items()):
        _got = _w_p.get(_sc)
        if _got is None:
            continue
        # 期望 = **Steam 基线**带钩子的位点数（不减不增）：
        #   * 搬运体（Steam 体原字节接回）本身就在基线之内 ⇒ 不能加；
        #   * 原版分支剔除的钩子本来就不在基线计数里（剔的是原版块那批）⇒ 不能减。
        _want = _n
        if _got < _want:
            fails.append('%s 带钩子的解锁对实例 %d < 期望 %d（对留了、成就点丢了）'
                         % (_sc, _got, _want))
    # 2. 成就钩子：期望 = Steam 基线；变体共存脚本（resource/variant_routes.json）把
    #    Steam 体**原字节**接回产物 ⇒ 期望 = 基线 + 搬运体自带的钩子数（双版本各带各的，
    #    不丢基线钩子，也不判多余为缺陷）。
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

    # 2b. Steam 原生对守恒（脚本粒度、只比存在性：删格会把组**提前**到存活格入口，
    #     位置变了但组合不变；被替换区间里仍是 Steam 独有的组同样前移）。
    ps_pairs = pairs_by_script(prod)
    for sc, want in sorted(pairs_by_script(steam).items()):
        have = ps_pairs.get(sc)
        if have is None:
            continue
        lost = sorted(p for p in want if p not in have and p in native)
        if lost:
            fails.append('%s 丢 %d 个 Steam 原生解锁对（应前移到存活格入口）: %s'
                         % (sc, len(lost), lost[:6]))
    # 2c. 画廊条目可达 + CG 收集成就阈值可达
    #     置位来源 = 产物 Rio.arc **∪ 未交付归档**（玩家原档）：朱莉线（`Rio1.arc`）
    #     的画廊条目只有它自己会点亮，产物 `Rio.arc` 里本来就不该有（`julie_guard`）。
    entries, top = gallery_entries(steam), ach_threshold(steam)
    writes = set()
    for _src in (prod, {}) + tuple(
            members(os.path.join(ROOT, 'asset', a)) if os.path.exists(
                os.path.join(ROOT, 'asset', a)) else members(os.path.join(ROOT, 'backup', a))
            for a in ('Rio1.arc',)):
        for n, raw in _src.items():
            if not n.lower().endswith('.ws2'):
                continue
            ins = ws2dis.disassemble(ws2.decode(raw), formats=ws2dis.FORMATS)[0]
            for _off, op, _sz, ops in ins:
                if op == 0x0B and len(ops) >= 3 and ops[2] == 0x01:
                    writes.add(struct.unpack('<H', ops[:2])[0])
    locked = sorted(b for b in entries if b not in writes)
    if locked:
        fails.append('画廊条目永不解锁 %d 个: %s' % (len(locked), locked[:8]))
    if top is not None and top > len(entries) - len(locked):
        fails.append('CG 收集成就阈值 %g > 可置位条目 %d（「全 CG」不可达）'
                     % (top, len(entries) - len(locked)))

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
    print('')
    print('✅ 解锁组合规：无原版编号对（同名已反查 / 原版独有已抛弃）、'
          'Steam 原生对守恒、画廊条目全部可达；成就钩子逐脚本与 Steam 一致')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
