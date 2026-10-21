# -*- coding: utf-8 -*-
"""S3 写盘（本作 Flight Diary）：按 `resource/restore_plan.json` 生成 `asset/Rio.arc`
与 `resource/slot_sources.json`。

产物
----
* `asset/Rio.arc` —— 相对 `backup/Rio.arc` 有差异的交付归档：
    - 14 个 `*_E.ws2` 宿主脚本**就地重建**（删 Steam 审查新写格 → 插原版格，见
      `tool/writer.py`）；
    - 新增成员 `AGS_001.ws2`（姬城あげは线整条，跨版本转换 + 注入成就）。
* `resource/slot_sources.json` —— 逐脚本「最终槽位序 → ('steam', 旧槽号) / ('orig', 原版行号)」，
  供 `.lng` 生成器按槽取中文（保留格直取官方条目、插入格取本项目语料）。

原版指令表的预处理（在进写盘器之前）
------------------------------------
1. `0x15` 的 `%LC<日文名>` → `%LC<Steam 罗马字键>`（`plan.meta.name_map`）；
2. `0x07` 的目标脚本名 → Steam 名（`AFT_003` → `AFT_003_E` 之类）；
3. 成就注入：在「`0x33` + `0x0b` + `0x0b`」之后插 `04 "CG_ACHIEVEMENT" 00`。

跳转改名（宿主骨架，不在插入块内）
----------------------------------
`KAN_3002_2_E` 还原成原版 H 场景后，尾跳须由 `KAN_3002_3_E`（全年龄替代场景）改指
`KAN_3003_E`，否则看完 H 又接播一遍全年龄内容。
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GALREV = os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')
for p in (ROOT, GALREV):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, paths, perfsync, pnaids, ws2, ws2dis, ws2conv, ws2fmt, writer  # noqa: E402

ACH = (0x04, b'CG_ACHIEVEMENT\x00')
JUMP_RENAME = {'KAN_3002_2': {'KAN_3002_3_E': 'KAN_3003_E'}}
REPLAY_GUARDS = os.path.join(ROOT, 'resource', 'replay_guards.json')


def _cond_id(ops):
    """`0x01 Condition` 的变量号（操作数布局 mode(1) id(2) value(4) a(4) b(4)）。"""
    return struct.unpack_from('<H', ops, 1)[0] if len(ops) >= 3 else None


def replay_exit_triads(ins):
    """原版里的「回想出口三连」：`01 flag[127]==1` + `01 var[110]==k` + `07 NextFile EVRET`。

    原版头部还有与之配对的「回想入口分派」（同两条 `01` + `06 Jump <场景起点>`）。Steam 把
    头部整簇删掉了（14 个宿主脚本全为 0 处 `01(127)`），所以只搬出口、不搬入口时那三条就是
    孤儿：`flag[127]=1` 且 `var[110]==k`（= 上次回想重播的正是一个吃 k 的脚本）时，**正常播放**
    也会在场景末尾 `NextFile EVRET` → 回主菜单，把它后面的场景整段吃掉。
    定案见 doc/route-mechanics.md「回想：入口/出口必须成对」、resource/replay_guards.json。
    """
    out = []
    for j in range(len(ins) - 2):
        op0, a0 = ins[j]
        if op0 != 0x01 or _cond_id(a0) != 127:
            continue
        op1, a1 = ins[j + 1]
        if op1 != 0x01 or _cond_id(a1) != 110:
            continue
        op2, a2 = ins[j + 2]
        if op2 != 0x07 or a2.split(b'\x00')[0] != b'EVRET':
            continue
        out.append((j, j + 1, j + 2, round(struct.unpack_from('<f', a1, 3)[0], 4)))
    return out


def steam_replay_gate(sinstrs):
    """Steam 侧是否自带 `01(127)` 回想守卫（`KAN_3002_2_E` 是唯一一个入口/出口成对的）。"""
    return any(op == 0x01 and _cond_id(ops) == 127 for _off, op, _sz, ops in sinstrs)


def evret_sites(instrs):
    """`07 NextFile "EVRET"` 的处数（归一化口径：只数 `07` 且目标串为 EVRET）。"""
    return sum(1 for _off, op, _sz, ops in instrs
               if op == 0x07 and ops.split(b'\x00')[0] == b'EVRET')


def orig_choice_entries(dec, orig_fmts):
    """{0x0f 的原版偏移: [条目 strid…]} —— 选项条目占文本槽位（见 tool/ws2.choice_entries）。"""
    out = {}
    for off, op, _sz, _ops in ws2dis.disassemble(dec, formats=orig_fmts)[0]:
        if op == 0x0F:
            out[off] = [struct.unpack_from('<H', dec, e[0])[0]
                        for e in ws2.choice_entries(dec, off)]
    return out


def prep_orig(dec, orig_fmts, name_map, jump_map, pna_map=None):
    """原版解码流 → (instrs, orig_offs, tail)：改名（`%LC` 名 / `0x07` 目标）。

    ⚠️ **不注入成就**（2026-10-16 实测定案）：
      * ORIG 与 Steam 的 CG 固有 id 对（`0x33` 后两条 `0x0b`）**交集为 0**（14 个脚本全为 0）
        ⇒ 按 ORIG 的 id 注入 `04 CG_ACHIEVEMENT` 是**空操作**（Steam 成就表里没有该 id）；
      * Steam 侧原有的 `0x0b`×2 + `04 CG_ACHIEVEMENT` 属 `KEEP_OPS` / 非 `LAYER_ORDER` 调用
        ⇒ **删格时已被 `writer.drop_units` 保留**，成就可达性不受影响
        （实测：被删区间内"只此一处"的 Steam 成就触发点 14 个，其 `0x0b`×2+成就调用全部留存）；
      * `AGS_001` 是**整条被删的线路**，Steam 侧不存在任何对应成就 ⇒ 更无须注入。
    """
    ins, tail = ws2conv.parse(dec, orig_fmts)
    offs, q = [], 0
    for op, ops in ins:
        offs.append(q)
        q += 1 + len(ops)
    stage = []
    n_lc = n_jmp = n_ids = 0
    id_miss = []
    disp = {}
    for j, (op, ops) in enumerate(ins):
        if op in (0x33, 0x34):
            parts = [x for x in ops.split(b'\x00') if x]
            if len(parts) >= 2:
                try:
                    disp[parts[0].decode('cp932')] = parts[1].decode('cp932').upper()
                except UnicodeDecodeError:
                    pass
        elif op == 0x37:
            parts = [x for x in ops.split(b'\x00') if x]
            if parts:
                try:
                    c = parts[0].decode('cp932')
                except UnicodeDecodeError:
                    c = ''
                for k in [k for k in disp if k.startswith(c)]:
                    disp.pop(k, None)
        elif op == 0x39 and pna_map:
            # 原版记录号 → Steam 记录号（哨兵删除/加层/重排，见 resource/pna_id_map.json）
            chan = pnaids.parse_039(ops)
            mp = pna_map.get(disp.get(chan[0]) if chan else None)
            if mp and chan:
                ops2, n, miss = pnaids.rewrite_039(ops, mp)
                if n:
                    ops = ops2
                    n_ids += n
                if miss:
                    id_miss.append({'op': j, 'chan': chan[0],
                                    'member': disp.get(chan[0]), 'ids': miss})
        if op == 0x15:
            q2 = ops.find(b'\x00')
            if q2 > 3 and ops[:3] == b'%LC':
                try:
                    nm = ops[3:q2].decode('cp932')
                except UnicodeDecodeError:
                    nm = None
                if nm and nm in name_map:
                    ops = writer.rewrite_lc_name(ops, name_map[nm])
                    n_lc += 1
        elif op == 0x07:
            new = writer.rename_07(bytes([op]) + ops, jump_map)
            if new != bytes([op]) + ops:
                ops = new[1:]
                n_jmp += 1
        stage.append((op, ops))
    out, ooffs, sent, n_ach = [], [], -1, 0
    j = 0
    while j < len(stage):
        out.append(stage[j])
        ooffs.append(offs[j])
        j += 1
    if id_miss:
        raise SystemExit('0x39 记录号映射缺项 %r' % (id_miss[:5],))
    return out, ooffs, tail, {'lc': n_lc, 'jump': n_jmp, 'ach': n_ach, 'ids': n_ids}


def site_noop(sc, slot, sinstrs, s14off, oin, o14, r, scope, deliver, kept):
    """`replace` 站点的前置检验：文本无需还原 + 演出序列已相同 + 素材原生且未被改画。"""
    if not perfsync.scope_text_clean(scope['scripts'].get(sc), slot):
        return False, 'text-restored'
    idx = {ins[0]: j for j, ins in enumerate(sinstrs)}
    s_sig = writer.perf_zone_sig(sinstrs, writer._perf_zone(sinstrs, idx, s14off, slot))
    o_sig = writer.perf_expected_sig(oin, o14, r)
    return perfsync.site_noop(s_sig, o_sig, deliver, kept)


def main():
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    scope = json.load(open(os.path.join(ROOT, 'resource', 'restore_scope.json'), encoding='utf-8'))
    guards = (json.load(open(REPLAY_GUARDS, encoding='utf-8')) or {}).get('scripts') or {}
    name_map = plan['meta']['name_map']
    deliver = perfsync.delivery_names(paths.STEAM)
    kept = perfsync.censored_keep_names() if hasattr(perfsync, 'censored_keep_names') else perfsync.censored_kept_names()
    pna_map = pnaids.load_map()
    orig_fmts = ws2conv.load_orig_formats(paths.orig_dir())

    jump_map = {}
    for sc, rec in scope['scripts'].items():
        of, sf = rec.get('orig_file'), rec.get('steam_file')
        if of and sf and of[:-4] != sf[:-4]:
            jump_map[of[:-4]] = sf[:-4]

    steam_members = arcbuild.read_raw(os.path.join(paths.STEAM, 'Rio.arc'))
    orig = {nb.decode('utf-16le'): d
            for nb, d in arcbuild.read_raw(os.path.join(paths.orig_dir(), 'Rio.arc'))}
    by_name = {nb.decode('utf-16le'): i for i, (nb, _) in enumerate(steam_members)}

    slot_sources, report, ach_steam = {}, [], {}
    evret_steam = {}
    for sc, p in sorted(plan['scripts'].items()):
        raw = orig[p['orig_file']]
        ins, ooffs, tail, st = prep_orig(ws2.decode(raw), orig_fmts, name_map, jump_map, pna_map)
        if p['kind'] == 'whole':
            conv = ws2conv.convert(ins, ooffs)
            dec = ws2conv.emit(conv, tail)
            back, _bt = ws2conv.parse(dec, ws2dis.FORMATS)
            assert len(back) == len(conv), '%s 指令数变化' % sc
            # 尾表（末尾 8 字节明文）按**新**指令流重算：跨版本转换会改 0x14/0x0f 条数，
            # 抄原版尾表 = 引擎按旧计数分配「已读位图」⇒ 写位越界 ⇒ 概率性闪退
            # （见 tool/ws2.py 尾表段 / lessons-learned §47）。
            _n0f = sum(1 for op, _o in conv if op == 0x0F)
            assert _n0f == 0, '%s 整脚本含 0x0f 选项表，需按条目补槽位（见 tool/ws2.choice_entries）' % sc
            _tc = ws2.tail_counts(dec[:-ws2.TAIL_LEN])
            enc = ws2.encode(dec[:-ws2.TAIL_LEN]) + struct.pack('<II', _tc[0], _tc[1])
            ins2, ok = ws2dis.disassemble(ws2.decode(enc))
            n14 = sum(1 for _, op, _, _ in ins2 if op == 0x14)
            slots = [['orig', r] for r in range(n14)]
            tgt = p['target_member']
            assert tgt not in by_name, '%s 已存在于 Steam 归档' % tgt
            steam_members.append((tgt.encode('utf-16le'), enc))
            by_name[tgt] = len(steam_members) - 1
            ach_steam[sc] = 0          # 整条被删的线路：Steam 侧不存在任何对应成就
            report.append('| %s | whole | 新增成员 %s | %d 格 | ok=%s | lc=%d jump=%d ach=%d ids=%d |'
                          % (sc, tgt, n14, ok, st['lc'], st['jump'], st['ach'], st['ids']))
        else:
            i = by_name[p['steam_file']]
            steam_dec = ws2.decode(steam_members[i][1])
            ach_steam[sc] = sum(1 for _, op, _, ops in ws2dis.disassemble(steam_dec)[0]
                                if op == 0x04 and ops.startswith(b'CG_ACHIEVEMENT'))
            sinstrs, _ok = ws2dis.disassemble(steam_dec)
            s14off = [off for off, op, _sz, _ops in sinstrs if op == 0x14]
            o14j = [j for j, (op, _ops) in enumerate(ins) if op == 0x14]
            noop = []
            for slot_s, spec in sorted((p.get('perf_sync') or {}).items()):
                if spec.get('mode') != 'replace':
                    continue
                ok, why = site_noop(sc, int(slot_s), sinstrs, s14off, ins, o14j,
                                    spec['orig_row'], scope, deliver, kept)
                if ok:
                    noop.append(int(slot_s))
                elif why != 'presentation-differs':
                    print('  ! %s 槽 %s 不能判 no-op：%s（照旧整段替换）' % (sc, slot_s, why))
            sub = {'drops': p['drops'], 'inserts': p['inserts'], 'external': {},
                   'orig_instrs': (ins, tail), 'orig_offs': ooffs,
                   'orig_choices': orig_choice_entries(ws2.decode(raw), orig_fmts),
                   'perf_sync': p.get('perf_sync') or {},
                   'perf_sync_noop': noop,
                   'jump_rename': JUMP_RENAME.get(sc, {}), 'script': sc}
            # 回想出口三连的搬运纪律（`resource/replay_guards.json`）：Steam 删了头部回想分派，
            # 孤立地搬回出口 => flag127=1 且 var110==k 时正常播放也会提前 NextFile EVRET。
            triads = replay_exit_triads(ins)
            o14j = [j for j, (op, _ops) in enumerate(ins) if op == 0x14]

            def _span(r0, r1):
                return (o14j[r0 - 1] + 1 if r0 > 0 else 0), o14j[r1] + 1

            spans = [_span(r0, r1) for _a, r0, r1 in p['inserts']]
            hit = [t for t in triads if any(lo <= t[0] and t[2] < hi for lo, hi in spans)]
            if hit or steam_replay_gate(sinstrs):
                decl = guards.get(sc)
                assert decl, '%s 会在产物里带回想出口三连/守卫，但 resource/replay_guards.json 无条目' % sc
                want = 'keep' if steam_replay_gate(sinstrs) else 'drop'
                assert decl['action'] == want, \
                    '%s 回想守卫处置与入库表不符：表=%s 实测=%s（Steam 自带守卫=%s）' \
                    % (sc, decl['action'], want, steam_replay_gate(sinstrs))
                got = sorted({t[3] for t in triads})
                assert got == sorted(decl['var110']), \
                    '%s 回想出口 var110 %s 与入库表 %s 不符' % (sc, got, decl['var110'])
                if want == 'drop':
                    sub['skip_orig'] = sorted(j for t in hit for j in t[:3])
                    print('  - %s 剥离回想出口三连 %d 组（var110=%s）：Steam 侧无入口分派'
                          % (sc, len(hit), got))
            evret_steam[sc] = evret_sites(sinstrs)
            res = writer.rebuild_host(steam_dec, ws2.decode(raw), sub, orig_fmts)
            assert res['ok'], '%s 产物线性解析不自洽' % sc
            n_text = res['n14'] + res['n_choice']   # 0x14 + Σ(0f count) == 文本槽位数
            assert n_text == res['n_slots'], \
                '%s 文本槽位 %d（0x14 %d + 选项 %d）!= 槽表 %d' % (
                    sc, n_text, res['n14'], res['n_choice'], res['n_slots'])
            assert res['fix_bad'] == 0, '%s 跳转回写失败 %s' % (sc, res['fix_bad_detail'][:3])
            # 选项帧内的 `0x16` 必须剔除：Steam 侧它会把 `MenuInf.enabled/effect` 推成
            # false/true（只有 closeMessageWindow 会产生这对值），输入门永久关闭 ⇒
            # 选项能画但点不动。实机证据见 doc/engine-mechanics.md「0x16 的副作用」。
            _dec16 = ws2.decode(res['raw'])
            _dec16, _n16 = ws2.drop_choice_frame_op16(_dec16)
            if _n16:
                res['raw'] = ws2.encode(_dec16)
                print('  - %s 剔除选项帧内 0x16 × %d（Steam 侧会关闭输入门）' % (sc, _n16))
            steam_members[i] = (steam_members[i][0], res['raw'])
            slots = [[k, v] for k, v in res['slot_sources']]
            report.append('| %s | host | %s | %d 槽（插 %d） | fixup=%d/%d（回落 %d） | lc=%d jump=%d ach=%d ids=%d | noop=%d |'
                          % (sc, p['steam_file'], res['n_slots'],
                             sum(r[2] - r[1] + 1 for r in p['inserts']),
                             res['fixups'] - res['fix_bad'], res['fixups'],
                             res['fix_fallback'], st['lc'], st['jump'], st['ach'], st['ids'],
                             len(res['perf_noop'])))
        slot_sources[sc] = {'steam_file': p['steam_file'], 'kind': p['kind'], 'slots': slots}

    out_arc = os.path.join(ROOT, 'asset', 'Rio.arc')
    os.makedirs(os.path.dirname(out_arc), exist_ok=True)
    n_orig = len(steam_members) - sum(1 for sc, p in plan['scripts'].items() if p['kind'] == 'whole')
    arcbuild.write_arc(steam_members, out_arc)
    cnt, size, end = arcbuild.verify(out_arc, expect_count=len(steam_members))
    with open(os.path.join(ROOT, 'resource', 'slot_sources.json'), 'w', encoding='utf-8') as fh:
        json.dump(slot_sources, fh, ensure_ascii=False, indent=1)
    print('写出 %s：成员 %d（Steam 原 %d）、%d B' % (out_arc, cnt, n_orig, size))
    print('\n'.join(report))

    # ── 产物自检（内容面）───────────────────────────────────────────────
    # ① 线性解析自洽；② 0x14 数 == 槽表长度；③ **成就触发点覆盖率 100%**
    # （每个「`0x33` + 两条 `0x0b`」站点之后都必须有 `04 CG_ACHIEVEMENT 00` —— 这是
    # Steam 侧的实测不变式，还原块按同型补齐后必须仍然成立）。
    prod = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(out_arc)}
    _ok_tail, _bad_tail = ws2.check_tails(prod)
    assert not _bad_tail, '尾表（末尾 8 字节明文）与实算条数不符：%r' % (_bad_tail[:5],)
    for sc, info in sorted(slot_sources.items()):
        f = info['steam_file'] if info['kind'] == 'host' else plan['scripts'][sc]['target_member']
        ins2, ok = ws2dis.disassemble(ws2.decode(prod[f]))
        n14 = sum(1 for _, op, _, _ in ins2 if op == 0x14)
        assert ok, '%s 产物线性解析不自洽' % sc
        _nch = sum(len(ws2.choice_entries(ws2.decode(prod[f]), off))
                   for off, op, _s, _x in ins2 if op == 0x0F)
        assert n14 + _nch == len(info['slots']), \
            '%s 产物文本槽位 %d（0x14 %d + 选项 %d）!= 槽表 %d' % (
                sc, n14 + _nch, n14, _nch, len(info['slots']))
        ach = sum(1 for _, op, _, ops in ins2 if op == 0x04 and ops.startswith(b'CG_ACHIEVEMENT'))
        want = ach_steam.get(sc, 0)
        assert ach == want, \
            '%s 成就调用 %d != Steam 原有 %d（Steam 侧触发点必须一个不丢）' % (sc, ach, want)
        # ④ 回想出口不得凭空增加：产物里的 `07 NextFile EVRET` 处数必须 == Steam 原有处数。
        #    （增加 = 搬回了孤儿的「出口」而没有配套的「入口分派」⇒ 会在场景末尾提前回主菜单。）
        if info['kind'] == 'host':
            evr = evret_sites(ins2)
            assert evr == evret_steam.get(sc, 0), \
                '%s 回想出口 EVRET %d != Steam 原有 %d（孤立的出口会让正常播放提前退场）' \
                % (sc, evr, evret_steam.get(sc, 0))
        print('  %-14s 槽 %-5d 成就调用 %-4d = Steam 原有 ✅' % (sc, len(info['slots']), ach))
    print('尾表：%d 个 .ws2 的末尾 8 字节明文 == 实算 (消息数, 选项数) ✅' % len(_ok_tail))
    print('自检通过：%d 脚本 —— 线性解析自洽 / 0x14 数 == 槽表 / Steam 成就触发点一个不丢 / 尾表正确'
          % len(slot_sources))
    print('槽位表 → resource/slot_sources.json（%d 脚本）' % len(slot_sources))


if __name__ == '__main__':
    main()
