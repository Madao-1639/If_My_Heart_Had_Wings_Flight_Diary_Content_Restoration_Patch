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
from tool import variants  # noqa: E402
from tool import censormap  # noqa: E402  （9XX 号段命名隔离）

ACH = (0x04, b'CG_ACHIEVEMENT\x00')
JUMP_RENAME = {'KAN_3002_2': {'KAN_3002_3_E': 'KAN_3003_E'}}
REPLAY_GUARDS = os.path.join(ROOT, 'resource', 'replay_guards.json')
ANIM_CLEARS = os.path.join(ROOT, 'resource', 'anim_exit_clears.json')
VARIANT_TABLE = os.path.join(ROOT, 'resource', 'variant_routes.json')


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
    n_lc = n_jmp = n_ids = n_46 = 0
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
        elif op == 0x46:
            # 子层槽绑定标志归一（跨引擎移植，与 0x39 记录号映射同类）：`0x46` 第一条
            # （绑定 PNA 子层到引擎层槽）的标志字节，原版工具链写 `0x80`、Steam 工具链
            # 写 `0xf0`（全库 ~7.6k 处零交叉；`0x00`＝纯坐标定位，两侧一致）。原版块
            # 带着 `0x80` 进 Steam 引擎会欠绑定子层槽——未重绑的槽保留上一次显示的
            # 子图 ⇒ 「上一处的立绘未去除、压在后续 CG 上，直到清槽」。整脚本转换路径
            # （`ws2conv.convert`）不经 `writer._conv`，必须在此归一；判据与移植路径
            # 共用 `writer.norm_op46_flag`（幂等）。
            ops_n = writer.norm_op46_flag(ops)
            if ops_n != ops:
                ops = ops_n
                n_46 += 1
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
    return out, ooffs, tail, {'lc': n_lc, 'jump': n_jmp, 'ach': n_ach, 'ids': n_ids, 'flag46': n_46}


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
    anim_clears_all = json.load(open(ANIM_CLEARS, encoding='utf-8'))
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

    # 变体共存表：{脚本: spec}；只对 host 类脚本生效（whole 是新增成员，无 Steam 宿主可搬）
    variant_specs = {}
    if os.path.exists(VARIANT_TABLE):
        _vt = variants.load()
        variant_specs = {k: v for k, v in (_vt.get('scripts') or {}).items()}
        for _k, _v in variant_specs.items():
            assert plan['scripts'].get(_k, {}).get('kind') == 'host', \
                '%s 不在 restore_plan 的 host 名单里，变体表无法挂接' % _k
    variant_detail = {}

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
            report.append('| %s | whole | 新增成员 %s | %d 格 | ok=%s | lc=%d jump=%d ach=%d ids=%d flag46=%d |'
                          % (sc, tgt, n14, ok, st['lc'], st['jump'], st['ach'], st['ids'], st['flag46']))
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
            # 变体脚本：**有选项的原版情节**不再保留 Steam 的 CG 解锁对与成就钩子
            #（成就/鉴赏由 Steam 分支原生提供）。范围按变体表给出：
            #   choice → 接缝之后到汇合点之前的那段；route → 整脚本。
            _no_ach = None
            _vsp = variant_specs.get(sc)
            if _vsp:
                if _vsp['kind'] == 'choice':
                    _a = int(_vsp['seam']['after'][1])
                    _b = int(((_vsp.get('confluence') or {}).get('at') or [None, None])[1]
                             or len(s14off))
                    _no_ach = set(range(_a + 1, _b))
                else:
                    _no_ach = set(range(len(s14off)))
            sub = {'drops': p['drops'], 'inserts': p['inserts'], 'external': {},
                   'no_ach_slots': _no_ach,
                   'orig_instrs': (ins, tail), 'orig_offs': ooffs,
                   'orig_choices': orig_choice_entries(ws2.decode(raw), orig_fmts),
                   'perf_sync': p.get('perf_sync') or {},
                   'perf_sync_noop': noop,
                   'jump_rename': JUMP_RENAME.get(sc, {}), 'script': sc,
                   'anim_exit_clears': anim_clears_all.get(sc) or {}}
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
            if res['state_fix']:
                print('  - %s 状态规范化（插入块/replace 站点）发清屏 %d 条：%s'
                      % (sc, len(res['state_fix']),
                         ['槽%d r%d %s' % (x['anchor'], x['row'], x['chan'])
                          for x in res['state_fix'][:8]]))
            assert res['ok'], '%s 产物线性解析不自洽' % sc
            n_text = res['n14'] + res['n_choice']   # 0x14 + Σ(0f count) == 文本槽位数
            assert n_text == res['n_slots'], \
                '%s 文本槽位 %d（0x14 %d + 选项 %d）!= 槽表 %d' % (
                    sc, n_text, res['n14'], res['n_choice'], res['n_slots'])
            assert res['fix_bad'] == 0, '%s 跳转回写失败 %s' % (sc, res['fix_bad_detail'][:3])
            # 选项帧内的 `0x16` 必须剔除：Steam 侧它会把 `MenuInf.enabled/effect` 推成
            # false/true（只有 closeMessageWindow 会产生这对值），输入门永久关闭 ⇒
            # 选项能画但点不动。实机证据见 doc/engine-mechanics.md「0x16 的副作用」。
            # ⚠️ 必须在 `variants.apply` **之前**做：还原块自带游戏原有选项帧时
            #（`BEF_004`），这里删一条 0x16 会把后面整体前移 3 字节，令变体布局（brA/brB/conf）失准。
            _dec16 = ws2.decode(res['raw'])
            _dec16, _n16 = ws2.drop_choice_frame_op16(_dec16)
            if _n16:
                res['raw'] = ws2.encode(_dec16)
                print('  - %s 剔除选项帧内 0x16 × %d（Steam 侧会关闭输入门）' % (sc, _n16))
            # 同名 CG 的 9XX 命名隔离：产品侧（A 路径 + 共享内容）一律引用原版画的新编号，
            # 原名留给 Steam 原生体（分支 B / route 体，它们是原字节搬运，天然用原名）。
            # 同长度改名 ⇒ 不改变任何偏移（见 tool/censormap.py）。
            _dec_iso, _n_iso = ws2.decode(res['raw']), 0   # 名字在**解码流**里，raw 是混淆后的
            for _old, _new in censormap.isolate_refs().items():
                _ob, _nb = _old.encode('ascii'), _new.encode('ascii')
                assert len(_ob) == len(_nb), '9XX 隔离名必须与原名等长：%s → %s' % (_old, _new)
                if _ob in _dec_iso:
                    _n_iso += _dec_iso.count(_ob)
                    _dec_iso = _dec_iso.replace(_ob, _nb)
            if _n_iso:
                res['raw'] = ws2.encode(_dec_iso)
                print('  - %s 9XX 命名隔离：%d 处显示名改为原版画编号' % (sc, _n_iso))
            # 变体共存（resource/variant_routes.json）：Steam 差分情节以选项/路由接回
            vspec = variant_specs.get(sc)
            if vspec:
                _vraw, _vslots, _vdetail = variants.apply(
                    sc, steam_members[i][1], res['raw'], res['slot_sources'], vspec)
                res['raw'] = _vraw
                res['slot_sources'] = _vslots
                _vdetail['ach_removed'] = res.get('ach_dropped', 0)
                variant_detail[sc] = _vdetail
                print('  - %s 变体共存（%s）：var%d，槽 %d→%d，尾表 %s'
                      % (sc, _vdetail['kind'], _vdetail['var_id'],
                         res['n_slots'], _vdetail['slots'], _vdetail['tail_counts']))
            # 变体帧自身不得带 0x16（幂等复检；删到就说明拼接器写错了）
            _dec16b, _n16b = ws2.drop_choice_frame_op16(ws2.decode(res['raw']))
            assert _n16b == 0, '%s 变体帧内出现 0x16 ×%d（拼接器缺陷）' % (sc, _n16b)
            steam_members[i] = (steam_members[i][0], res['raw'])
            slots = [[k, v] for k, v in res['slot_sources']]
            report.append('| %s | host | %s | %d 槽（插 %d） | fixup=%d/%d（回落 %d） | lc=%d jump=%d ach=%d ids=%d flag46=%d | noop=%d |'
                          % (sc, p['steam_file'], res['n_slots'],
                             sum(r[2] - r[1] + 1 for r in p['inserts']),
                             res['fixups'] - res['fix_bad'], res['fixups'],
                             res['fix_fallback'], st['lc'], st['jump'], st['ach'], st['ids'],
                             st['flag46'], len(res['perf_noop'])))
        slot_sources[sc] = {'steam_file': p['steam_file'], 'kind': p['kind'], 'slots': slots}
        if sc in variant_detail:
            # 变体布局（供闸门直接使用：条目落点 brA/brB、汇合点 conf、区间、槽位信息）
            slot_sources[sc]['variant'] = variant_detail[sc]

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
    # 搬运体 EVRET 口径必须取**原始 Steam 基线**（此时 steam_members 已被变体产物替换）
    _body_evr = variants.body_evret_counts(
        {nb.decode('utf-16le'): d for nb, d in
         arcbuild.read_raw(os.path.join(paths.STEAM, 'Rio.arc'))})
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
        # 变体共存把 Steam 体**原字节**接回产物：原版体的钩子数已与 Steam 基线对齐，
        # 再加 Steam 体自带的钩子 ⇒ 期望 = 基线 + 搬运体钩子数（不是回归，是双版本各带各的）
        # 分支体各带各的解锁/成就位点，不跨分支重放（条件可达是正确语义）；
        # 且**原版分支不带 Steam 成就钩子**（成就由 Steam 分支原生提供）⇒ 减去 A 体剔除数
        _in_body = variant_detail.get(sc, {}).get('ach_in_body', 0)
        _removed = variant_detail.get(sc, {}).get('ach_removed', 0)
        _extra = _in_body - _removed
        want += _extra
        assert ach == want, \
            '%s 成就调用 %d != 期望 %d（基线 %d + 搬运体 %d − 原版分支剔除 %d）' % (
                sc, ach, want, ach_steam.get(sc, 0), _in_body, _removed)
        # ④ 回想出口不得凭空增加：产物里的 `07 NextFile EVRET` 处数必须 == Steam 原有处数。
        #    （增加 = 搬回了孤儿的「出口」而没有配套的「入口分派」⇒ 会在场景末尾提前回主菜单。）
        if info['kind'] == 'host':
            evr = evret_sites(ins2)
            _allow = _body_evr.get(info['steam_file'], 0)
            assert evr == evret_steam.get(sc, 0) + _allow, \
                '%s 回想出口 EVRET %d != 期望 %d（Steam 原有 %d + 搬运体 %d；孤立的出口会让正常播放提前退场）' \
                % (sc, evr, evret_steam.get(sc, 0) + _allow, evret_steam.get(sc, 0), _allow)
        print('  %-14s 槽 %-5d 成就调用 %-4d = Steam 原有 ✅' % (sc, len(info['slots']), ach))
    print('尾表：%d 个 .ws2 的末尾 8 字节明文 == 实算 (消息数, 选项数) ✅' % len(_ok_tail))
    print('自检通过：%d 脚本 —— 线性解析自洽 / 0x14 数 == 槽表 / Steam 成就触发点一个不丢 / 尾表正确'
          % len(slot_sources))
    print('槽位表 → resource/slot_sources.json（%d 脚本）' % len(slot_sources))


if __name__ == '__main__':
    main()
