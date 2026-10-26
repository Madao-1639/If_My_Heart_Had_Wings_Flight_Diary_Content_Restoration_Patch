# -*- coding: utf-8 -*-
"""变体共存闸（`resource/variant_routes.json` 驱动的选项/路由拼接产物）。

判据
----
1. **路由变量独占**：`meta.var_id` 在 Steam/原版全库 0 占用；产物里只允许出现在
   变体表脚本内（写 `0b`、条件 `0x01`）。写去别处 = 语义撞车，HARD。
2. **choice 结构**（选项编写规范 A1，`doc/file-formats.md`）：
   - `0e` 头紧邻 `0f` 前、count 一致；条目数 = 表 texts 的选项数；
   - 提示句 `0x14` 尾 `%K`、日文与表一致；条目文本与表一致；
   - 每个条目 `06` 落点 = **指令起点**且正对 `0b var <旗标>` + `14 "%P"`（旗标 0=原版 / 1=Steam）；
   - 非末支以 `06 → 汇合点` 收尾，末支顺流入汇合点；汇合点为指令起点；
   - 选项帧内无 `0x16` / `0x28` / 非空 `0x15`。
3. **route 结构**：
   - 脚本首指令 = `01 mode=2 var == 0 → b`，`b` 落在指令起点（var==0 走原版体，否则跳 Steam 体）；
   - `b` 起的 Steam 体与**基线逐指令等值**（opcode/操作数；`0x14` 只比正文——槽位 id 进
     产物后被 repool 重排属预期；绝对偏移字段按统一 delta 平移）；
   - 体末 `07 NextFile` 目标 == 原版体尾跳目标（两版本汇合到同一下一脚本）；
   - 体引用的 `CSEV_*` 名与 Steam 基线一致（和谐 CG 随变体回到剧情线）。
4. **槽位面**：`slot_sources` 里的 `variant`/`vchoice` 槽在表 texts 中有非空 zh
   （内容面闸：中文必须真实存在，不许占位）。
5. **画廊解锁点（条件可达，非两路径守恒）**：分支是玩家的选择，**解锁点归属各自分支**——
   选原版分支的玩家没看过 Steam 分支的 CG，就不该解锁它（反之亦然）。判据：
   - **不丢**：Steam 基线每个画廊显示站点（CG 名 + 解锁对）在产物同名脚本中仍存在；
   - **同区锚定**：每个站点的解锁对与其显示在**同一区**（shared/A/B）——被接缝切开 = 丢；
   - **不跨分支重放**：某区内某个解锁对的数量多于本区显示锚定数时，若该对的显示出现在
     **另一分支**，即为「把对方分支的解锁组搬到本分支」（会凭空点亮没看过的 CG）= HARD。
   全库成就钩子数由 `cg_unlock_check` 按「Steam 基线 + 搬运体」把守，重放同样会撞在那里。

退出码 1 = 任一判据失败。明细打印到 stdout。
"""
import collections
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, paths, variants, ws2, ws2dis  # noqa: E402


def members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def var_users(dec, formats=None):
    """该脚本内读写指定变量的指令（0b 写 / 01 条件）；线性解析失败的脚本退化为字节扫。"""
    out = []
    try:
        ins = ws2dis.disassemble(dec, formats=formats)[0]
    except Exception:
        pat = b'\x0b' + struct.pack('<H', 0)   # 退化：整流字节扫描由调用方兜底
        return [(m.start(), '0b-raw', struct.unpack_from('<H', dec, m.start() + 1)[0])
                for m in __import__('re').finditer(b'\x0b..', dec)]
    for off, op, _sz, ops in ins:
        if op == 0x0b and len(ops) >= 3:
            out.append((off, '0b', struct.unpack_from('<H', ops, 0)[0]))
        elif op == 0x01 and len(ops) >= 16:
            out.append((off, '01', struct.unpack_from('<H', ops, 1)[0]))
    return out


def text_of_14(ops):
    # 0x14 操作数 = <id:u32>'char\0'<text>\0\0：先跳过 4 字节槽位 id
    parts = [x for x in ops[4:].split(b'\x00') if x]
    for x in parts:
        t = x.decode('cp932', 'replace')
        if t not in ('char',) and not t.upper().endswith('.OGG'):
            return t
    return ''


def check_choice(sc, spec, dec, detail, fails):
    """choice 结构（选项编写规范 A1）——以 `slot_sources[sc]['variant']` 的布局为准。

    布局由 `variants.apply` 产出（brA/brB/conf），闸门只做**回读验证**：
    条目落点、`0b var val`、`14 "%P"` 前奏、`0e` 头、提示句与条目文本、汇合点。
    注意：还原块里可能自带游戏原有的 `0f`（如 `BEF_004` 的 H 场景选项），
    所以「选项表唯一」不能当判据——取 `brA` 之前**最近**的那张 `0f` 才是本变体的帧。
    """
    var_id = spec.get('var_id') or variants.load()['meta']['var_id']
    ins, _ok = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)
    starts = {x[0] for x in ins}
    by_off = {x[0]: x for x in ins}
    t = spec['texts']
    opts = [k for k in t if k.startswith('opt')]
    if not detail or 'targets' not in detail:
        fails.append('%s: slot_sources 缺变体布局（variant.targets），无法定位选项帧' % sc)
        return
    tg = detail['targets']
    # ① 条目落点 = brA / brB，正对 `0b var <val>` + `14 "%P"`
    for k, key in enumerate(opts):
        val = tg['brA'] if k == 0 else tg['brB']
        if val not in starts:
            fails.append('%s: 条目 %s 落点 %#x 不在指令起点' % (sc, key, val))
            continue
        b0 = by_off[val]
        want = variants._flag(t[key]['var_val'])   # 表里 1=原版/2=Steam → 布尔旗标 0/1
        if not (b0[1] == 0x0b and struct.unpack_from('<H', b0[3], 0)[0] == var_id
                and b0[3][2] == want):
            fails.append('%s: 条目 %s 落点不是 0b var%d=%d（实为 op %02x %r）'
                         % (sc, key, var_id, want, b0[1], b0[3][:6]))
        nxt = by_off.get(val + b0[2])
        if not (nxt and nxt[1] == 0x14 and text_of_14(nxt[3]) == '%P'):
            fails.append('%s: 条目 %s 落点后不是 14 "%%P"' % (sc, key))
    # ② 选项帧：brA 之前最近的 0f；条目落点必须等于 [brA, brB]
    frames = [x for x in ins if x[1] == 0x0F and x[0] < tg['brA']]
    if not frames:
        fails.append('%s: brA 之前找不到选项表 0f' % sc)
        return
    fi = frames[-1]
    idx = [i for i, x in enumerate(ins) if x[0] == fi[0]][0]
    if idx == 0 or ins[idx - 1][1] != 0x0E:
        fails.append('%s: 0x0f 前缺 0e 头' % sc)
    else:
        cnt = struct.unpack_from('<H', ins[idx - 1][3], 2)[0]
        if cnt != fi[3][0]:
            fails.append('%s: 0e count %d != 0f count %d' % (sc, cnt, fi[3][0]))
    ents = ws2dis.choice_entries(dec, fi[0])
    if len(ents) != len(opts):
        fails.append('%s: 条目数 %d != 表选项数 %d' % (sc, len(ents), len(opts)))
        return
    if [e[5] for e in ents] != [tg['brA'], tg['brB']]:
        fails.append('%s: 条目落点 %s != 布局 [brA=%#x, brB=%#x]'
                     % (sc, ['%#x' % e[5] for e in ents], tg['brA'], tg['brB']))
    for k, (so, to, lo, jo, kind, val) in enumerate(ents):
        key = 'opt%d' % (k + 1)
        label = dec[to:dec.index(b'\x00', to)].decode('cp932', 'replace')
        if label != t[key]['jp']:
            fails.append('%s: 条目 %s 文本不符 %r' % (sc, key, label))
    # ③ 提示句（帧前最近的 0x14）+ 帧内禁项
    j = idx - 1
    while j >= 0 and ins[j][1] != 0x14:
        j -= 1
    if j < 0:
        fails.append('%s: 0x0f 前找不到提示句 0x14' % sc)
        frame_lo = fi[0]
    else:
        frame_lo = ins[j][0]
        ptxt = text_of_14(ins[j][3])
        if not ptxt.endswith('%K') or ptxt != t['prompt']['jp']:
            fails.append('%s: 提示句不符 %r' % (sc, ptxt))
    for off, op, _sz, ops in ins:
        if frame_lo <= off < fi[0] and op in (0x16, 0x28):
            fails.append('%s: 选项帧内出现 %#x @0x%x' % (sc, op, off))
        if frame_lo <= off < fi[0] and op == 0x15 and ops not in (b'\x00\x00', b'\x00'):
            fails.append('%s: 选项帧内出现非空 0x15 @0x%x' % (sc, off))
    # ④ 汇合：conf 必须是指令起点；分支 A 末尾的 06 正好落到那里；conf 前一条是台词行
    conf = tg['conf']
    if conf not in starts:
        fails.append('%s: 汇合点 %#x 不在指令起点' % (sc, conf))
    jmps = [x for x in ins if x[1] == 0x06 and tg['brA'] < x[0] < tg['brB']]
    if not jmps:
        fails.append('%s: 分支 A 末尾找不到 06 跳转' % sc)
    else:
        tgt = struct.unpack_from('<I', jmps[-1][3], 0)[0]
        if tgt != conf:
            fails.append('%s: 分支 A 的 06 目标 %#x != 汇合点 %#x' % (sc, tgt, conf))
    prev = None
    for x in ins:
        if x[0] < conf:
            prev = x
    if prev is None or prev[1] != 0x14:
        fails.append('%s: 汇合点 %#x 前一条不是 0x14（分支体未以台词收尾）' % (sc, conf))


def check_route(sc, spec, dec_p, dec_s, fails):
    var_id = spec.get('var_id') or variants.load()['meta']['var_id']
    ins_p, ok_p = ws2dis.disassemble(dec_p)
    ins_s, ok_s = ws2dis.disassemble(dec_s)
    assert ok_p and ok_s
    starts = {x[0] for x in ins_p}
    mode, vid = dec_p[1], struct.unpack_from('<H', dec_p, 2)[0]
    val = struct.unpack_from('<f', dec_p, 4)[0]
    a, b = struct.unpack_from('<II', dec_p, 8)
    # 首选判定：01 mode=2（== 0）—— var==0 顺序执行（原版体），否则跳 Steam 体。
    # `0b` 只能存布尔（0/1）：写 2 会被布尔比较当成 true，两条分支会同路（实机教训）。
    if not (ins_p[0][1] == 0x01 and mode == 2 and vid == var_id and val == 0.0 and a == 0):
        fails.append('%s: 首指令不是 01 var%d == 0（mode=%d vid=%d val=%s a=%#x）'
                     % (sc, var_id, mode, vid, val, a))
        return
    if b not in starts:
        fails.append('%s: 条件 b=%#x 不在指令起点' % (sc, b))
        return
    # Steam 体逐指令等值（`0x14` 只比正文；绝对偏移按统一 delta 平移）
    delta = None
    si = 0
    last_off = None
    for off, op, sz, ops in ins_p:
        if off < b:
            continue
        if si >= len(ins_s):
            fails.append('%s: Steam 体比基线长（基线耗尽 @prod %#x）' % (sc, off))
            return
        if ins_s[si][1] == 0xFF:
            break                      # Steam 流收尾符：拼接器重写，字节不可比
        if delta is None:
            delta = off
        soff, sop, ssz, sops = ins_s[si]
        if op != sop or sz != ssz:
            fails.append('%s: Steam 体指令错位 @prod %#x vs steam %#x（%02x/%02x）'
                         % (sc, off, soff, op, sop))
            return
        if op in variants.REBASE_OPS:
            for fld in variants.REBASE_OPS[op]:
                vp = struct.unpack_from('<I', ops, fld)[0]
                vs = struct.unpack_from('<I', sops, fld)[0]
                if vp or vs:
                    if vp != vs + delta:
                        fails.append('%s: 体跳转字段未按 delta 平移 @steam %#x' % (sc, soff))
                        return
        elif op == 0x0F:
            for ep, es in zip(ws2dis.choice_entries(dec_p, off),
                              ws2dis.choice_entries(dec_s, soff)):
                if ep[4] == 'abs' and es[4] == 'abs' and ep[5] != es[5] + delta:
                    fails.append('%s: 体选项跳转未按 delta 平移 @steam %#x' % (sc, soff))
        elif op == 0x14:
            if ops[4:] != sops[4:]:
                fails.append('%s: 体 0x14 正文不一致 @prod %#x vs steam %#x' % (sc, off, soff))
        elif ops != sops:
            fails.append('%s: 体操作数不一致 @prod %#x vs steam %#x op %02x' % (sc, off, soff, op))
        last_off = off
        si += 1
    rest_s = [x for x in ins_s[si:] if x[1] != 0xFF]
    if rest_s:
        fails.append('%s: Steam 体比基线短（产物 %d 条 / 基线 %d 条）'
                     % (sc, si - 1, len(ins_s) - 1))
        return
    # 体后只剩 0xff（Steam 流的 0xff 由拼接器重写为收尾符）
    rest = [x for x in ins_p if x[0] > last_off]
    if not all(x[1] == 0xFF for x in rest):
        fails.append('%s: Steam 体之后仍有指令（%s）'
                     % (sc, [(hex(x[0]), x[1]) for x in rest][:4]))
    # 尾跳：产物原版体的最后一个 07 vs Steam 流的最后一个 07
    #（`KAN_3002_2` 声明分叉：Steam 演绎走它自己的 3002_3_E，见表内 note）
    def _last07(seq, limit=None):
        hit = None
        for x in seq:
            if x[1] == 0x07 and (limit is None or x[0] < limit):
                hit = x[3].split(b'\x00')[0]
        return hit
    p07, s07 = _last07(ins_p, b), _last07(ins_s)
    if p07 and s07 and p07 != s07 and not spec.get('tail_jump_diverges'):
        fails.append('%s: 两版本尾跳不同（%r vs %r）' % (sc, p07, s07))
    # CSEV 覆盖：产物必须引用基线体引用的全部 CSEV 名
    import re as _re
    pat = _re.compile(rb'CSEV_[A-Za-z0-9_]+')
    body_hi = last_off if last_off else len(dec_p)
    prod_csev = set(pat.findall(dec_p[b:body_hi]))
    steam_csev = set(pat.findall(dec_s[:body_hi - b]))
    if prod_csev != steam_csev:
        fails.append('%s: 体 CSEV 引用与基线不一致（缺 %s / 多 %s）'
                     % (sc, sorted(steam_csev - prod_csev), sorted(prod_csev - steam_csev)))


def _op_name(ops):
    return str(ops.split(b'\x00')[0].decode('ascii', 'replace'))


def check_branch_front(sc, sp, dec_p, detail, fails):
    """分支头部不得夹带**解锁组**（`0b` 旗标组 / `04 CG_ACHIEVEMENT`）。

    跨分支重放的特征是「紧贴分支前奏之后塞一串 `0b A 01 0b B 01`」；单个 `0b` 写
    在分支首拍是正常的（场景旗标），所以只判**连续两个 `0b`** 与成就钩子。
    """
    ins = ws2dis.disassemble(dec_p, formats=ws2dis.FORMATS)[0]
    by_off = dict((x[0], i) for i, x in enumerate(ins))
    if sp['kind'] == 'choice':
        if not detail or 'targets' not in detail:
            return
        tg = detail['targets']
        heads = [('分支A', by_off[tg['brA']] + 2), ('分支B', by_off[tg['brB']] + 2)]
    else:
        heads = [('原版体', 1)]                      # `01` 条件之后
    for name, i in heads:
        for j in range(i, len(ins)):
            op, ops = ins[j][1], ins[j][3]
            if op == 0x0B and j + 1 < len(ins) and ins[j + 1][1] == 0x0B:
                fails.append('%s: %s 头部出现解锁旗标组 `0b`(id %d)+`0b`(id %d) @0x%x'
                             '——把对方分支的解锁组搬到了本分支前端'
                             % (sc, name, struct.unpack_from('<H', ops, 0)[0],
                                struct.unpack_from('<H', ins[j + 1][3], 0)[0], ins[j][0]))
                break
            if op == 0x04 and _op_name(ops) == 'CG_ACHIEVEMENT':
                fails.append('%s: %s 头部出现成就钩子 @0x%x（同上）' % (sc, name, ins[j][0]))
                break
            if op in (0x14, 0x0F, 0x06, 0xFF):
                break


def check_choice_body_b(sc, sp, dec_p, dec_s, detail, fails):
    """choice 分支 B 体 == Steam 行区间**逐指令等值**（B 路径的解锁点原样保留）。

    B 体起点由布局给出（brB + `0b var val` + `14 "%P"`），终点 = 汇合点 conf。
    `0x14` 只比正文（槽位 id 进产物后被 repool 重排属预期），绝对偏移按统一 delta 平移。
    """
    if not detail or 'targets' not in detail:
        return
    tg = detail['targets']
    ins_p = ws2dis.disassemble(dec_p, formats=ws2dis.FORMATS)[0]
    ins_s = ws2dis.disassemble(dec_s, formats=ws2dis.FORMATS)[0]
    idx = dict((x[0], i) for i, x in enumerate(ins_p))
    if tg['brB'] not in idx:
        fails.append('%s: 分支 B 落点 %#x 不是指令起点' % (sc, tg['brB']))
        return
    i0 = idx[tg['brB']] + 2                                   # 跳过 `0b` + `14 "%P"`
    lo, hi = sp['branch_b_steam_rows']
    ts_s = [x for x in ins_s if x[1] == 0x14]
    si0 = next(i for i, x in enumerate(ins_s) if x[0] == ts_s[lo - 1][0]) + 1
    si1 = next(i for i, x in enumerate(ins_s) if x[0] == ts_s[hi][0]) + 1
    n_p = sum(1 for x in ins_p[i0:] if x[0] < tg['conf'])
    n_s = si1 - si0
    if n_p != n_s:
        fails.append('%s: 分支 B 指令数 %d != Steam 行 %d..%d 的 %d' % (sc, n_p, lo, hi, n_s))
        return
    delta = ins_p[i0][0] - ins_s[si0][0]
    for k in range(n_s):
        op_p, sz_p, o_p = ins_p[i0 + k][1], ins_p[i0 + k][2], ins_p[i0 + k][3]
        op_s, sz_s, o_s = ins_s[si0 + k][1], ins_s[si0 + k][2], ins_s[si0 + k][3]
        if (op_p, sz_p) != (op_s, sz_s):
            fails.append('%s: 分支 B 第 %d 条与 Steam 行错位（%02x/%02x）'
                         % (sc, k, op_p, op_s))
            return
        if op_p == 0x14:
            if o_p[4:] != o_s[4:]:
                fails.append('%s: 分支 B 第 %d 条 0x14 正文与 Steam 不一致' % (sc, k))
                return
        elif op_p in variants.REBASE_OPS:
            for fld in variants.REBASE_OPS[op_p]:
                vp = struct.unpack_from('<I', o_p, fld)[0]
                vs = struct.unpack_from('<I', o_s, fld)[0]
                if (vp or vs) and vp != vs + delta:
                    fails.append('%s: 分支 B 第 %d 条跳转字段未按 delta 平移' % (sc, k))
                    return
        elif op_p == 0x0F:
            for ep, es in zip(ws2dis.choice_entries(dec_p, ins_p[i0 + k][0]),
                              ws2dis.choice_entries(dec_s, ins_s[si0 + k][0])):
                if ep[4] == 'abs' and es[4] == 'abs' and ep[5] != es[5] + delta:
                    fails.append('%s: 分支 B 第 %d 条选项跳转未按 delta 平移' % (sc, k))
                    return
        elif o_p != o_s:
            fails.append('%s: 分支 B 第 %d 条操作数不一致（op %02x）' % (sc, k, op_p))
            return


CG_RX = re.compile(
    rb'^(?:(?:CSEV|AFT|BEF|HOT|HUS|KAN|NOV|AGS|KOT|AMA|HUT)_\d{2,4}_\d{2,4}[A-Z]?'
    rb'|FDSDEV\d{2,4}_\d{2,4}[A-Z]?)\.PNG$', re.I)


def _layout(dec, spec):
    """→ zone(文件内偏移) ∈ {'shared','A','B'}（与 `variants.apply` 的布局一致）。

    choice：条目落点 = 分支体起点，非末支 `06` 目标 = 汇合点；
    route：`01` 的 `b` = Steam 体起点（其前是原版体）。
    """
    ins = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)[0]
    starts = [x[0] for x in ins]
    if spec['kind'] == 'choice':
        fi = next(x for x in ins if x[1] == 0x0F)
        ents = ws2dis.choice_entries(dec, fi[0])
        lo, hi = ents[0][5], ents[1][5]
        end = next(struct.unpack_from('<I', x[3], 0)[0] for x in ins
                   if x[1] == 0x06 and x[0] > lo)
    else:
        lo, hi = 0, struct.unpack_from('<I', dec, 12)[0]
        end = len(dec)

    def zone(off):
        k = max(x for x in starts if x <= off)
        if lo <= k < hi:
            return 'A'
        return 'B' if hi <= k < end else 'shared'
    return zone


def _sites(ins):
    """画廊显示站点 → [(偏移, CG 名, (A 旗标, B 旗标))]；对 = 显示后窗口内前两条 `0b`。"""
    out = []
    for i, (off, op, _sz, ops) in enumerate(ins):
        if op != 0x33:
            continue
        parts = [x for x in ops.split(b'\x00') if x]
        if len(parts) < 2 or not CG_RX.match(parts[1]):
            continue
        pair = []
        for j in range(i + 1, min(len(ins), i + 120)):
            if ins[j][1] in (0x14, 0x33):
                break
            if ins[j][1] == 0x0b:
                pair.append(struct.unpack('<H', ins[j][3][:2])[0])
                if len(pair) == 2:
                    break
        out.append((off, parts[1].decode('ascii', 'replace').upper(), tuple(pair)))
    return out


def _pair_instances(ins):
    """解锁对实例（`0b A 01` 紧邻 `0b B 01`）→ [(偏移, (A, B))]。"""
    out = []
    for i in range(len(ins) - 1):
        a, b = ins[i], ins[i + 1]
        if (a[1] == 0x0b and b[1] == 0x0b
                and a[3][2:3] == b'\x01' and b[3][2:3] == b'\x01'):
            out.append((a[0], (struct.unpack('<H', a[3][:2])[0],
                               struct.unpack('<H', b[3][:2])[0])))
    return out


def check_gallery(sc, sp, dec_p, dec_s, fails):
    """画廊解锁点：不丢（条件可达）/ 同区锚定 / 不跨分支重放。

    分支是玩家的选择，**解锁点归属各自分支**：选原版分支的玩家没看过 Steam 分支的 CG，
    就不该点亮它（反之亦然）。所以判据不是「两路径都可达」（那是把两条互斥剧情当成同一
    条链），而是「各自路径上都说得通」—— 详见 `doc/restoration-scope.md` §8。
    """
    zone = _layout(dec_p, sp)
    ins = ws2dis.disassemble(dec_p, formats=ws2dis.FORMATS)[0]
    inst = _pair_instances(ins)
    sites = _sites(ins)
    zs = ('shared', 'A', 'B')
    pair_zone = dict((z, collections.Counter()) for z in zs)
    for off, pair in inst:
        pair_zone[zone(off)][pair] += 1
    anchor = dict((z, collections.Counter()) for z in zs)
    for off, _nm, pair in sites:
        if len(pair) == 2:
            anchor[zone(off)][pair] += 1

    # ① 不丢：Steam 基线的每个画廊站点（名 + 对）在产物同名脚本中仍存在
    _scope = json.load(open(os.path.join(ROOT, 'resource', 'restore_scope.json'),
                            encoding='utf-8'))['scripts'].get(sc) or {}
    _restored = set()
    for _r in (_scope.get('regions') or []):
        _lo, _hi = _r['steam_range']
        _restored.update(range(_lo, _hi + 1))
    _ins_s = ws2dis.disassemble(dec_s, formats=ws2dis.FORMATS)[0]
    _r14_s = [x for x in _ins_s if x[1] == 0x14]
    def _row(off, _r14=_r14_s):
        cand = [k for k, x in enumerate(_r14) if x[0] <= off]
        return (cand[-1] + 1) if cand else 0
    need = collections.Counter((nm, p) for o, nm, p in _sites(_ins_s)
                               if len(p) == 2 and _row(o) not in _restored)
    have = collections.Counter((nm, p) for _o, nm, p in sites if len(p) == 2)
    for key, n in sorted(need.items()):
        if have.get(key, 0) < n:
            fails.append('%s: Steam 画廊站点 %s %s 丢失（Steam %d 处 / 产物 %d 处）'
                         % (sc, key[0], key[1], n, have.get(key, 0)))

    # ② 同区锚定：站点的解锁对必须与显示落在同一区（被接缝切走 = 该路径上看不到解锁）
    for off, nm, pair in sites:
        if len(pair) != 2:
            continue
        z = zone(off)
        if not any(zone(o) == z for o, k in inst if k == pair):
            fails.append('%s: 站点 %s @0x%x 的解锁对 %s 不在同一区（%s）'
                         % (sc, nm, off, pair, z))

    # ③ 分支头部洁净（不跨分支重放的可验形态）见 check_branch_front()
    return sites, dict((z, sum(anchor[z].values())) for z in zs)


def main():
    spec = variants.load()
    var_ids = sorted({(s.get('var_id') or spec['meta']['var_id'])
                      for s in (spec.get('scripts') or {}).values()})
    prod = members(os.path.join(ROOT, 'asset', 'Rio.arc'))
    steam = members(os.path.join(ROOT, 'backup', 'Rio.arc'))
    orig = members(os.path.join(paths.orig_dir(), 'Rio.arc'))
    fails = []

    # 1. 变量独占：表内全部变量在两侧基线全库 0 占用；产物里只出现在自己的变体脚本内
    for tag, base in (('steam', steam), ('orig', orig)):
        for name, data in sorted(base.items()):
            if not name.lower().endswith('.ws2'):
                continue
            fmts = ws2dis.FORMATS if tag == 'steam' else ws2dis.FORMATS_ORIG
            hits = [x for x in var_users(ws2.decode(data), fmts) if x[2] in var_ids]
            if hits:
                fails.append('变体变量 %s 在基线 %s/%s 已被占用 @%s'
                             % ([v for v in var_ids if v == hits[0][2]], tag, name,
                                [hex(h[0]) for h in hits[:3]]))
    # 每个变量只允许出现在用它自己的脚本里（choice 写入者 + 同变量的 route 消费者）
    var_owner = {}
    for sc, s in (spec.get('scripts') or {}).items():
        v = s.get('var_id') or spec['meta']['var_id']
        var_owner.setdefault(v, set()).add(s['steam_file'])
    for name, data in sorted(prod.items()):
        if not name.lower().endswith('.ws2'):
            continue
        used = {x[2] for x in var_users(ws2.decode(data)) if x[2] in var_ids}
        for v in used:
            if name not in var_owner[v]:
                fails.append('var%d 出现在未声明它的脚本 %s' % (v, name))

    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'),
                               encoding='utf-8'))
    # 2/3. 逐脚本结构
    for sc, sp in sorted((spec.get('scripts') or {}).items()):
        sf = sp['steam_file']
        if sf not in prod:
            fails.append('%s: 产物缺 %s' % (sc, sf))
            continue
        dec_p = ws2.decode(prod[sf])
        _vf = (slots_all.get(sc) or {}).get('variant') or {}
        if sp['kind'] == 'choice':
            check_choice(sc, sp, dec_p, _vf, fails)
        else:
            check_route(sc, sp, dec_p, ws2.decode(steam[sf]), fails)
        # 4. 槽位内容面
        slots = [tuple(x) for x in (slots_all.get(sc) or {}).get('slots') or []]
        for kind, key in slots:
            if kind in ('variant', 'vchoice'):
                zh = ((sp.get('texts') or {}).get(key) or {}).get('zh') or ''
                if not zh.strip():
                    fails.append('%s: 槽 %s:%s 缺中文' % (sc, kind, key))

    # 5. 画廊解锁点（条件可达口径，见 doc/restoration-scope.md §8）：
    #    分支是玩家的选择——解锁点归属各自分支，不要求「两路径都可达」。
    #    ① Steam 站点不丢 ② 显示与其解锁对同区 ③ 不跨分支重放（凭空点亮没看过的 CG）
    tot = {}
    for sc, sp in sorted((spec.get('scripts') or {}).items()):
        sf = sp['steam_file']
        if sf not in prod:
            continue
        _sites_p, zc = check_gallery(sc, sp, ws2.decode(prod[sf]),
                                     ws2.decode(steam[sf]), fails)
        check_branch_front(sc, sp, ws2.decode(prod[sf]), _vf, fails)
        if sp['kind'] == 'choice':
            check_choice_body_b(sc, sp, ws2.decode(prod[sf]), ws2.decode(steam[sf]), _vf, fails)
        tot[sc] = (len(_sites_p), zc)
    print('画廊解锁点：%s' % '；'.join(
        '%s %d 站点（A %d / B %d / 共享 %d）' % (sc, n, z['A'], z['B'], z['shared'])
        for sc, (n, z) in sorted(tot.items())))

    if fails:
        print('变体共存闸: FAIL %d 项' % len(fails))
        for f in fails[:30]:
            print('  -', f)
        return 1
    n = len(spec.get('scripts') or {})
    print('变体共存闸: PASS（%d 脚本；变量 %s 独占 / 选项帧规范 / Steam 体逐指令等值 / '
          '槽位有中文 / 画廊解锁点条件可达且归属各自分支）' % (n, var_ids))
    return 0


if __name__ == '__main__':
    sys.exit(main())
