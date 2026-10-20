# -*- coding: utf-8 -*-
"""PNA 层内修复（画面还原）：把同名声望立绘里被 Steam 改画的子图换回原版。

输入（只读）
------------
* `resource/pna_id_map.json` 的 `repair` 清单（逐成员、逐记录）；该清单已由
  `script/build/build_pna_id_map.py` 做「不得被 Steam 新增段/未还原段复用」的引用核对；
* `backup/Graphic.arc`（Steam 基线）与 `asset/Graphic.arc`（若 L3 已写盘则以其为底）；
* 原版发行目录的 `Graphic.arc`。

动作
----
**只替换 `repair` 记录的子图字节与 box**，不改：
  * PNA 记录数、记录顺序、`layer_id`、`u0`、画布尺寸；
  * 脚本（Steam 侧记录号本就对着 Steam 记录表；原版来源块的记录号由
    `tool/writer` 之前的 `build_patch.prep_orig` 按 `map` 换算）。

因此层内修复**不移动任何记录号**，Steam 侧既有调用点不受影响。

产出：`asset/Graphic.arc`（相对 backup 有差异才写；幂等，重复运行内容一致）。
报告：`tmp/pna_repair_report.txt`。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, paths, pna  # noqa: E402

MAP_PATH = os.path.join(ROOT, 'resource', 'pna_id_map.json')
ARCH = 'Graphic.arc'


def repair(data, orig, repairs):
    """PNA 字节 → 修复后字节；返回 (new_bytes, applied)。"""
    p = pna.load(data)
    q = pna.load(orig)
    applied = 0
    for r in repairs:
        si, oi = int(r['steam']), int(r['orig'])
        if not (0 <= si < len(p['entries'])) or not (0 <= oi < len(q['entries'])):
            raise SystemExit('repair 记录越界 steam=%d orig=%d' % (si, oi))
        if q['images'][oi] is None:
            raise SystemExit('原版记录 %d 无子图，不能修复' % oi)
        p['images'][si] = q['images'][oi]
        e, oe = p['entries'][si], q['entries'][oi]
        e[2], e[3], e[4], e[5] = oe[2], oe[3], oe[4], oe[5]
        e[9] = oe[9]
        applied += 1
    return pna.dump(p), applied


def canonicalize(directory):
    """把目录里大小写不同的同名归档规范成 `ARCH` 的拼写（Windows 保留首次拼写）。"""
    if not os.path.isdir(directory):
        return
    for fn in os.listdir(directory):
        if fn.lower() == ARCH.lower() and fn != ARCH:
            tmp = os.path.join(directory, ARCH + '.casefix')
            os.replace(os.path.join(directory, fn), tmp)
            os.replace(tmp, os.path.join(directory, ARCH))


def main():
    canonicalize(os.path.join(ROOT, 'asset'))
    mp = json.load(open(MAP_PATH, encoding='utf-8'))
    members = mp.get('members') or {}
    asset = os.path.join(ROOT, 'asset', ARCH)
    base_path = asset if os.path.exists(asset) else os.path.join(paths.STEAM, ARCH)
    if not os.path.exists(base_path):
        raise SystemExit('缺底档 %s' % base_path)
    steam_members = [(nb, d) for nb, d in arcbuild.read_raw(base_path)]
    orig_members = {nb.decode('utf-16le', 'replace').upper(): d
                    for nb, d in arcbuild.read_raw(os.path.join(paths.orig_dir(), ARCH))}
    backup_members = {nb.decode('utf-16le', 'replace').upper(): d
                      for nb, d in arcbuild.read_raw(os.path.join(paths.STEAM, ARCH))}
    idx = {nb.decode('utf-16le', 'replace').upper(): i for i, (nb, _d) in enumerate(steam_members)}

    report, changed = [], False
    for name, rec in sorted(members.items()):
        reps = rec.get('repair') or []
        if not reps:
            continue
        key = name.upper()
        if key not in idx:
            raise SystemExit('asset 缺成员 %s' % name)
        if key not in orig_members:
            raise SystemExit('原版缺成员 %s' % name)
        i = idx[key]
        old = steam_members[i][1]
        new, n = repair(old, orig_members[key], reps)
        if new != old:
            steam_members[i] = (steam_members[i][0], new)
            changed = True
        # 回读校验
        p = pna.load(new)
        q = pna.load(orig_members[key])
        for r in reps:
            si, oi = int(r['steam']), int(r['orig'])
            assert p['images'][si] == q['images'][oi], '%s 记录 %d 子图回读不一致' % (name, si)
            assert p['entries'][si][2:6] == q['entries'][oi][2:6], '%s 记录 %d box 不一致' % (name, si)
        assert p['layer_count'] == pna.load(old)['layer_count'], '%s 记录数变化' % name
        assert (p['canvas_w'], p['canvas_h']) == (pna.load(old)['canvas_w'],
                                                  pna.load(old)['canvas_h']), \
            '%s 画布变化' % name
        report.append('%s: repair %d 记录 %s' % (name, n, sorted(int(r['steam']) for r in reps)))
        print('  %-24s repair %d' % (name, n))

    if not changed:
        print('层内修复：无变化（已满足）')
        return 0
    out = os.path.join(ROOT, 'asset', ARCH)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    arcbuild.write_arc(steam_members, out)
    # Windows 保留首次创建的拼写；build_l3 默认写成大写 `GRAPHIC.arc`。交付名单按
    # backup 的 `Graphic.arc` 匹配 ⇒ 这里把文件名规范回 backup 拼写。
    want = os.path.join(ROOT, 'asset', ARCH)
    if os.path.abspath(out) != os.path.abspath(want):
        tmp = want + '.casefix'
        os.replace(out, tmp)
        os.replace(tmp, want)
        out = want
    cnt, size, _ = arcbuild.verify(out, expect_count=len(steam_members))
    # 非修复成员必须与底档逐字节一致
    have = {nb.decode('utf-16le', 'replace').upper(): d for nb, d in arcbuild.read_raw(out)}
    for k, d in {nb.decode('utf-16le', 'replace').upper(): d
                 for nb, d in arcbuild.read_raw(base_path)}.items():
        if k in {name.upper() for name, rec in members.items() if rec.get('repair')}:
            continue
        assert have[k] == d, '非修复成员被改动：%s' % k
    # 被修复成员在 backup 中必须存在（同名换内容）
    for name, rec in members.items():
        if rec.get('repair'):
            assert name.upper() in backup_members, '%s 不在 Steam 基线' % name
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with open(os.path.join(ROOT, 'tmp', 'pna_repair_report.txt'), 'w',
              encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(report) + '\n')
    print('写出 %s：成员 %d、%d B' % (out, cnt, size))
    print('报告 tmp/pna_repair_report.txt')
    return 0


if __name__ == '__main__':
    sys.exit(main())
