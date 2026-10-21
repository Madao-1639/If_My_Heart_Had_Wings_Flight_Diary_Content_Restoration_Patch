# -*- coding: utf-8 -*-
"""资源配对正确性闸：还原块引用的素材是否都能在交付面找到。

判据（`doc/acceptance-criteria.md`「资源配对正确性」）
---------------------------------------------------
还原块（`resource/restore_plan.json` 的 `inserts`；整脚本还原取全脚本）**与演出同步
`replace` 的整段搬运区间**（`perf_sync` 的原版行区间）里每一条 `0x33`/`0x34`（显示）、
`0x28`（语音体）、`0x1e`（BGM）引用的资源名，都必须在**交付面**存在。交付面 =
`asset/`（相对 `backup/` 有差异的归档，取优先）+ `backup/`（其余沿用玩家目录里
Steam 自带那份）。

`replace` 区间必须一起扫：该模式搬的是**原版整段演出**（含原版 SE / 遮罩 / 特效名），
只扫 `inserts` 会漏掉这批新引用（`SUB-TITLE_*`、`EFMSK_*` 一类）。

缺口有两种，必须分开报：
* **归档内缺成员** —— 该资源名在 Steam 与 `asset/` 里都不存在，但在原版归档里有
  ⇒ **L4 素材补齐的范围漏了**（需把该归档纳入并集）。
* **两版都缺** —— 原版也没有 ⇒ 引用名有误或该资源另有来源（`RIO/` 裸目录等）。

用法：`python script/checks/restore_asset_coverage.py`
"""
import collections
import json
import os
import re
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

from tool import arcbuild, paths, ws2, ws2conv, ws2fmt  # noqa: E402

NAME = re.compile(rb'[A-Za-z0-9_\-\.]{3,}\.(?:PNG|PNA|OGG|BMP|JPG|WAV|FX)\Z', re.I)


def instr_names(ins, lo, hi):
    """指令区间内引用的资源名（大写）。"""
    out = []
    for j in range(lo, hi):
        op, ops = ins[j]
        if op not in (0x33, 0x34, 0x28, 0x2e, 0x1e):
            continue
        for seg in ops.split(b'\x00'):
            if NAME.match(seg):
                out.append(seg.decode('ascii').upper())
    return out


def archive_index(root, only=None):
    """{归档名: set(成员名大写)}。"""
    idx = {}
    for fn in sorted(os.listdir(root)):
        if not fn.lower().endswith('.arc'):
            continue
        if only and fn.lower() not in only:
            continue
        try:
            idx[fn.lower()] = {nb.decode('utf-16le').upper() for nb, _ in
                               arcbuild.read_raw(os.path.join(root, fn))}
        except Exception as e:
            print('  ! 读不动 %s: %s' % (fn, e))
    return idx


def main():
    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    steam_idx = archive_index(paths.STEAM)
    asset_dir = os.path.join(ROOT, 'asset')
    asset_idx = archive_index(asset_dir) if os.path.isdir(asset_dir) else {}
    orig_idx = archive_index(paths.orig_dir())

    deliver = {}
    for k, v in steam_idx.items():
        deliver.setdefault(k, set()).update(v)
    for k, v in asset_idx.items():
        deliver.setdefault(k, set()).update(v)
    have = set()
    for s in deliver.values():
        have |= s
    orig_all = set()
    for s in orig_idx.values():
        orig_all |= s

    fmts = ws2conv.load_orig_formats(paths.orig_dir())
    orig_rio = {nb.decode('utf-16le'): d for nb, d in
                arcbuild.read_raw(os.path.join(paths.orig_dir(), 'Rio.arc'))}

    refs = collections.Counter()
    for sc, p in sorted(plan['scripts'].items()):
        raw = ws2.decode(orig_rio[p['orig_file']])
        ins, _t = ws2conv.parse(raw, fmts)
        offs, q = [], 0
        for op, ops in ins:
            offs.append(q)
            q += 1 + len(ops)
        o14 = [j for j, (op, _) in enumerate(ins) if op == 0x14]
        spans = []
        if p['kind'] == 'whole':
            spans.append((0, len(ins)))
        else:
            for _a, r0, r1 in p['inserts']:
                i0 = o14[r0 - 1] + 1 if r0 > 0 else 0
                i1 = o14[r1] + 1
                spans.append((i0, i1))
            for _slot, spec in sorted((p.get('perf_sync') or {}).items()):
                if spec.get('mode') != 'replace':
                    continue
                r = spec['orig_row']
                i0 = o14[r - 1] + 1 if r > 0 else 0
                spans.append((i0, o14[r]))
        for lo, hi in spans:
            for n in instr_names(ins, lo, hi):
                refs[n] += 1

    miss_asset = sorted(n for n in refs if n not in have and n in orig_all)
    miss_both = sorted(n for n in refs if n not in have and n not in orig_all)
    print('还原块引用资源名 %d 个（去重）' % len(refs))
    print('交付面（asset/ ∪ backup/）已覆盖 %d 个' % len([n for n in refs if n in have]))
    print()
    print('❌ 归档内缺成员（原版有、交付面没有）%d 个 —— L4 补齐范围漏了：' % len(miss_asset))
    for n in miss_asset:
        where = sorted(a for a, s in orig_idx.items() if n in s)
        print('   %-28s 原版位于 %s（引用 %d 次）' % (n, where, refs[n]))
    print()
    print('⚠️ 两版都没有 %d 个（引用名有误 / 另有来源）：' % len(miss_both))
    for n in miss_both[:20]:
        print('   %-28s（引用 %d 次）' % (n, refs[n]))
    return 1 if (miss_asset or miss_both) else 0


if __name__ == '__main__':
    sys.exit(main())
