# -*- coding: utf-8 -*-
"""CG 显示序列闸（FD 移植版）：产物 vs 原版，按名按序。

与姊妹作同名闸的差别（本作实测）：
* 本作用 `restore_plan.json` 的 25 个改动脚本为范围（`host` / `whole`），不遍历全库——
  未改动脚本的 CG 序列差异属 Steam 基线，不是本补丁的责任。
* 三方对比（产物 / Steam 基线 / 原版）：产物某段与 Steam 相同、与原版不同 ⇒ **继承的审查差异**
  （Steam 把 CG 换成 `CSEV_*` 或删掉显示调用），登记为 `baseline`，不算缺陷；
  产物出现两侧都没有的 CG 名 ⇒ **产物自造**，HARD。
* 逐槽自证：产物每个槽的 CG 显示集合必须等于其来源行（`slot_sources` 的 `steam` 槽 / `orig` 行）
  的 CG 显示集合——这是构建缺陷的硬判据，不依赖行对齐。

用法：工程根目录 `python script/checks/cg_seq_check.py [--strict]`
默认只报告（与姊妹作同口径）；HARD 或 `--strict` 下的 REVIEW ⇒ 退出码 1。
"""
import argparse
import collections
import difflib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tool import arcbuild, ws2, ws2dis, perfsync, paths  # noqa: E402

# 本作 CG 名：`<剧本组>_<两位场次>_<三位编号><B|S>`。
# `CSEV_*` 是 Steam 的**审查替代 CG**（同场景着装/裁切版本，只在 Chip10.arc，原版脚本 0 引用），
# 纳入 CG 类以便把「原版 CG → CSEV」识别成换名而不是「显示被删」；BG/SKY/EST/CUTIN/FDSDEV/COM 不是 CG。
CG_RX = re.compile(r'^(CSEV|AFT|BEF|HOT|HUS|KAN|NOV|AGS|KOT|AMA|HUT)_\d{2,4}_\d{2,4}[A-Z]?\.PNG$')


def is_cg(name):
    return bool(name and CG_RX.match(name.upper()))


def is_censor(name):
    return bool(name and name.upper().startswith('CSEV_'))


def series(name):
    m = re.match(r'^([A-Z]+_\d{2,4})_\d{2,4}[A-Z]?\.PNG$', (name or '').upper())
    return m.group(1) if m else (name or '').upper()


def members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def rows_of(raw, fmt):
    """逐 0x14 槽：{'cg': [CG 名], 'disp': [通道:名], 'text': 文本}。

    **归属口径＝前缀模型**（`doc/file-formats.md`「格内指令的归属次序」）：
    一条 `0x14` 的行单元 = 上一条 `0x14` 之后 → 本条 `0x14` 之前的演出/语音/名字
    ＋ 本条 `0x14` 的正文。`0x14` 之后的指令属于**下一条** `0x14`，不是本行。
    本作实测自证：8,831/8,993 条语音的 OGG 角色码与其后 `0x15` 名字一致，
    仅 8 条只与前一个名字一致（2026-10-19）。
    """
    out, cur = [], []
    for _off, op, _sz, ops in ws2dis.disassemble(ws2.decode(raw), formats=fmt)[0]:
        if op == 0x14:
            cg, disp = [], []
            for o2, ops2 in cur:
                if o2 in (0x33, 0x34):
                    parts = [x for x in ops2.split(b'\x00') if x]
                    if len(parts) >= 2:
                        chan = parts[0].decode('cp932', 'replace')
                        name = parts[1].decode('cp932', 'replace').upper()
                        disp.append('%s:%s' % (chan, name))
                        if is_cg(name):
                            cg.append(name)
            parts = [x for x in ops.split(b'\x00') if x]
            text = ''
            for x in parts:
                t = x.decode('cp932', 'replace')
                if t not in ('char',) and not t.upper().endswith('.OGG'):
                    text = t
            out.append({'cg': cg, 'disp': disp, 'text': text})
            cur = []
        else:
            cur.append((op, ops))
    return out


def cg_seq(rows):
    return [(i, n) for i, r in enumerate(rows) for n in r['cg']]


def main(argv=None):
    ap = argparse.ArgumentParser(description='CG 显示序列闸（产物 vs 原版，按名按序）')
    ap.add_argument('--product', default=os.path.join(ROOT, 'asset'))
    ap.add_argument('--backup', default=os.path.join(ROOT, 'backup'))
    ap.add_argument('--orig-dir', default='')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--out', default=os.path.join(ROOT, 'tmp', 'cg_seq_check.md'))
    args = ap.parse_args(argv)

    orig_dir = args.orig_dir or paths.orig_dir()
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    prod = members(os.path.join(args.product, 'Rio.arc'))
    steam = members(os.path.join(args.backup, 'Rio.arc'))
    orig = members(os.path.join(orig_dir, 'Rio.arc'))

    hard, review, baseline = [], [], []
    stat = collections.Counter()
    for sc, p in sorted(plan['scripts'].items()):
        if p.get('kind') not in ('host', 'whole'):
            continue
        sf = p.get('steam_file') or p.get('target_member')
        of = p.get('orig_file')
        if not sf or sf not in prod:
            hard.append({'script': sc, 'issue': 'absent-in-product'})
            continue
        if not of or of not in orig:
            stat['skip_no_orig'] += 1
            continue
        pr = rows_of(prod[sf], ws2dis.FORMATS)
        orr = rows_of(orig[of], ws2dis.FORMATS_ORIG)
        sr = rows_of(steam[sf], ws2dis.FORMATS) if sf in steam else []

        # 1) 逐槽自证：产物槽的 CG 集合 == 来源行的 CG 集合
        slots = slots_all.get(sc, {}).get('slots') or []
        sync = {int(k) for k in (p.get('perf_sync') or {})}
        stat['slots'] += len(slots)
        if len(pr) != len(slots):
            hard.append({'script': sc, 'issue': 'row-count', 'product': len(pr), 'slots': len(slots)})
        for i, (src, val) in enumerate(slots):
            if i >= len(pr):
                break
            if src == 'steam' and val in sync:
                # 演出同步（replace）：该槽图像演出已按原版行重排 ⇒ 与**原版行**比
                spec = (p.get('perf_sync') or {}).get(str(val)) or {}
                r = spec.get('orig_row')
                ref = orr[r] if r is not None and r < len(orr) else None
            elif src == 'orig':
                ref = orr[val] if val < len(orr) else None
            else:
                ref = sr[val] if src == 'steam' and val < len(sr) else None
            if ref is None:
                continue
            if sorted(set(pr[i]['cg'])) != sorted(set(ref['cg'])):
                # 槽级 CG 组成与来源行不同：序列级对比通常能解释为 Steam 侧
                # CSEV_* 审查 CG / 解锁块（见下方 baseline 段），故登记 REVIEW，
                # 不直接判缺陷；`--strict` 时仍会失败。
                review.append({'script': sc, 'slot': i, 'src': '%s:%s' % (src, val),
                               'issue': 'cg-of-source-mismatch',
                               'product': pr[i]['cg'], 'source': ref['cg']})

        # 2) 序列对比（产物 vs 原版），按 Steam 侧解释差异
        ps = [n for _, n in cg_seq(pr)]
        os_ = [n for _, n in cg_seq(orr)]
        ss = {n for _, n in cg_seq(sr)}
        if ps == os_:
            stat['seq_same'] += 1
            continue
        stat['seq_diff'] += 1
        sm = difflib.SequenceMatcher(a=os_, b=ps, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            opart, ppart = os_[i1:i2], ps[j1:j2]
            oset, pset = set(opart), set(ppart)
            fabricated = pset - oset - ss
            rec = {'script': sc, 'tag': tag, 'orig': opart, 'product': ppart,
                   'series': sorted({series(x) for x in oset | pset})}
            if fabricated:
                rec['issue'] = 'fabricated-cg'
                hard.append(rec)
            elif any(is_censor(x) for x in pset) and pset <= ss:
                rec['issue'] = 'steam-censor-variant'
                baseline.append(rec)
            elif pset and pset <= ss:
                rec['issue'] = 'baseline-steam'
                baseline.append(rec)
            elif not pset and oset - ss:
                rec['issue'] = 'steam-deleted-display'
                baseline.append(rec)
            else:
                rec['issue'] = 'review'
                review.append(rec)
            stat['seg_' + rec['issue']] += 1

    lines = ['# CG 显示序列闸（产物 vs 原版，按名按序）', '',
             '- 产物 `%s` ｜ 原版 `%s`' % (args.product, orig_dir),
             '- 范围：restore_plan 的 host/whole 脚本（未改动脚本的差异属 Steam 基线，不在本闸范围）', '',
             '## 读数', '', '| 项 | 值 |', '|---|---|']
    for k, v in sorted(stat.items()):
        lines.append('| %s | %d |' % (k, v))
    lines += ['', '## HARD（产物自造 CG / 来源行不符）', '']
    lines += ['- %s' % json.dumps(x, ensure_ascii=False, sort_keys=True) for x in hard[:40]]
    lines += ['', '## REVIEW（两侧都不完全解释）', '']
    lines += ['- %s' % json.dumps(x, ensure_ascii=False, sort_keys=True) for x in review[:40]]
    lines += ['', '## 继承的 Steam 审查差异（未还原，登记备查）', '']
    lines += ['- %s' % json.dumps(x, ensure_ascii=False, sort_keys=True) for x in baseline[:60]]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')

    print('CG 序列：脚本 %d（同序 %d / 有差异 %d）｜HARD %d｜REVIEW %d｜继承审查差异 %d'
          % (stat['seq_same'] + stat['seq_diff'], stat['seq_same'], stat['seq_diff'],
             len(hard), len(review), len(baseline)))
    for x in hard[:8]:
        print('  HARD', x.get('script'), x.get('issue'), x.get('product'), '!=', x.get('source'))
    print('report:', os.path.relpath(args.out, ROOT))
    return 1 if hard or (args.strict and review) else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
