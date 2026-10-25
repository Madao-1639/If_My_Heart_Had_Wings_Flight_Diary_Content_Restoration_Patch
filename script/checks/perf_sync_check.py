# -*- coding: utf-8 -*-
"""演出同步闸（FD 移植版）：产物 vs 来源行，逐槽对账。

本作的槽位来源是**权威表** `resource/slot_sources.json`（计划器产出）：
每个产物槽 → `['steam', 旧槽]` 或 `['orig', 原版行]`。因此本闸**不读取承载图**
（`resource/carrier_map.json` 保留为空表，仅维持与姊妹作的路径/接口同名）：

* **HARD**：产物槽自带的演出（语音 / 显示 / 清屏 / SE / BGM）≠ 其来源行的同一组演出
  ——构建把内容搬错/搬丢；
* **HARD（顺序闸）**：`perf_sync` 的 `replace` 槽，产物该槽的**演出指令序列**（逐条逐序，
  含拖拽 `45`／特效 `47`/`48`/`57`／渐变 `65`／计时 `11`/`12`／图层权重 `09`／音频）
  必须与原版行 r 的演出序列**逐条相同**——顺序本身是演出的一部分，只对齐「在屏图集合」
  会让宿主残留的拖拽/特效作用在已删通道上（动画错乱，见 doc/lessons-learned.md §44）；
* **HARD**：`orig` 来源槽在屏出现**原版与 Steam 两侧都没有的图名**（产物自造）；
* **REVIEW**：`orig` 来源槽与原版行在屏图名集合的其余差异（缺失 / 通道错位）；
* **表闸**：`resource/perf_sync_map.json` 存在时，`drop`/`replace` 条目数须等于
  `restore_plan.gates.perf_sync_*` 之和；本作无此表 ⇒ 跳过（0 条，不判失败）。

用法：`python script/checks/perf_sync_check.py [--orig-dir DIR] [--quiet]`
HARD ⇒ 退出码 1。
"""
import argparse
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tool import arcbuild, ws2, ws2dis, perfsync, paths, writer  # noqa: E402
from tool.ws2conv import load_orig_formats, parse as conv_parse  # noqa: E402


def members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def rows_of(raw, fmt):
    return perfsync.perf_rows(ws2dis.disassemble(ws2.decode(raw), formats=fmt)[0])


def _own_sig(own):
    """槽自带演出的可比值：语音/SE/BGM/清屏按序，显示按通道。"""
    return {
        'voice': tuple(own.get('voice') or ()),
        'se': tuple(own.get('se') or ()),
        'bgm': tuple(own.get('bgm') or ()),
        'clear': tuple(sorted(own.get('clear') or ())),
        'display': dict(own.get('display') or {}),
    }


def _imgs(eff):
    return {v for k, v in eff.items() if perfsync._is_img_chan(k) and v}


SKELETON = writer._PERF_TAKE_STEAM_ONLY | {0x0B, 0x01, 0x02, 0x06, 0x14}


def _is_skeleton(op, ops):
    """骨架/非演出指令（比较时跳过）：状态写入、流程、成就与引擎调用、名字框、别的行正文。"""
    if op in SKELETON:
        return True
    return op == 0x04 and ops.split(b'\x00')[0] != b'LAYER_ORDER'


def _match_from(ins, start, exp):
    """从 `ins[start]` 起按序匹配 `exp`（允许中间跳过骨架指令），返回结束下标或 None。"""
    k, m = start, 0
    n = len(ins)
    while k < n and m < len(exp):
        op, ops = ins[k][1], ins[k][3]
        if _sig(op, ops) == exp[m]:
            k += 1
            m += 1
            continue
        if _is_skeleton(op, ops):
            k += 1
            continue
        return None
    return k if m == len(exp) else None


def replace_order_diff(ins, oins, o14, r, prod_slot):
    """`replace` 槽的顺序闸：产物**该槽前**的演出序列 vs 原版行 r 的演出序列。

    做法：把「原版行 r 的演出序列」按序在产物里匹配（允许跳过骨架指令与别的行正文），
    取**结束位置最靠该槽 `14`** 的那一处，再断言它之后到 `14` 之间只剩骨架指令。
    于是「一条不差、一条不多、顺序不变」三件事一起被断言，同时允许插入的原版行正文与
    骨架指令夹在中间（`perf_sync` 补块排在插入块之后）。

    两侧用产出端同一套判据（`writer.perf_is_presentation` / `writer._perf_replace_zone`）；
    `0x39` 帧号跨版本由 `pna_id_map` 换算，只比通道串。
    """
    idx14 = [k for k, x in enumerate(ins) if x[1] == 0x14]
    if prod_slot >= len(idx14):
        return {'issue': 'product-slot-missing', 'slot': prod_slot}
    target = idx14[prod_slot]
    if r >= len(o14):
        return {'issue': 'orig-row-missing', 'row': r}
    exp = writer.perf_expected_sig(oins, o14, r)
    if not exp:
        return None
    best = None
    first = exp[0]
    for start in range(target):
        if _sig(ins[start][1], ins[start][3]) != first:
            continue
        end = _match_from(ins, start, exp)
        if end is None or end > target:
            continue
        if all(_is_skeleton(ins[k][1], ins[k][3]) for k in range(end, target)):
            best = end
    if best is None:
        return {'issue': 'sequence-not-found', 'expect_len': len(exp),
                'expect': ['%02x %r' % (op, ops[:30]) for op, ops in exp[:4]]}
    extra = ['%02x %r' % (ins[k][1], ins[k][3][:30]) for k in range(best, target)
             if not _is_skeleton(ins[k][1], ins[k][3])]
    if extra:
        return {'issue': 'extra-presentation-after-block', 'extra': extra[:4]}
    return None


def _sig(op, ops):
    """可比值：`0x39` 的帧号列表跨版本会被 `pna_id_map` 换算，只比通道串。"""
    if op == 0x39:
        return (op, ops.split(b'\x00')[0])
    return (op, ops)


def _conv_of(op, ops):
    return writer._conv(op, ops, None)


def main(argv=None):
    ap = argparse.ArgumentParser(description='演出同步闸（产物 vs 来源行）')
    ap.add_argument('--product', default=os.path.join(ROOT, 'asset'))
    ap.add_argument('--backup', default=os.path.join(ROOT, 'backup'))
    ap.add_argument('--orig-dir', default='')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--max-detail', type=int, default=40)
    ap.add_argument('--out', default=os.path.join(ROOT, 'tmp', 'perf_sync_check.md'))
    args = ap.parse_args(argv)

    orig_dir = args.orig_dir or paths.orig_dir()
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    scope = json.load(open(os.path.join(ROOT, 'resource', 'restore_scope.json'), encoding='utf-8'))
    anim_clears = json.load(open(os.path.join(ROOT, 'resource', 'anim_exit_clears.json'), encoding='utf-8'))
    deliver = perfsync.delivery_names(os.path.join(ROOT, 'backup'))
    kept_censored = perfsync.censored_kept_names()
    prod = members(os.path.join(args.product, 'Rio.arc'))
    steam = members(os.path.join(args.backup, 'Rio.arc'))
    orig = members(os.path.join(orig_dir, 'Rio.arc'))

    hard, review = [], []
    prep = {}
    stat = collections.Counter()
    stat['perf_sync_noop'] = 0
    for sc, p in sorted(plan['scripts'].items()):
        if p.get('kind') not in ('host', 'whole'):
            continue
        sync = {int(k) for k in (p.get('perf_sync') or {})}
        sf = p.get('steam_file') or p.get('target_member')
        of = p.get('orig_file')
        if not sf or sf not in prod:
            hard.append({'script': sc, 'issue': 'absent-in-product'})
            continue
        pr = rows_of(prod[sf], ws2dis.FORMATS)
        sr = rows_of(steam[sf], ws2dis.FORMATS) if sf in steam else []
        orr = rows_of(orig[of], ws2dis.FORMATS_ORIG) if of in orig else []
        # 选项条目（'choice'）占 .lng 槽位但不是台词行：行口径只看 0x14 来源槽
        slots = [s for s in (slots_all.get(sc, {}).get('slots') or []) if s[0] != 'choice']
        stat['slots'] += len(slots)
        if len(pr) != len(slots):
            hard.append({'script': sc, 'issue': 'row-count', 'product': len(pr), 'slots': len(slots)})
        orig_imgs = set()
        for r in orr:
            orig_imgs |= _imgs(r['eff'])
        steam_imgs = set()
        for r in sr:
            steam_imgs |= _imgs(r['eff'])
        for i, (src, val) in enumerate(slots):
            if i >= len(pr):
                break
            if src == 'orig':
                ref = orr[val] if val < len(orr) else None
            else:
                ref = sr[val] if val < len(sr) else None
            if ref is None:
                stat['unaligned'] += 1
                continue
            stat['pairs'] += 1
            if src == 'steam' and val in sync:
                spec = (p.get('perf_sync') or {}).get(str(val)) or {}
                if spec.get('mode') == 'replace':
                    # 前置检验（与产出端同一批函数）：判为「本来就对」的站点不改字节、
                    # 因而不跑顺序闸（否则会拿「期望整段替换后的序列」去要求它）。
                    ctx = prep.get(sc)
                    if ctx is None:
                        sinstrs2 = ws2dis.disassemble(ws2.decode(steam[sf]), formats=ws2dis.FORMATS)[0]
                        oins2, _t2 = conv_parse(ws2.decode(orig[of]), load_orig_formats(orig_dir))
                        ctx = {'ins': sinstrs2,
                               's14': [o2 for o2, op2, _s2, _x2 in sinstrs2 if op2 == 0x14],
                               'idx': {x[0]: k2 for k2, x in enumerate(sinstrs2)},
                               'oins': oins2,
                               'o14': [j2 for j2, (op2, _x2) in enumerate(oins2) if op2 == 0x14],
                               'prod': ws2dis.disassemble(ws2.decode(prod[sf]),
                                                          formats=ws2dis.FORMATS)[0]}
                        prep[sc] = ctx
                    s_sig = writer.perf_zone_sig(
                        ctx['ins'], writer._perf_zone(ctx['ins'], ctx['idx'], ctx['s14'], int(val)))
                    o_sig = writer.perf_expected_sig(ctx['oins'], ctx['o14'], spec['orig_row'])
                    noop, why = perfsync.site_noop(s_sig, o_sig, deliver, kept_censored)
                    if noop and not perfsync.scope_text_clean(scope['scripts'].get(sc), int(val)):
                        noop, why = False, 'text-restored'
                    if noop:
                        stat['perf_sync_noop'] += 1
                        continue
                    stat['perf_sync_checked'] += 1
                    diff = replace_order_diff(ctx['prod'], ctx['oins'], ctx['o14'],
                                              spec['orig_row'], i)
                    if diff:
                        stat['hard_order'] += 1
                        hard.append({'script': sc, 'slot': i, 'src': 'steam:%s' % val,
                                     'issue': 'replace-order', 'diff': diff})
                else:
                    stat['perf_sync_skip'] += 1
                continue
            ps, rs = _own_sig(pr[i]['own']), _own_sig(ref['own'])
            # 动画离场清屏兜底（resource/anim_exit_clears.json 人工定案）：产物按表在
            # 该行补的 `37 <通道>` 是 Steam 引擎动画终点不一致的合法补偿，不计 own 差异
            if src == 'orig':
                _tbl = (anim_clears.get(sc) or {}).get(str(val))
                if _tbl:
                    _allowed = set(_tbl)
                    ps['clear'] = tuple(c for c in ps['clear'] if c not in _allowed)
                    rs['clear'] = tuple(c for c in rs['clear'] if c not in _allowed)
            if ps != rs:
                stat['hard_own'] += 1
                diff = {k: [ps[k], rs[k]] for k in ps if ps[k] != rs[k]}
                hard.append({'script': sc, 'slot': i, 'src': '%s:%s' % (src, val),
                             'issue': 'own-mismatch', 'diff': diff})
                continue
            if src == 'orig':
                pe, oe = _imgs(pr[i]['eff']), _imgs(ref['eff'])
                extra = sorted(pe - oe)
                missing = sorted(oe - pe)
                # 真正「产物自造」＝ 原版与 Steam 两侧都没有的图名；Steam 侧有的
                # （CSEV_* 审查 CG / Steam 解锁块）属继承状态，降为 REVIEW。
                fabricated = [x for x in extra if x not in orig_imgs and x not in steam_imgs]
                if fabricated:
                    stat['hard_fabricated'] += 1
                    hard.append({'script': sc, 'slot': i, 'src': 'orig:%d' % val,
                                 'issue': 'fabricated-image', 'extra': fabricated})
                rest = [x for x in extra if x not in fabricated]
                if rest or missing:
                    stat['review'] += 1
                    review.append({'script': sc, 'slot': i, 'src': 'orig:%d' % val,
                                   'extra': rest, 'missing': missing})

    want = got = 0
    pmap = os.path.join(ROOT, 'resource', 'perf_sync_map.json')
    if os.path.exists(pmap):
        pm = json.load(open(pmap, encoding='utf-8'))
        for site in pm.get('sites', []):
            act = site.get('action')
            if act not in ('drop', 'replace'):
                continue
            want += 1
            spec = (plan['scripts'].get(site['script'], {}).get('perf_sync') or {}).get(str(site['slot']))
            if not spec:
                continue
            if act == 'replace' and spec.get('mode') == 'replace' \
                    and int(spec.get('orig_row', -1)) == int(site.get('orig_row', -2)):
                got += 1
            elif act == 'drop' and spec.get('mode') == 'drop':
                got += 1
        if want != got:
            hard.append({'script': '(table)', 'issue': 'perf_sync 名单未逐条落地',
                         'table_sites': want, 'applied_sites': got})
    stat['table_sites'] = want
    stat['applied_sites'] = got

    lines = ['# 演出同步闸（产物 vs 来源行）', '',
             '- 产物 `%s` ｜ 原版 `%s`' % (args.product, orig_dir),
             '- 对齐来源：`resource/slot_sources.json`（本作无承载图，`carrier_map.json` 为空表）', '',
             '## 读数', '', '| 项 | 值 |', '|---|---|']
    for k, v in sorted(stat.items()):
        lines.append('| %s | %d |' % (k, v))
    lines += ['', '## HARD', '']
    lines += ['- %s' % json.dumps(x, ensure_ascii=False, sort_keys=True) for x in hard[:args.max_detail]]
    lines += ['', '## REVIEW（原版有、产物缺 / 通道错位）', '']
    lines += ['- %s' % json.dumps(x, ensure_ascii=False, sort_keys=True) for x in review[:args.max_detail]]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    with open(os.path.join(ROOT, 'tmp', 'perf_sync_check.json'), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump({'hard': hard, 'review': review, 'stat': dict(stat)}, fh, ensure_ascii=False, indent=0)
        fh.write('\n')

    if not args.quiet:
        print('演出同步：pairs %d ; HARD %d ; REVIEW %d ; 名单 %d / 落地 %d'
              % (stat['pairs'], len(hard), len(review), want, got))
        for h in hard[:8]:
            print('  HARD', h.get('script'), h.get('slot'), h.get('issue'))
        print('report:', os.path.relpath(args.out, ROOT))
    return 1 if hard else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
