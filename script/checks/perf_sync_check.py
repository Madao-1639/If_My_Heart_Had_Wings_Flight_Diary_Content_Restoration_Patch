# -*- coding: utf-8 -*-
"""演出同步闸（FD 移植版）：产物 vs 来源行，逐槽对账。

本作的槽位来源是**权威表** `resource/slot_sources.json`（计划器产出）：
每个产物槽 → `['steam', 旧槽]` 或 `['orig', 原版行]`。因此本闸**不读取承载图**
（`resource/carrier_map.json` 保留为空表，仅维持与姊妹作的路径/接口同名）：

* **HARD**：产物槽自带的演出（语音 / 显示 / 清屏 / SE / BGM）≠ 其来源行的同一组演出
  ——构建把内容搬错/搬丢；
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

from tool import arcbuild, ws2, ws2dis, perfsync, paths  # noqa: E402


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
    prod = members(os.path.join(args.product, 'Rio.arc'))
    steam = members(os.path.join(args.backup, 'Rio.arc'))
    orig = members(os.path.join(orig_dir, 'Rio.arc'))

    hard, review = [], []
    stat = collections.Counter()
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
        slots = slots_all.get(sc, {}).get('slots') or []
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
                stat['perf_sync_skip'] += 1
                continue
            ps, rs = _own_sig(pr[i]['own']), _own_sig(ref['own'])
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
