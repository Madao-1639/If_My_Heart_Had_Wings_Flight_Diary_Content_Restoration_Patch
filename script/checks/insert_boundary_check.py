# -*- coding: utf-8 -*-
"""插入边界状态闸（产物 vs 原版，两方向 HARD）。

判据（移植姊妹作 V-11 的「对齐状态」口径，2026-10-25 定案）：
  * 内容层切换点（插入块入口、`perf_sync` replace/drop 站点入口）的**在屏状态**必须
    与原版对应点一致——凡「混合」（还原内容与宿主残留或缺口同屏）都是缺陷，不需另证；
    遮挡/层序关系未必肉眼可见，也不该成为判据。
  * 写盘器的状态规范化（`tool/writer.py::align_state`）只发「清」；**缺失/取值不同**
    必须能被本闸看见（HARD），归 `perf_sync` / `perf_sync_manual` 入库表处置。
  * 对比按**帧身份**归一：`norm_sprite`（Steam `ST_*` → 原版角色码）＋ `_SC` 水印变体
    ＋同编号 `S`/`B` 同帧（姊妹作 V-11 守卫①：只用于判方向，不构成保留理由）。
退出码：1 = 存在边界状态差。明细写 tmp/insert_boundary_check.md。
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, perfsync, paths, variants, ws2, ws2conv, ws2dis  # noqa: E402

IMG = perfsync._is_img_chan


def frame(name):
    """帧身份：norm_sprite ＋ 去 `_SC` 水印 ＋ 去同编号 S/B 后缀（大写）。"""
    if not name:
        return name
    n = perfsync.norm_sprite(name).upper()
    n = re.sub(r'_SC(\.PNG)$', r'\1', n)
    return re.sub(r'([0-9A-Z])[SB]\.PNG$', r'\1.PNG', n)


def diff_states(a, b):
    """两个在屏状态 → {通道: (产物值, 原版值)}（帧身份不同的图像通道）。"""
    out = {}
    for c in sorted(set(a) | set(b)):
        if not IMG(c):
            continue
        va, vb = frame(a.get(c)), frame(b.get(c))
        if va == vb:
            continue
        out[c] = (a.get(c), b.get(c))
    return out


def main():
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    orig_fmts = ws2conv.load_orig_formats(paths.orig_dir())
    prod = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(os.path.join(ROOT, 'asset', 'Rio.arc'))}
    orig = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(os.path.join(paths.orig_dir(), 'Rio.arc'))}

    bad = []
    stat = collections.Counter()
    for sc, p in sorted(plan['scripts'].items()):
        if p['kind'] != 'host':
            continue
        has_boundary = p.get('inserts') or p.get('perf_sync')
        if not has_boundary:
            continue
        pin, ok = ws2dis.disassemble(ws2.decode(prod[p['steam_file']]))
        assert ok, '%s 产物线性解析不自洽' % sc
        slots = [tuple(x) for x in slots_all[sc]['slots']]
        pstates, _ = perfsync.row_setters(pin)
        # 产物槽表里非 choice 槽与 pstates 一一对应（variant 槽也是 0x14：变体共存的
        # 提示句 / %P 清框行，见 resource/variant_routes.json）
        pi, k = {}, 0
        for i, s in enumerate(slots):
            if s[0] != 'vchoice':   # choice/vchoice 是 0f 条目槽，不是 0x14
                pi[i] = k
                k += 1
        oinstrs, _t = ws2conv.parse(ws2.decode(orig[p['orig_file']]), orig_fmts)
        ostates, _ = perfsync.row_setters(oinstrs)

        def penter(ki):
            return dict(pstates[pi[ki - 1]]) if ki > 0 else {}

        # 变体 choice：站点入口状态按所在区分层——
        #   分支 A 区间（< pp2 槽序）      ⇒ 原版语义，按前一行（现有逻辑）；
        #   分支 B 区间（pp2 后、汇合槽前）⇒ Steam 语义，产物该区间是 Steam 原字节，
        #                                    由 variant_route_check 的逐指令等值把守，跳过；
        #   汇合槽及之后                   ⇒ 共享内容，入口状态取「分支 A（原版）终态」
        #                                    （= ('variant','pp2') 前最后一个 0x14 行）。
        pp2_i = next((i for i, s in enumerate(slots) if s == ('variant', 'pp2')), None)

        def penter_station(ki):
            # pp2 之后（分支 B 区间 + 汇合后共享区）一律跳过：分支 B = Steam 原字节
            # （variant_route_check 逐指令等值把守）；汇合后的入口状态两路径必然不同
            #（分支终态差异是变体设计使然，非还原缺陷），两路径各自的入口正确性
            # 由「分支体 = 原字节」结构性保证。
            if pp2_i is not None and ki >= pp2_i:
                return None
            return penter(ki)

        for a, r0, r1 in p.get('inserts') or []:
            k0 = next(i for i, s in enumerate(slots) if s == ('orig', r0))
            want = dict(ostates[r0 - 1]) if r0 > 0 else {}
            d = diff_states(penter(k0), want)
            stat['insert'] += 1
            if d:
                stat['insert_bad'] += 1
                bad.append((sc, '插入块 r%d-..%d（锚 %d）入口' % (r0, r1, a), d))
        for sl, spec in sorted((p.get('perf_sync') or {}).items(), key=lambda kv: int(kv[0])):
            sl = int(sl)
            if spec.get('mode', 'drop') != 'replace':
                continue
            r = spec['orig_row']
            ki = next((i for i, s in enumerate(slots) if s == ('steam', sl)), None)
            if ki is None:
                bad.append((sc, 'replace 槽 %d 不在产物槽表' % sl, {'?': ('?', '?')}))
                stat['site_bad'] += 1
                continue
            want = dict(ostates[r - 1]) if r > 0 else {}
            _st = penter_station(ki)
            if _st is None:
                stat['site_variant_body'] += 1
                continue
            d = diff_states(_st, want)
            stat['site'] += 1
            if d:
                stat['site_bad'] += 1
                bad.append((sc, 'replace 槽 %d（原版行 %d）入口' % (sl, r), d))

    with open(os.path.join(ROOT, 'tmp', 'insert_boundary_check.md'), 'w', encoding='utf-8') as fh:
        for sc, where, d in bad:
            fh.write('- **%s** %s\n' % (sc, where))
            for c, (vp, vo) in sorted(d.items()):
                fh.write('  - `%s`: 产物=%r 原版=%r\n' % (c, vp, vo))
        if not bad:
            fh.write('全部边界在屏状态与原版一致。\n')
    print('插入边界：块 %d（差 %d）、replace 站点 %d（差 %d）'
          % (stat['insert'], stat['insert_bad'], stat['site'], stat['site_bad']))
    if bad:
        print('明细: tmp/insert_boundary_check.md')
        sys.exit(1)


if __name__ == '__main__':
    main()
