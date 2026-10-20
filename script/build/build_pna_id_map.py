# -*- coding: utf-8 -*-
"""PNA 记录号映射与「层内修复」判定表（本作 Flight Diary）。

背景
----
两侧同名 `.pna` 里，**记录号（0x39 的 u16）是记录下标、含哨兵/空层**（见
`doc/pna-resources.md`）。Steam 版把原版 PNA 里的哨兵记录整批删掉，并把部分
「身体/着衣」子图改画成和谐版；而脚本里的 `0x39` 记录号仍是**原版编号**
（Steam 侧的 0x39 号位在自己的 PNA 内一一有效，但语义已按 Steam 记录表偏移）。
因此：

* **原版来源的块**（插入的原版格、`perf_sync replace` 带入的原版块）必须把
  `0x39` 的记录号从「原版记录号」换算成「Steam 记录号」，否则取到别的子图；
* 部分记录在 Steam 被改画（裸体/内衣 → 着衣），仅换号仍显示和谐版 ⇒ 需要把
  该记录的子图与 box 换回原版（**层内修复**，不改记录数/顺序/画布）。

本表是这两件事的唯一输入（build 只读本表）：

* `map`      ：原版记录号 → Steam 记录号（按记录秩或按内容配对）；
* `repair`   ：允许层内修复的 Steam 记录号（子图 + box 换成原版）；
* `waive`    ：有内容差但**不得修复**的记录及原因。

层内修复的硬约束（用户 2026-10-20 定案）
----------------------------------------
**被换图不能出现在 Steam 新增段/未还原段复用的记录上**，否则会把新路线/新写的
场景改成原版画面，产生歧义。判定方式：扫描 Steam 全库脚本的 `0x39` 引用，把
每个命中记录号的引用行分类：

* `restored_slot`：本补丁 25 个脚本里的保留格/原版格 ⇒ 允许（正是还原目标）；
* `dropped_row`：该行已被删格 ⇒ 引用不进产物 ⇒ 无影响；
* `steam_added`：Steam 新增格（`orig_row=None`）⇒ **禁止**；
* `steam_route`：Steam 新增路线（`Rio1.arc` 的 `AKA_*`）⇒ **禁止**；
* `other_script`：不在还原范围的脚本 ⇒ **禁止**（保守）。

策略选择
--------
* `rank`   ：两侧**非空记录数相等**（哨兵删除）⇒ 按「非空记录秩」一一对应。
  内容可能被改画（和谐层），映射仍正确（同一身体层的着衣版）。
* `content`：非空记录数不等/记录被重排（如 `H朱莉_01*`：Steam 朱莉线新增 2 层，
  43..46 整体移到 45..48）⇒ 按子图 RGBA 配对。

用法
----
    mamba run -n GalRev python script/build/build_pna_id_map.py [--write]

默认 dry-run；`--write` 写 `resource/pna_id_map.json`（入库表）。
"""
import argparse
import collections
import json
import os
import re
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

from tool import arcbuild, paths, pna, ws2, ws2dis  # noqa: E402
from tool.pnglite import diff_rgba, rgba_of  # noqa: E402

OUT_JSON = os.path.join(ROOT, 'resource', 'pna_id_map.json')
OUT_REPORT = os.path.join(ROOT, 'tmp', 'pna_id_map_report.txt')
SAME_MEAN = 1.0
SAME_BIG = 0.01
IMG_EXT = ('.png', '.pna')

# 非脚本成员（归档里混有图片/文本/数据）——扫描 0x39 时跳过
SKIP_ARC = re.compile(r'^(graphic|chip\d*|voice|se|bgm|pgse|pse|sysgraphic|'
                      r'fonts|effect|chip\d+)\b', re.I)


def members(path):
    return {nb.decode('utf-16le', 'replace').upper(): d for nb, d in arcbuild.read_raw(path)}


def real_indices(p):
    return [i for i, x in enumerate(p['images']) if x]


def is_w(member):
    return bool(re.search(r'_W\.PNA$', member, re.I))


class Img:
    """子图 RGBA 缓存（原始字节哈希 → (w,h,rgba)）。"""

    def __init__(self):
        self.c = {}

    def get(self, blob):
        k = hash(blob)
        if k not in self.c:
            self.c[k] = rgba_of(blob)
        return self.c[k]


IMG = Img()


def pair_same(a, b):
    """两张子图 → (same, mean, big, size_equal)。"""
    wa, ha, ra = IMG.get(a)
    wb, hb, rb = IMG.get(b)
    if (wa, ha) != (wb, hb):
        return False, None, None, False
    m, big = diff_rgba(ra, rb)
    return (m < SAME_MEAN and big < SAME_BIG), m, big, True


def build_rank(steam, orig):
    """非空记录数相等 ⇒ 按秩映射；返回 (map, detail)。"""
    sa, sb = real_indices(steam), real_indices(orig)
    assert len(sa) == len(sb), 'rank strategy requires equal real counts'
    mp, det = {}, []
    for na, nb in zip(sa, sb):
        same, m, big, size_eq = pair_same(steam['images'][na], orig['images'][nb])
        mp[nb] = na
        det.append({'orig': nb, 'steam': na, 'same': same, 'size_eq': size_eq,
                    'mean': None if m is None else round(m, 3),
                    'big': None if big is None else round(big, 5),
                    'orig_box': list(orig['entries'][nb][2:6]),
                    'steam_box': list(steam['entries'][na][2:6])})
    return mp, det


def build_content(steam, orig):
    """按子图 RGBA 配对（优先同 box）；返回 (map, detail)。未配对的原版记录不入 map。"""
    sa, sb = real_indices(steam), real_indices(orig)
    cand = {}
    for na in sa:
        wa, ha, ra = IMG.get(steam['images'][na])
        for nb in sb:
            wb, hb, rb = IMG.get(orig['images'][nb])
            if (wa, ha) != (wb, hb):
                continue
            m, big = diff_rgba(ra, rb)
            if m < SAME_MEAN and big < SAME_BIG:
                box_s = tuple(steam['entries'][na][2:6])
                box_o = tuple(orig['entries'][nb][2:6])
                cand.setdefault(nb, []).append((0 if box_s == box_o else 1, m, na))
    mp, det = {}, []
    for nb in sb:
        hits = sorted(cand.get(nb) or [])
        if not hits:
            continue
        _pri, m, na = hits[0]
        mp[nb] = na
        det.append({'orig': nb, 'steam': na, 'same': True, 'size_eq': True,
                    'mean': round(m, 3), 'big': 0.0,
                    'orig_box': list(orig['entries'][nb][2:6]),
                    'steam_box': list(steam['entries'][na][2:6])})
    # 内容配不上的记录（如 `H朱莉_01W` 的全画布底图：画布重心裁切导致 RGBA 尺寸不同）
    # 在「未被占用的 Steam 记录」里按 **box 尺寸/位置最近** 补映射，避免抢已配对的号。
    used = set(mp.values())
    for nb in sb:
        if nb in mp:
            continue
        oe = orig['entries'][nb]
        cands = []
        for na in sa:
            if na in used:
                continue
            se = steam['entries'][na]
            cands.append((abs(oe[4] - se[4]) + abs(oe[5] - se[5]),
                          abs(oe[2] - se[2]) + abs(oe[3] - se[3]), na))
        if not cands:
            continue
        cands.sort()
        na = cands[0][2]
        mp[nb] = na
        used.add(na)
        det.append({'orig': nb, 'steam': na, 'same': False, 'size_eq': False,
                    'mean': None, 'big': None,
                    'orig_box': list(oe[2:6]),
                    'steam_box': list(steam['entries'][na][2:6]),
                    'fallback': 'nearest_box'})
    return mp, det


def parse_039(ops):
    """`0x39` 操作数 → (chan, head3, ids)；解析失败返回 None。"""
    q = ops.find(b'\x00')
    if q < 0:
        return None
    try:
        chan = ops[:q].decode('cp932')
    except UnicodeDecodeError:
        return None
    rest = ops[q + 1:]
    if len(rest) < 3:
        return None
    n = rest[2]
    if 3 + 2 * n > len(rest):
        return None
    ids = [struct.unpack_from('<H', rest, 3 + 2 * k)[0] for k in range(n)]
    return chan, rest[:3], ids


def rebuild_039(chan, head3, ids):
    out = bytearray(chan.encode('cp932') + b'\x00' + head3)
    for i in ids:
        out += struct.pack('<H', i)
    return bytes(out)


def scan_refs(rio_path, fmt, want):
    """归档内脚本的 0x39 引用 → [(file, row, chan, member, ids)]。"""
    out = []
    for nb, raw in arcbuild.read_raw(rio_path):
        fn = nb.decode('utf-16le', 'replace')
        if not fn.lower().endswith('.ws2'):
            continue
        try:
            ins = ws2dis.disassemble(ws2.decode(raw), formats=fmt)[0]
        except Exception:
            continue
        disp, row = {}, -1
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
            if op == 0x39:
                p = parse_039(ops)
                if not p:
                    continue
                chan, _head, ids = p
                nm = disp.get(chan)
                if nm in want:
                    out.append((fn, row, chan, nm, ids))
    return out


def arc_scripts(root, want):
    """读目录内全部归档，收集引用。"""
    out = []
    for fn in sorted(os.listdir(root)):
        if not fn.lower().endswith('.arc') or SKIP_ARC.match(fn):
            continue
        out += scan_refs(os.path.join(root, fn), ws2dis.FORMATS, want)
    return out


def load_slot_index():
    """(脚本, Steam 行号) → (product_slot, src) 反向索引；以及 plan/merged 信息。"""
    ss = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    scope = json.load(open(os.path.join(ROOT, 'resource', 'restore_scope.json'), encoding='utf-8'))
    # Steam 纯增区间（不依赖 tmp/merged.jsonl，保证干净检出可复现）
    added = set()
    for sc, rec in (scope.get('scripts') or {}).items():
        for r in rec.get('regions') or []:
            if r.get('form') == 'pure_add' and r.get('action') in ('keep', 'no_action'):
                for row in range(r['steam_range'][0], r['steam_range'][1] + 1):
                    added.add((sc, row))
    idx = {}
    for sc, info in ss.items():
        for i, (src, val) in enumerate(info['slots']):
            if src == 'steam':
                idx.setdefault((sc, int(val)), []).append((i, src))
    return ss, plan, idx, added


def row_context(fn, row, ss, idx, added=()):
    """把一条 Steam 脚本引用行分类（见模块 docstring）。"""
    base = fn[:-4]
    if base.endswith('_E'):
        base = base[:-2]
    if base.startswith('AKA'):
        return 'steam_route'
    if base not in ss or ss[base]['kind'] != 'host':
        return 'other_script'
    if (base, row) in added:
        return 'steam_added'
    if idx.get((base, row)):
        return 'restored_slot'
    return 'dropped_row'


def orig_used_ids(plan, orig_rio, orig_names):
    """还原块实际会引用到的原版记录号：{member: set(orig record)}。"""
    out = collections.defaultdict(set)
    want = set(orig_names)
    # 收集需要搬运的原版行区间
    spans = collections.defaultdict(list)
    for sc, p in plan['scripts'].items():
        of = p['orig_file']
        if p['kind'] == 'whole':
            spans[of].append((0, 10 ** 9))
            continue
        for _a, r0, r1 in p.get('inserts') or []:
            spans[of].append((r0, r1))
        for spec in (p.get('perf_sync') or {}).values():
            if isinstance(spec, dict) and spec.get('orig_row') is not None:
                r = int(spec['orig_row'])
                spans[of].append((r, r))
    for fn, blobs in spans.items():
        raw = orig_rio.get(fn)
        if raw is None:
            continue
        try:
            ins = ws2dis.disassemble(ws2.decode(raw), formats=ws2dis.FORMATS_ORIG)[0]
        except Exception:
            continue
        rows, cur, disp = [], [], {}
        for _off, op, _sz, ops in ins:
            if op == 0x14:
                rows.append((cur, dict(disp)))
                cur = []
                continue
            cur.append((op, ops))
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
        rows.append((cur, dict(disp)))
        for r0, r1 in spans[fn]:
            for r in range(max(0, r0), min(len(rows), r1 + 1)):
                pref, d = rows[r]
                for op, ops in pref:
                    if op != 0x39:
                        continue
                    p = parse_039(ops)
                    if not p:
                        continue
                    chan, _h, ids = p
                    nm = d.get(chan)
                    if nm in want:
                        out[nm].update(ids)
    return out


def main():
    ap = argparse.ArgumentParser(description='生成 PNA 记录号映射 / 层内修复表')
    ap.add_argument('--write', action='store_true', help='写 resource/pna_id_map.json')
    args = ap.parse_args()

    steam = members(os.path.join(paths.STEAM, 'Graphic.arc'))
    orig = members(os.path.join(paths.orig_dir(), 'Graphic.arc'))
    # 只处理 **censor_map keep** 的同名 PNA：`overwrite` 成员的产物字节已是原版
    # （记录表即原版）⇒ 记录号不能换算，也不能层内修复。
    cmap = json.load(open(os.path.join(ROOT, 'resource', 'censor_map.json'), encoding='utf-8'))
    keep_names = {m['name'].upper() for m in cmap['members']
                  if m.get('action') == 'keep' and m.get('archive') == 'Graphic.arc'
                  and m['name'].upper().endswith('.PNA')}
    names = sorted(n for n in steam if n in orig and n.upper().endswith('.PNA')
                   and n.upper() in keep_names)
    if not names:
        raise SystemExit('censor_map 中无 keep 的同名 PNA（检查资源表）')
    ss, plan, idx, added = load_slot_index()
    refs = arc_scripts(paths.STEAM, set(names))
    orig_rio = {nb.decode('utf-16le', 'replace'): d
                for nb, d in arcbuild.read_raw(os.path.join(paths.orig_dir(), 'Rio.arc'))}
    used = orig_used_ids(plan, orig_rio, set(names))

    out = {'meta': {
        'purpose': 'PNA 记录号（0x39 u16）原版→Steam 映射 + 允许层内修复的记录清单',
        'producer': 'script/build/build_pna_id_map.py',
        'consumers': ['script/build/build_patch.py', 'script/build/build_pna_repair.py',
                      'script/checks/pna_id_check.py'],
        'coordinate': 'record index (0-based, includes sentinel/empty records)',
        'same_threshold': {'mean': SAME_MEAN, 'big': SAME_BIG},
        'repair_guard': 'changed record must not be referenced by steam_added/steam_route/other_script rows',
    }, 'members': {}}

    report = ['# PNA 记录映射与层内修复判定', '',
              '| 成员 | 策略 | 记录 orig/steam（非空） | 映射 | 改画 | 修复 | 豁免 |',
              '|---|---|---|---:|---:|---:|---:|']
    for nm in names:
        a, b = pna.load(steam[nm]), pna.load(orig[nm])
        ra, rb = real_indices(a), real_indices(b)
        rec = {'archive': 'Graphic.arc', 'canvas': {'steam': [a['canvas_w'], a['canvas_h']],
                                                    'orig': [b['canvas_w'], b['canvas_h']]},
               'orig_count': b['layer_count'], 'steam_count': a['layer_count'],
               'orig_real': len(rb), 'steam_real': len(ra)}
        if len(ra) == len(rb):
            rec['strategy'] = 'rank'
            mp, det = build_rank(a, b)
        else:
            rec['strategy'] = 'content'
            mp, det = build_content(a, b)
        changed = []
        for d in det:
            if not d['size_eq']:
                changed.append({'orig': d['orig'], 'steam': d['steam'], 'kind': 'size',
                                'orig_box': d['orig_box'], 'steam_box': d['steam_box']})
            elif not d['same']:
                changed.append({'orig': d['orig'], 'steam': d['steam'], 'kind': 'pixel',
                                'mean': d['mean'], 'big': d['big']})
        # 引用上下文（只对「映射到的 Steam 记录号」判）
        ctx = collections.defaultdict(collections.Counter)
        for fn, row, _chan, _mem, ids in refs:
            if _mem != nm:
                continue
            for i in ids:
                ctx[i][row_context(fn, row, ss, idx, added)] += 1
        repair, waive = [], []
        for c in changed:
            st = c['steam']
            hits = ctx.get(st) or {}
            bad = {k: v for k, v in hits.items()
                   if k in ('steam_added', 'steam_route', 'other_script')}
            use = used.get(nm) or set()
            if bad:
                waive.append(dict(c, reason='referenced by %s' % sorted(bad), refs=dict(hits)))
            elif c['orig'] not in use:
                waive.append(dict(c, reason='not referenced by restored orig blocks',
                                  refs=dict(hits)))
            else:
                repair.append(dict(c, refs=dict(hits)))
        rec['map'] = {str(k): v for k, v in sorted(mp.items())}
        rec['detail'] = det
        rec['changed'] = changed
        rec['repair'] = repair
        rec['waive'] = waive
        out['members'][nm] = rec
        report.append('| %s | %s | %d/%d | %d | %d | %d | %d |'
                      % (nm, rec['strategy'], len(rb), len(ra), len(mp),
                         len(changed), len(repair), len(waive)))

    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(report) + '\n')
    n_rep = sum(len(v['repair']) for v in out['members'].values())
    n_waive = sum(len(v['waive']) for v in out['members'].values())
    print('PNA members %d, mapped records %d, changed %d, repair %d, waive %d'
          % (len(out['members']),
             sum(len(v['map']) for v in out['members'].values()),
             sum(len(v['changed']) for v in out['members'].values()), n_rep, n_waive))
    for nm, v in sorted(out['members'].items()):
        if v['changed']:
            print('  %-24s %-7s changed %-2d repair %-2d waive %-2d'
                  % (nm, v['strategy'], len(v['changed']), len(v['repair']), len(v['waive'])))
    if args.write:
        with open(OUT_JSON, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('WROTE %s' % OUT_JSON)
    else:
        print('[dry-run] not writing %s' % OUT_JSON)
    print('report -> %s' % OUT_REPORT)


if __name__ == '__main__':
    main()
