# -*- coding: utf-8 -*-
"""CG / 立绘 一致性闸（产物 vs 原版，**按内容**对齐）。

判据（用户 2026-10-19）：
  * 对齐的是**内容**，不是文件名：名字不同但内容实质相同（水印级差异、引用名不同但
    PNA 图层相同）⇒ **不算差异、不纠正**（`tool/imgcmp.same_content`）。
  * 每行在屏的 CG / 立绘 / 背景，必须能与原版对应行的同类图像**一一配上**；配不上的
    才是差异（多 / 缺）。
  * 差异按**根因行**（本槽自带显示/清屏与原版不同）归类，避免把「上一行没清屏」的连锁
    影响重复计成几百条。

退出码：1 = 存在内容差异。明细写 tmp/perf_consistency_check.{md,json}。
"""
import collections
import json
import os
import re
import sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tool import arcbuild, imgcmp, perfsync, paths, ws2, ws2dis  # noqa: E402

CG_RX = re.compile(
    r'^(?:(?:CSEV|AFT|BEF|HOT|HUS|KAN|NOV|AGS|KOT|AMA|HUT)_\d{2,4}_\d{2,4}[A-Z]?'
    r'|FDSDEV\d{2,4}_\d{2,4}[A-Z]?)\.PNG$', re.I)
IMG_RX = re.compile(r'\.(PNG|PNA)$', re.I)


def members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def rows(raw, fmt):
    return perfsync.perf_rows(ws2dis.disassemble(ws2.decode(raw), formats=fmt)[0])


def cat(name):
    u = (name or '').upper()
    if not IMG_RX.search(u):
        return None
    if u.endswith('.PNA'):
        return 'sprite'
    u2 = re.sub(r'_SC(\.PNG)$', r'\1', u)      # 水印变体 `_SC` 归到同一类
    return 'cg' if CG_RX.match(u2) else 'bg'


def imgs_of(eff):
    return [(k, v) for k, v in eff.items() if perfsync._is_img_chan(k) and cat(v)]


class Resolver:
    def __init__(self):
        self.idx = {}

    def load(self, root):
        if not os.path.isdir(root):
            return
        for fn in sorted(os.listdir(root)):
            p = os.path.join(root, fn)
            if not (os.path.isfile(p) and fn.lower().endswith('.arc')):
                continue
            for nb, d in arcbuild.read_raw(p):
                n = nb.decode('utf-16le', 'replace')
                if IMG_RX.search(n):
                    self.idx.setdefault(n.upper(), (n, d))

    def get(self, name):
        return self.idx.get((name or '').upper())


def match(plist, olist, res, notes):
    """名字集合比 + 差集内容等价豁免。

    返回 (pe, om)：仍未被内容等价豁免掉的 (chan,name) 列表。
    """
    def key(item):
        c, n = item
        return cat(n), perfsync.norm_sprite(n).upper()

    pset, oset = set(), set()
    for it in plist:
        pset.add(key(it))
    for it in olist:
        oset.add(key(it))
    ponly = [it for it in plist if key(it) not in oset]
    oonly = [it for it in olist if key(it) not in pset]
    used = set()
    pe = []
    for c, n in ponly:
        hit = None
        for j, (c2, n2) in enumerate(oonly):
            if j in used or cat(n) != cat(n2):
                continue
            # CG 身份按**名字**认定：不同编号就是不同 CG（即使像素接近也不能互相豁免；
            # 用户 2026-10-19 明确 KAN_01_006S ≠ KAN_01_004S）。仅 `_SC` 水印变体视为同名。
            if cat(n) == 'cg':
                b1 = re.sub(r'_SC(\.PNG)$', r'\1', n.upper())
                b2 = re.sub(r'_SC(\.PNG)$', r'\1', n2.upper())
                if b1 != b2:
                    continue
            a, b = res.get(n), res.get(n2)
            if a is None or b is None:
                continue
            ok, why = imgcmp.same_content(a[0], a[1], b[0], b[1])
            if ok:
                hit = (j, n2, why)
                break
        if hit:
            used.add(hit[0])
            notes.append('%s ≡ %s（%s）' % (n, hit[1], hit[2]))
        else:
            pe.append((c, n))
    om = [x for j, x in enumerate(oonly) if j not in used]
    return pe, om


def lcs(a, b):
    sm = SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for blk in sm.get_matching_blocks():
        if blk.size:
            out.extend((blk.a + k, blk.b + k) for k in range(blk.size))
    return out


def align(sr, orr, orig_deleted=frozenset()):
    """Steam 槽 → 原版行（语音锚点 + 等长缺口内插）。

    `orig_deleted`：**原版有、Steam 整行删去**的行号（`resource/orig_deleted.json`）。
    这些行在原版侧不存在对应 Steam 格，必须先剔除再做内插——否则缺口两侧等长时，
    内插会把后续每个 Steam 槽整体映射错 1 行（BEF_005 O#1116 的实测假阳性），
    进而诱导「修」出一条错误的演出处置。
    """
    kept = [i for i in range(len(orr)) if i not in orig_deleted]
    sv = [i for i, r in enumerate(sr) if r['own'].get('voice')]
    ov = [k for k, i in enumerate(kept) if orr[i]['own'].get('voice')]
    anchors = [(sv[a], kept[ov[b]]) for a, b in lcs(
        [tuple(sr[i]['own']['voice']) for i in sv],
        [tuple(orr[kept[k]]['own']['voice']) for k in ov])]
    s2o = {s: o for s, o in anchors}
    # 内插在 **kept 序**里做（原版侧下标是 kept 的位置，不是原版行号）
    kpos = {i: k for k, i in enumerate(kept)}
    bnds = [(-1, -1)] + [(s, kpos[o]) for s, o in anchors] + [(len(sr), len(kept))]
    for (s0, o0), (s1, o1) in zip(bnds, bnds[1:]):
        if s1 - s0 == o1 - o0:
            for k in range(1, s1 - s0):
                s2o[s0 + k] = kept[o0 + k]
    return s2o


def main():
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    od_path = os.path.join(ROOT, 'resource', 'orig_deleted.json')
    orig_deleted = {}
    if os.path.exists(od_path):
        orig_deleted = json.load(open(od_path, encoding='utf-8')).get('scripts') or {}
    af_path = os.path.join(ROOT, 'resource', 'align_fixes.json')
    align_fixes = {}
    if os.path.exists(af_path):
        align_fixes = json.load(open(af_path, encoding='utf-8')).get('fixes') or {}
    pw_path = os.path.join(ROOT, 'resource', 'perf_waivers.json')
    slot_waivers = {}
    if os.path.exists(pw_path):
        for w in json.load(open(pw_path, encoding='utf-8')).get('slots') or []:
            slot_waivers[(w['script'], int(w['slot']))] = w
    anim_clears = json.load(open(os.path.join(ROOT, 'resource', 'anim_exit_clears.json'), encoding='utf-8'))
    prod = members(os.path.join(ROOT, 'asset', 'Rio.arc'))
    steam = members(os.path.join(ROOT, 'backup', 'Rio.arc'))
    orig = members(os.path.join(paths.orig_dir(), 'Rio.arc'))

    res = Resolver()
    res.load(os.path.join(ROOT, 'asset'))
    res.load(paths.orig_dir())
    res.load(os.path.join(ROOT, 'backup'))

    stat = collections.Counter()
    root, waived = [], []
    for sc, p in sorted(plan['scripts'].items()):
        of, sf = p.get('orig_file'), p.get('steam_file') or p.get('target_member')
        if not of or of not in orig or sf not in prod:
            continue
        pr = rows(prod[sf], ws2dis.FORMATS)
        orr = rows(orig[of], ws2dis.FORMATS_ORIG)
        sr = rows(steam[sf], ws2dis.FORMATS) if sf in steam else []
        s2o = align(sr, orr, frozenset(int(x) for x in (orig_deleted.get(sc) or []))) if sr else {}
        # 人工定案优先（拆行/整行删除/等长缺口里的非线性对应）
        for k, v in (align_fixes.get(sc) or {}).items():
            if v is None:
                s2o.pop(int(k), None)
            else:
                s2o[int(k)] = int(v)
        for i, (src, val) in enumerate([s for s in slots_all[sc]['slots'] if s[0] != 'choice']):
            if i >= len(pr):
                break
            if (sc, i) in slot_waivers:
                w = slot_waivers[(sc, i)]
                stat['waived_slot'] += 1
                waived.append({'script': sc, 'slot': i,
                               'notes': ['%s：%s' % (w.get('kind'), w.get('reason'))]})
                continue
            o = val if src == 'orig' else s2o.get(val)
            if o is None or o >= len(orr):
                stat['unaligned'] += 1
                continue
            # 动画离场清屏兜底（resource/anim_exit_clears.json 人工定案）：产物在该行起的
            # `37 <通道>` 补清让该通道从产物 eff 消失——原版引擎上同一动画是视觉离场
            # （状态模型看不见），故原版 eff 里该通道的图不算「产物缺失」。
            acl_ge, acl_eq = set(), set()
            for _r, _cs in (anim_clears.get(sc) or {}).items():
                _r = int(_r)
                if o >= _r:
                    acl_ge.update(_cs)
                if o == _r:
                    acl_eq.update(_cs)
            notes = []
            pe, om = match(imgs_of(pr[i]['eff']), imgs_of(orr[o]['eff']), res, notes)
            om = [x for x in om if x[0] not in acl_ge]
            if notes:
                waived.append({'script': sc, 'slot': i, 'notes': notes})
                stat['waived_pairs'] += len(notes)
            if not pe and not om:
                stat['ok'] += 1
                continue
            pe_cg = [x for x in pe if cat(x[1]) == 'cg']
            om_cg = [x for x in om if cat(x[1]) == 'cg']
            pe_st = [x for x in pe if cat(x[1]) == 'sprite']
            om_st = [x for x in om if cat(x[1]) == 'sprite']
            if pe_cg or om_cg:
                stat['cg_diff'] += 1
            if pe_st or om_st:
                stat['st_diff'] += 1
            pd = {(k, perfsync.norm_sprite(v)) for k, v in (pr[i]['own'].get('display') or {}).items()}
            od = {(k, perfsync.norm_sprite(v)) for k, v in (orr[o]['own'].get('display') or {}).items()}
            pcl = set(pr[i]['own'].get('clear') or ()) - acl_eq
            ocl = set(orr[o]['own'].get('clear') or ())
            if pd != od or pcl != ocl:
                stat['root'] += 1
                root.append({'script': sc, 'slot': i, 'src': src, 'steam_row': val, 'orig_row': o,
                             'cg_extra': [x[1] for x in pe_cg], 'cg_missing': [x[1] for x in om_cg],
                             'st_extra': [x[1] for x in pe_st], 'st_missing': [x[1] for x in om_st],
                             'display_extra': sorted('%s=%s' % x for x in pd - od),
                             'display_missing': sorted('%s=%s' % x for x in od - pd),
                             'clear_extra': sorted(pcl - ocl), 'clear_missing': sorted(ocl - pcl)})

    lines = ['# CG / 立绘 一致性闸（产物 vs 原版，按内容）', '',
             '| 项 | 值 |', '|---|---|']
    for k, v in sorted(stat.items()):
        lines.append('| %s | %d |' % (k, v))
    lines += ['', '## 根因行', '',
              '| 脚本 | 槽 | 来源 | Steam 行 | 原版行 | CG 多/缺 | 立绘 多/缺 | 显示 多/缺 | 清屏 多/缺 |',
              '|---|---|---|---|---|---|---|---|---|']
    for r in root:
        lines.append('| %s | %d | %s | %s | %s | %s / %s | %s / %s | %s / %s | %s / %s |' % (
            r['script'], r['slot'], r['src'], r['steam_row'], r['orig_row'],
            ','.join(r['cg_extra']) or '-', ','.join(r['cg_missing']) or '-',
            ','.join(r['st_extra']) or '-', ','.join(r['st_missing']) or '-',
            ','.join(r['display_extra']) or '-', ','.join(r['display_missing']) or '-',
            ','.join(r['clear_extra']) or '-', ','.join(r['clear_missing']) or '-'))
    if waived:
        lines += ['', '## 内容等价（名字不同、内容相同 ⇒ 不纠正）', '']
        for w in waived[:80]:
            lines.append('- %s 槽 %d：%s' % (w['script'], w['slot'], '；'.join(w['notes'])))
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with open(os.path.join(ROOT, 'tmp', 'perf_consistency_check.md'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    with open(os.path.join(ROOT, 'tmp', 'perf_consistency_check.json'), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(root, fh, ensure_ascii=False, indent=1)
        fh.write('\n')

    print('一致性：对齐 %d 槽，内容一致 %d；CG 差异 %d 行、立绘差异 %d 行；根因 %d；内容等价豁免 %d 对'
          % (stat['ok'] + stat['cg_diff'] + stat['st_diff'], stat['ok'],
             stat['cg_diff'], stat['st_diff'], len(root), stat['waived_pairs']))
    print('报告 tmp/perf_consistency_check.md')
    return 1 if root else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
