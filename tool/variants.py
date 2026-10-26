# -*- coding: utf-8 -*-
"""变体路由拼接器：把 Steam 差分情节（还原后被顶替的新写段落）以『新增选项 / 变量路由』
接回产物（`resource/variant_routes.json` 驱动）。

两种接法
--------
* `choice`（`KAN_3001_2`）：在共享内容终点插入一张原生形态的选项——
  提示句 `14 %K`（前有 `15 00 00` 清名）→ `0e 0b 00 <count> 00 01` → `0f` 条目
  （内联，`<strid><jp 文本>\\0 80 01 00 06 <u32>`）→ 双分支（`0b var val` + `14 %P`
  + 分支体），非末支以 `06 → 汇合点` 收尾、末支落到汇合点。分支 A = 产物现有原版块
  （原位），分支 B = Steam 基线行区间的**原字节搬运**。
* `route`（`KAN_3001_3/4`）：脚本顶部插 `01 (var != 2 → b=Steam 体起点)`，Steam 整脚
  本体（`0xff` 前全部指令）追加在原版体之后，整体平移重定基；var=2 走 Steam 体，
  var=1 走原版体（不做旧存档兼容）。

共同纪律
--------
* Steam 体是 Steam 引擎原生指令，**原字节搬运**，仅平移绝对偏移（`01.a/b`、`02`、`06`、
  `0f` 条目 `06`）；逐条断言重定基命中（目标必须落在体区间内）。
* **解锁点归属各自分支，不得跨分支重放**：画廊/成就的解锁对（`0b A 01 0b B 01`）与
  成就钩子（`04 CG_ACHIEVEMENT`）随各自分支体原样搬运——分支 A 只带产物（原版）侧的
  位点、分支 B 只带 Steam 行区间/脚本体自带的位点。选 A 的玩家没看过 B 的 CG，就不该
  解锁它；**条件可达是正确语义**（见 `doc/restoration-scope.md` §8）。
* 新增文本槽：`('variant', key)`＝提示句/%P 等 0x14 行、`('vchoice', key)`＝0f 条目（表内 zh）；追加的 Steam 行 → `('steam', 旧槽号)`
  （官方 zh lng 直取）。
* 收尾三件套：`ws2.repool_text_ids()`（0x14 id 与 0f strid 同计数器）→ `tail_counts`
  → `encode + 明文尾表`（见 `tool/ws2.py` 尾表段、`doc/file-formats.md` A1）。
"""
import json
import os
import struct

from . import ws2, ws2dis

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(HERE, 'resource', 'variant_routes.json')

REBASE_OPS = {0x01: (7, 11), 0x02: (0,), 0x06: (0,)}   # 与 tool/ws2conv.REBASE_OPS 同源


def load():
    with open(TABLE, encoding='utf-8') as fh:
        return json.load(fh)


# ── 指令构造（字节形态逐一对齐产物语料模板，见 doc/file-formats.md A1）─────────
def _i14(idx, text):
    return b'\x14' + struct.pack('<I', idx) + b'char\x00' + text.encode('cp932') + b'\x00\x00'


def _i_name_clear():
    return b'\x15\x00\x00'


def _i0e(count):
    return b'\x0e' + struct.pack('<H', 0x0b) + struct.pack('<H', count) + b'\x01'


def _entry(text, target):
    return (struct.pack('<H', 0xFFFF) + text.encode('cp932') + b'\x00'
            + b'\x80\x01\x00' + b'\x06' + struct.pack('<I', target))


def _i0f(entries):
    return b'\x0f' + bytes([len(entries)]) + b''.join(entries)


def _i0b(var, val):
    return b'\x0b' + struct.pack('<H', var) + bytes([val])


def _i06(target):
    return b'\x06' + struct.pack('<I', target)


def _i01_eq0(var, target):
    """`var == 0` 成立则顺序执行，否则跳 `target`（mode 2 = ==，bit7=0 布尔路径）。"""
    return (b'\x01\x02' + struct.pack('<H', var) + struct.pack('<f', 0.0)
            + struct.pack('<I', 0) + struct.pack('<I', target))


FLAG_ORIG, FLAG_STEAM = 0, 1     # `0b` 只能存布尔（0/1），不能用 2（见下）


def _flag(opt_var_val):
    """选项的 `var_val`（表里 1=原版 / 2=Steam）→ **布尔旗标**（0=原版 / 1=Steam）。

    ⚠️ 实机教训（2026-10-27）：`0b` 是**布尔**存储——写 2 与写 1 在布尔比较里都等于 true，
    于是 `01 mode=3 var != 2` 对两个选项都判假 ⇒ 两条分支走同一体（都是 Steam）。
    现在只写 0/1，条件用 `== 0`（未写入亦为 0 ⇒ 缺省走原版，回想场景安全）。
    """
    return FLAG_ORIG if int(opt_var_val) == 1 else FLAG_STEAM


# ── 基础件 ─────────────────────────────────────────────────────────────────────
def _chunks(dec, ins, lo, hi):
    """dec[lo:hi) 内的完整指令字节列表（区间必须指令对齐）。"""
    out = []
    for off, _op, sz, _ops in ins:
        if lo <= off < hi:
            assert off + sz <= hi, '区间 %#x..%#x 未指令对齐' % (lo, hi)
            out.append(dec[off:off + sz])
    assert out, '区间 %#x..%#x 内无指令' % (lo, hi)
    assert out[0] == dec[lo:lo + len(out[0])], '区间首指令错位'
    return out


def _rebase_group(chunks, remap, coord):
    """组内指令的绝对偏移字段按 remap 平移；remap=None（本模块新造）原样返回。"""
    if remap is None:
        return list(chunks)
    out = []
    for cb in chunks:
        buf = bytearray(cb)
        ins = ws2dis.disassemble(bytes(buf), stop_at_end=False)[0]
        for off, op, _sz, _ops in ins:
            if op in REBASE_OPS:
                for k in REBASE_OPS[op]:
                    v = struct.unpack_from('<I', buf, off + 1 + k)[0]
                    if v:
                        struct.pack_into('<I', buf, off + 1 + k, remap(v))
            elif op == 0x0F:
                # `choice_entries` 返回的 jo 已经是**块内绝对偏移**（相对 off），
                # 不能再加 `off+1`（那是普通操作数字段的算法）——多加 1 会越界。
                for _so, _to, _lo, jo, kind, val in ws2dis.choice_entries(bytes(buf), off):
                    if kind == 'abs' and val:
                        struct.pack_into('<I', buf, jo, remap(val))
        out.append(bytes(buf))
    return out


def _finish(groups):
    """groups: [(chunks, remap, coord)] 按序拼接 → repool 槽位 → 明文尾表 → encode。"""
    body = b''.join(b''.join(_rebase_group(c, r, k)) for c, r, k in groups) + b'\xff'
    padded = body + b'\x00' * ws2.TAIL_LEN       # 假尾（0xff 按 9 字节消费，repool 需要）
    repooled = ws2.repool_text_ids(padded)
    tc = ws2.tail_counts(padded[:len(body)])
    raw = ws2.encode(repooled[:len(body)]) + struct.pack('<II', tc[0], tc[1])
    ins, ok = ws2dis.disassemble(ws2.decode(raw))
    assert ok, '变体拼接后线性解析不自洽'
    return raw, tc


def _slots_of(dec):
    ts = ws2.text_slots(dec)
    ins, ok = ws2dis.disassemble(dec)
    assert ok
    return ts, ins


def _instr_end(ins, off):
    for o, _op, sz, _ops in ins:
        if o == off:
            return off + sz
    raise AssertionError('偏移 %#x 不是指令起点' % off)


def _mk_remap(zones, coord):
    """zones = [(lo, hi, delta)] 有序不重叠（源坐标系）→ 目标平移函数（含区间断言）。"""
    def remap(t):
        for lo, hi, delta in zones:
            if lo <= t < hi:
                return t + delta
        raise AssertionError('变体 %s 的跳转目标 %#x 落在已知区外 %s' % (coord, t, zones))
    return remap


def _slot_anchor(slots, ts, anchor):
    """槽锚点 `[kind, value]` → 唯一槽序号（锚点必须存在于产物槽表且是 0x14 行）。"""
    a = tuple(anchor)
    hit = [i for i, s in enumerate(slots) if tuple(s) == a]
    assert len(hit) == 1, '锚点 %r 命中 %d 个槽（须唯一）' % (a, len(hit))
    i = hit[0]
    assert ts[i][0] == '14', '锚点 %r 不是 0x14 槽' % (a,)
    return i


# ── choice 接法 ────────────────────────────────────────────────────────────────
def apply_choice(script, steam_raw, prod_raw, slots, spec, var_id):
    dec_p = ws2.decode(prod_raw)
    dec_s = ws2.decode(steam_raw)
    ts_p, ins_p = _slots_of(dec_p)
    ts_s, ins_s = _slots_of(dec_s)
    assert all(k == '14' for k, _ in ts_s), '%s Steam 侧存在 0f 条目，行区间口径不适用' % script

    assert len(ts_p) == len(slots), '%s 文本槽 %d != 槽表 %d（锚点口径失效）' % (
        script, len(ts_p), len(slots))
    after = _slot_anchor(slots, ts_p, spec['seam']['after'])
    assert 0 <= after < len(ts_p) - 1
    seam_cut = _instr_end(ins_p, ts_p[after][1])
    # 汇合点：给了锚点 → 该槽前一行的 0x14 之后（区间中部汇合）；未给 → 脚本尾部
    conf_anchor = (spec.get('confluence') or {}).get('at')
    conf_idx = _slot_anchor(slots, ts_p, conf_anchor) if conf_anchor else len(slots)
    conf_cut = _instr_end(ins_p, ts_p[conf_idx - 1][1])
    assert seam_cut < conf_cut

    lo, hi = spec['branch_b_steam_rows']
    s_lo = _instr_end(ins_s, ts_s[lo - 1][1])           # Steam 行 lo 块起点
    s_hi = _instr_end(ins_s, ts_s[hi][1])               # Steam 行 hi 块终点（含其 0x14）
    assert 0 < s_lo < s_hi

    t = spec['texts']
    head = _chunks(dec_p, ins_p, 0, seam_cut)
    body_a = _chunks(dec_p, ins_p, seam_cut, conf_cut)
    body_b = _chunks(dec_s, ins_s, s_lo, s_hi)
    tail = _chunks(dec_p, ins_p, conf_cut, _ff_off(ins_p))
    # 选项帧（BEF_004 模板）：清名 → 提示句 → 0e → 0f；条目落点 = 各分支自己的 `0b`
    frame_len = (len(_i_name_clear()) + len(_i14(0, t['prompt']['jp'])) + len(_i0e(2))
                 + len(_i0f([_entry(t['opt1']['jp'], 0), _entry(t['opt2']['jp'], 0)])))
    preA = _i0b(var_id, _flag(t['opt1']['var_val'])) + _i14(0, t['pp1']['jp'])
    preB = _i0b(var_id, _flag(t['opt2']['var_val'])) + _i14(0, t['pp2']['jp'])

    # 解锁/成就点归属各自分支：分支 A 只带产物侧位点、分支 B 只带 Steam 行区间自带位点。
    # 不跨分支重放（选 A 的玩家没看过 B 的 CG，不应解锁它——条件可达是正确语义）。

    # 目标偏移（新流坐标）：纯算术。条目 A 落点 = 帧后第一条（0b），即顺流位置
    brA = sum(map(len, head)) + frame_len
    brB = brA + len(preA) + sum(map(len, body_a)) + len(_i06(0))
    conf = brB + len(preB) + sum(map(len, body_b))

    frame = (_i_name_clear() + _i14(0, t['prompt']['jp']) + _i0e(2)
             + _i0f([_entry(t['opt1']['jp'], brA), _entry(t['opt2']['jp'], brB)]))
    assert len(frame) == frame_len
    jmpA = _i06(conf)

    # 重定基：产物坐标系分段平移；Steam 块坐标系独立平移
    insert_at_seam = (len(frame) + len(preA) + len(jmpA)
                      + len(preB) + sum(map(len, body_b)))
    prod_map = _mk_remap([(0, seam_cut, 0),
                          (seam_cut, conf_cut, len(frame) + len(preA)),
                          (conf_cut, _ff_off(ins_p), insert_at_seam)],
                         'prod')
    steam_map = _mk_remap([(s_lo, s_hi, brB + len(preB) - s_lo)], 'steam-bodyB')
    groups = [
        (head, prod_map, 'head'),
        ([frame], None, 'choice-frame'),
        ([preA], None, 'branchA-prelude'),
        (body_a, prod_map, 'bodyA'),
        ([jmpA], None, 'branchA-jump'),
        ([preB], None, 'branchB-prelude'),
        (body_b, steam_map, 'bodyB'),
        (tail, prod_map, 'tail'),
    ]
    raw, tc = _finish(groups)

    # 槽位表（文件序）：head 槽 + prompt/opt1/opt2/pp1 + 分支 A 槽（区间内）+ pp2
    # + Steam 行槽（分支 B 整段，含与分支 A 重复的共享行——文件里出现两次，各占一槽）
    # + 汇合点之后的尾部槽
    n_head_slots = after + 1
    new_slots = (list(slots[:n_head_slots])
                 + [('variant', 'prompt'), ('vchoice', 'opt1'), ('vchoice', 'opt2'),
                    ('variant', 'pp1')]
                 + list(slots[n_head_slots:conf_idx])
                 + [('variant', 'pp2')]
                 + [('steam', i) for i in range(lo, hi + 1)]
                 + list(slots[conf_idx:]))
    detail = {'kind': 'choice', 'var_id': var_id, 'seam_slot': after, 'conf_idx': conf_idx,
              'branch_b_rows': [lo, hi], 'targets': {'brA': brA, 'brB': brB, 'conf': conf},
              'tail_counts': list(tc), 'slots': len(new_slots),
              'ach_in_body': sum(1 for c in body_b if c[0] == 0x04
                                 and c[1:].startswith(b'CG_ACHIEVEMENT'))}
    return raw, new_slots, detail


def _ff_off(ins):
    for off, op, _sz, _ops in ins:
        if op == 0xFF:
            return off
    raise AssertionError('找不到 0xff 终结符')


# ── route 接法 ─────────────────────────────────────────────────────────────────
def apply_route(script, steam_raw, prod_raw, slots, spec, var_id):
    dec_p = ws2.decode(prod_raw)
    dec_s = ws2.decode(steam_raw)
    ins_p, ok_p = ws2dis.disassemble(dec_p)
    ins_s, ok_s = ws2dis.disassemble(dec_s)
    assert ok_p and ok_s
    ts_s = ws2.text_slots(dec_s)
    assert all(k == '14' for k, _ in ts_s), '%s Steam 体含 0f，需先拆解选项结构' % script

    head = _chunks(dec_p, ins_p, 0, _ff_off(ins_p))
    body = _chunks(dec_s, ins_s, 0, _ff_off(ins_s))
    assert body

    # 解锁/成就点归属各自分支：原版体只带产物侧位点、Steam 体只带脚本体自带位点。
    # 不跨分支重放（条件可达是正确语义）。
    cond_len = 16                                    # 01 <mode:u8><id:u16><f32><u32><u32>
    body_b_start = cond_len + sum(map(len, head))
    cond = _i01_eq0(var_id, body_b_start)

    groups = [
        ([cond], None, 'route-cond'),
        (head, _mk_remap([(0, _ff_off(ins_p), cond_len)], 'orig-body'),
         'orig-body'),
        (body, _mk_remap([(0, _ff_off(ins_s), body_b_start)], 'steam-body'), 'steam-body'),
    ]
    raw, tc = _finish(groups)

    new_slots = list(slots) + [('steam', i) for i in range(len(ts_s))]
    detail = {'kind': 'route', 'var_id': var_id, 'body_b_start': body_b_start,
              'cond_len': cond_len, 'tail_counts': list(tc), 'slots': len(new_slots),
              'steam_body_rows': len(ts_s),
              'ach_in_body': sum(1 for c in body if c[0] == 0x04
                                 and c[1:].startswith(b'CG_ACHIEVEMENT'))}
    return raw, new_slots, detail


def apply(script, steam_raw, prod_raw, slots, spec, var_id=None):
    # 变量优先级：脚本级 `var_id` > `meta.var_id`（互不相干的场景各用各的变量）
    var_id = spec.get('var_id') or var_id or load()['meta']['var_id']
    fn = apply_choice if spec['kind'] == 'choice' else apply_route
    return fn(script, steam_raw, prod_raw, [tuple(s) for s in slots], spec, var_id)


def body_hook_counts(steam_members):
    """{产物成员名: 搬运体自带的成就钩子数}——choice=行区间、route=整脚本。

    消费方：`cg_unlock_check` / `final_verification`（期望 = Steam 基线 + 本值；
    双版本各带各的钩子，基线「一个不丢」的原则不变）。
    """
    out = {}
    for _sc, s in (load().get('scripts') or {}).items():
        sf = s.get('steam_file')
        raw = (steam_members or {}).get(sf)
        if raw is None:
            continue
        dec = ws2.decode(raw)
        if s['kind'] == 'route':
            out[sf] = dec.count(b'\x04CG_ACHIEVEMENT\x00')
            continue
        lo, hi = s['branch_b_steam_rows']
        ins, _ok = ws2dis.disassemble(dec)
        i14 = [x for x in ins if x[1] == 0x14]
        blo = i14[lo - 1][0] + i14[lo - 1][2] if lo > 0 else 0
        bhi = i14[hi][0] + i14[hi][2]
        out[sf] = sum(1 for off, op, _s, ops in ins
                      if op == 0x04 and ops.startswith(b'CG_ACHIEVEMENT')
                      and blo <= off < bhi)
    return out


def ach_removed_counts(slot_sources=None):
    """{产物成员名: 原版分支被剔掉的 Steam 成就钩子数}。

    原版分支（A 体）**不再带** `04 CG_ACHIEVEMENT`：成就由 Steam 分支原生提供。
    数字由 `build_patch` 写入 `resource/slot_sources.json` 的 `[sc].variant.ach_removed`。
    消费方：`build_patch` 自检、`cg_unlock_check`、`final_verification`（期望 = 基线 + 搬运体 − 本值）。
    """
    if slot_sources is None:
        path = os.path.join(HERE, 'resource', 'slot_sources.json')
        if not os.path.exists(path):
            return {}
        with open(path, encoding='utf-8') as fh:
            slot_sources = json.load(fh)
    out = {}
    for sc, info in (slot_sources or {}).items():
        v = (info or {}).get('variant') or {}
        n = v.get('ach_removed') or 0
        if not n:
            continue
        sf = info.get('steam_file') or (sc + '_E.ws2')
        out[sf] = out.get(sf, 0) + n
    return out


def body_evret_counts(steam_members):
    """{产物成员名: 搬运体自带的 `07 NextFile EVRET` 处数}——route=整脚本、choice=B 区间。

    消费方：`replay_guard_check` / `final_verification` 2b（期望 = Steam 基线 + 本值）。
    Steam 体自带回想出口时（如 `KAN_3002_2`：Steam 版在该脚本末尾有 EVRET），还原后的
    产物体已按 `replay_guards.json` 剥离出口；接回 Steam 体等于把这个出口也带回来——
    它是**Steam 原生演绎的组成部分**，不是孤立出口，所以按「基线 + 搬运体」计账。
    """
    out = {}
    for _sc, s in (load().get('scripts') or {}).items():
        sf = s.get('steam_file')
        raw = (steam_members or {}).get(sf)
        if raw is None:
            continue
        dec = ws2.decode(raw)
        ins, _ok = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)
        evr = lambda seq: sum(1 for _o, op, _s, o in seq
                              if op == 0x07 and o.split(b'\x00')[0] == b'EVRET')
        if s['kind'] == 'route':
            out[sf] = evr(ins)
            continue
        lo, hi = s['branch_b_steam_rows']
        r14 = [x for x in ins if x[1] == 0x14]
        blo = r14[lo - 1][0] + r14[lo - 1][2]
        bhi = r14[hi][0] + r14[hi][2]
        out[sf] = evr([x for x in ins if blo <= x[0] < bhi])
    return out


def variant_body_slots(script, slots, steam_members):
    """`script` 的产物槽序 → 变体分支体（Steam 副本）槽序集合（非变体脚本 = 空集）。

    * `choice`：分支 B = 行区间 `[lo, hi]` 的副本——`lo` 是被还原顶替的首行，线性流里
      不存在 ⇒ `('steam', lo)` 的**最后**一次出现即为分支 B 起点（其后必是 `lo+1..hi` 连续）；
    * `route`：尾部追加的整段 Steam 体（长度 = Steam 脚本 0x14 数）。

    消费方：`perf_sync_check` / `perf_consistency_check`——这些槽是 Steam 变体的逐字节
    副本，由 `variant_route_check` 的「逐指令等值」单独把守，不参与「产物 vs 原版」的
    线性对齐与顺序闸。
    """
    out = set()
    # 与消费方同口径：choice/vchoice 是 0f 条目槽，不占 0x14 行号——先过滤再编号
    slots = [tuple(x) for x in slots if x[0] not in ('choice', 'vchoice')]
    entries = [e for e in (load().get('scripts') or {}).items()
               if e[1].get('steam_file') == script or e[0] == script]
    for _sc, s in entries:
        if s['kind'] == 'choice':
            lo, hi = s['branch_b_steam_rows']
            hits = [i for i, x in enumerate(slots) if x == ('steam', lo)]
            if not hits:
                continue                       # 尚未拼接（基线状态）
            b = hits[-1]
            run = slots[b:b + (hi - lo + 1)]
            assert run == [('steam', k) for k in range(lo, hi + 1)],                 '%s 分支 B 槽位段不是连续 steam 行 %d..%d' % (_sc, lo, hi)
            out.update(range(b, b + (hi - lo + 1)))
        else:
            raw = (steam_members or {}).get(s['steam_file'])
            if raw is None:
                continue
            n = sum(1 for _o, op, _s2, _x in ws2dis.disassemble(ws2.decode(raw))[0] if op == 0x14)
            assert len(slots) >= n and all(x[0] == 'steam' for x in slots[-n:]),                 '%s 尾部 %d 槽不是追加的 Steam 体' % (_sc, n)
            out.update(range(len(slots) - n, len(slots)))
    return out
