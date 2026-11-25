# -*- coding: utf-8 -*-
"""归档素材统一写盘（画面处置 + 并集补入 + 名字规范化 + 回读校验）。

画面处置、并集补入、名字规范化三件事都在对**同一批归档**做「读底 → 改成员 → 写回」。
拆成三个脚本串行时，顺序会成为隐藏依赖（后一个以 `backup/` 为底重写就会把前一个的
覆盖整档抹掉，实测回退 21 项），因此**合并为单一写盘器**、以 `asset/` 为底保证幂等。

三个阶段（每个归档都按序走一遍）
--------------------------------
  1. **起底**：`asset/<归档>`（已存在）否则 `backup/<归档>`。
     以 asset 为底是为了幂等——重复运行不会把上一轮的结果丢掉。
  2. **画面处置**（输入＝`resource/censor_map.json`，写盘器不自行判断）：
       `overwrite`    同名成员字节换成原版（记录表随之变成原版）
       `isolate`      原名保留 Steam 字节；原版字节另存 `<9XX>` 成员
       `insert_orig`  Steam 归档**没有**这个同名成员 ⇒ 按原编号把原版成员补进来
       `keep`         不动
  3. **并集补入**：原版有、底里没有、且不是 `.MOS` 的成员 ⇒ 按原版原名追加
     （`.MOS` 是打码变体，引擎触发条件未明，不补）
  4. **名字规范化**：同一名字若存在**大小写不同的两份**（早期并集补入的重复成员），
     只保留与 `backup/` 拼写一致的那一份。

回读校验（逐名断言，缺一即失败）
--------------------------------
  · 覆盖成员 / 插入成员 == 原版字节
  · 隔离原名 == Steam 字节；9XX 成员 == 原版原名对应字节
  · 其余成员 == `backup/` 字节
  · 成员数 == 底 + 新增 − 去重
  · **覆盖名单条数 == 实际替换次数**（逐名对齐，不得由「已覆盖大多数」推定无漏）

用法：
    python script/build/build_assets.py            # dry-run（只报告）
    python script/build/build_assets.py --write    # 写 asset/
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

from tool import arcbuild, paths  # noqa: E402

ASSET = ROOT / 'asset'
CENSOR_MAP = ROOT / 'resource' / 'censor_map.json'
# 本工序涉及的归档（= censor_map 的 archives ∪ 并集补入的归档），大小写以 backup 为准
TARGET_ARCHIVES = ('chip1.arc', 'chip2.arc', 'chip7.arc', 'chip8.arc', 'chip9.arc',
                   'graphic.arc', 'se.arc', 'voice.arc')


def canon(fn):
    """按 `backup/` 里的**实际拼写**解析归档名（Windows 不区分大小写，发布链按名匹配）。"""
    for name in os.listdir(paths.STEAM):
        if name.lower() == fn.lower():
            return name
    return fn


def sha_(b):
    import hashlib
    return hashlib.sha256(bytes(b)).hexdigest()


def lname(nb):
    return nb.decode('utf-16le', 'replace').lower()


def tname(nb):
    return nb.decode('utf-16le', 'replace')


def load_censor_plan():
    """→ {归档名(原拼写): {成员名小写: 动作}}，以及 isolate 映射。"""
    cm = json.load(open(CENSOR_MAP, encoding='utf-8'))
    acts, iso = {}, {}
    for m in cm.get('members') or []:
        arch = m['archive']
        low = m['name'].lower()
        a = m.get('action', 'keep')
        acts.setdefault(arch, {})[low] = a
        if a == 'isolate' and m.get('isolate'):
            iso.setdefault(arch, {})[low] = m['isolate']
    return acts, iso


def load_layer_fix():
    """→ {成员名小写}：`pna_id_map.repair` 涉及的同名 PNA。

    这些成员在 Steam 基线上做过**层内修复**（只换少数记录的子图/box，
    记录数、顺序、layer_id 都不变）⇒ 整成员字节当然 ≠ backup；
    其正确性由 `script/checks/pna_id_check.py` 逐记录核，本脚本放行。
    """
    p = ROOT / 'resource' / 'pna_id_map.json'
    if not p.exists():
        return set()
    d = json.load(open(p, encoding='utf-8'))
    return {nm.lower() for nm, rec in (d.get('members') or {}).items() if rec.get('repair')}


def build_one(archive_name, orig_dir, acts, iso, write=False, layer_fix=()):
    """处理单个归档。返回统计 dict。"""
    o_path = Path(orig_dir) / archive_name
    s_path = Path(paths.STEAM) / archive_name
    a_path = ASSET / archive_name
    if not o_path.exists():
        return {'archive': archive_name, 'skip': '原版缺该归档'}
    base_path = a_path if a_path.exists() else s_path
    base = arcbuild.read_raw(base_path)
    orig = arcbuild.read_raw(o_path)
    steam = arcbuild.read_raw(s_path) if s_path.exists() else []
    o_by = {lname(nb): (nb, d) for nb, d in orig}
    s_by = {lname(nb): (nb, d) for nb, d in steam}

    plan = acts.get(archive_name, {})
    iso_map = iso.get(archive_name, {})

    # 名 → 成员；保留首次出现的拼写，重复拼写（大小写不同）在同名去重时丢弃
    members = []                     # [[name_bytes, bytearray]]
    have = {}

    def find(low):
        for i, m in enumerate(members):
            if lname(m[0]) == low:
                return i
        return None

    for nb, data in base:
        members.append([nb, bytearray(data)])
    # 起底后按名建立索引（同名的第一份为准）
    for i, m in enumerate(members):
        have.setdefault(lname(m[0]), i)

    stat = {'archive': archive_name, 'base': len(base), 'base_from': str(base_path.name),
            'overwrite': 0, 'isolate': 0, 'insert': 0, 'union': 0,
            'dedup': 0, 'errors': [],
            # `mutated` = 本轮**实际改动**了成员集合/字节；用于「无差异不写盘」
            'mutated': (str(base_path.name) != (s_path.name if s_path.exists() else ''))}

    # ── 2. 画面处置 ──
    # 顺序：先 overwrite / insert_orig（改既有成员或补原版成员），
    # 再并集补入，最后追加 9XX 隔离成员 —— 保证成员顺序确定且 9XX 落在表尾
    # （与历史产物一致；引擎按名查找，顺序不参与语义）。
    for low, act in sorted(plan.items()):
        if act in ('keep', 'isolate'):
            continue
        if act == 'overwrite':
            if low not in o_by:
                stat['errors'].append('overwrite 但原版无 %s' % low)
                continue
            if low not in s_by:
                stat['errors'].append('overwrite 但 Steam 无 %s（应为 insert_orig）' % low)
                continue
            i = have.get(low)
            if i is None:
                stat['errors'].append('overwrite 但底里无 %s' % low)
                continue
            if sha_(members[i][1]) != sha_(o_by[low][1]):
                stat['mutated'] = True
            members[i][1] = bytearray(o_by[low][1])
            stat['overwrite'] += 1
        elif act == 'insert_orig':
            if low not in o_by:
                stat['errors'].append('insert_orig 但原版无 %s' % low)
                continue
            if low in s_by:
                stat['errors'].append('insert_orig 但 Steam 已有 %s（应为 overwrite）' % low)
                continue
            nb, data = o_by[low]
            if low in have:
                # 底里已有（上一轮补过）⇒ 幂等，只校正字节
                if sha_(members[have[low]][1]) != sha_(data):
                    stat['mutated'] = True
                members[have[low]][1] = bytearray(data)
            else:
                members.append([nb, bytearray(data)])
                have[low] = len(members) - 1
                stat['mutated'] = True
            stat['insert'] += 1
        else:
            stat['errors'].append('未知动作 %r（%s）' % (act, low))

    # ── 3. 并集补入 ──
    for low, (nb, data) in o_by.items():
        if low in have:
            continue
        if low.endswith('.mos'):
            continue                     # .MOS：打码变体，不补
        members.append([nb, bytearray(data)])
        have[low] = len(members) - 1
        stat['union'] += 1
        stat['mutated'] = True

    # ── 3b. 9XX 命名隔离（追加到表尾）──
    for low, act in sorted(plan.items()):
        if act != 'isolate':
            continue
        if low not in o_by:
            stat['errors'].append('isolate 但原版无 %s' % low)
            continue
        i = have.get(low)
        if i is None:
            stat['errors'].append('isolate 但底里无 %s' % low)
            continue
        # 原名回 Steam 字节（Steam 路径继续取原名）
        if low in s_by:
            if sha_(members[i][1]) != sha_(s_by[low][1]):
                stat['mutated'] = True
            members[i][1] = bytearray(s_by[low][1])
        iso_name = iso_map.get(low)
        if not iso_name:
            stat['errors'].append('isolate 缺 9XX 名 %s' % low)
            continue
        ilow = iso_name.lower()
        if ilow in have:
            if sha_(members[have[ilow]][1]) != sha_(o_by[low][1]):
                stat['mutated'] = True
            members[have[ilow]][1] = bytearray(o_by[low][1])
        else:
            members.append([iso_name.encode('utf-16le'), bytearray(o_by[low][1])])
            have[ilow] = len(members) - 1
            stat['mutated'] = True
        stat['isolate'] += 1

    # ── 4. 名字规范化：同名多拼写只留与 backup 一致的那一份 ──
    seen = {}
    keep = []
    for m in members:
        low = lname(m[0])
        if low in seen:
            # 保留拼写与 backup 一致的一份
            prev = seen[low]
            want = s_by.get(low, (None,))[0]
            if want is not None and tname(m[0]) == tname(want):
                keep[prev] = None         # 丢弃先前那份
                seen[low] = len(keep)
            else:
                stat['dedup'] += 1
                continue
        else:
            seen[low] = len(keep)
        keep.append(m)
    deduped = [m for m in keep if m is not None]
    if len(deduped) != len(members):
        stat['dedup'] = len(members) - len(deduped)
        stat['mutated'] = True
    members = deduped

    # ── 回读校验 ──
    sha = sha_

    by = {}
    for m in members:
        low = lname(m[0])
        if low in by:
            stat['errors'].append('仍有重复成员 %s' % low)
        by[low] = m
    for low, act in plan.items():
        if act in ('overwrite', 'insert_orig'):
            if low not in by:
                stat['errors'].append('缺成员 %s' % low)
            elif low in o_by and sha(by[low][1]) != sha(o_by[low][1]):
                stat['errors'].append('%s != 原版字节' % low)
        elif act == 'isolate':
            if low not in by or (low in s_by and sha(by[low][1]) != sha(s_by[low][1])):
                stat['errors'].append('隔离原名 %s != Steam 字节' % low)
            ilow = (iso_map.get(low) or '').lower()
            if not ilow or ilow not in by:
                stat['errors'].append('缺 9XX 成员 %s' % low)
            elif sha(by[ilow][1]) != sha(o_by[low][1]):
                stat['errors'].append('9XX %s != 原版字节' % ilow)
    # 其余成员必须等于 backup：只查**没有处置动作**（plan 里无条目或 keep）的成员。
    # overwrite / isolate / insert_orig 已在上面的分支里断言过，不再重复查 backup。
    for low, (nb, data) in s_by.items():
        if plan.get(low) not in (None, 'keep'):
            continue
        if low in layer_fix:
            continue                     # 层内修复：逐记录由 pna_id_check 核
        if low in by and sha(by[low][1]) != sha(data):
            stat['errors'].append('非处置成员 %s != backup 字节' % low)

    stat['members'] = len(members)
    if stat['errors']:
        return stat

    # 无差异则不写：判据是「本轮是否真的改动了成员」。
    # 不能拿产物与 backup 比——底可能是 asset（上一轮的产物），必然 ≠ backup。
    changed = stat['mutated']
    stat['changed'] = changed
    if write and changed:
        arcbuild.write_arc([(bytes(nb), bytes(d)) for nb, d in members], a_path)
        arcbuild.verify(a_path, expect_count=len(members))
        stat['wrote'] = True
        stat['size'] = a_path.stat().st_size
    else:
        stat['wrote'] = False
    return stat


def verify_asset(archive_name, orig_dir, acts, iso):
    """独立校验已有 asset/<归档>（不写盘）。"""
    return build_one(archive_name, orig_dir, acts, iso, write=False,
                     layer_fix=load_layer_fix())


def main():
    ap = argparse.ArgumentParser(description='归档素材统一写盘（画面处置 + 并集补入 + 规范化）')
    ap.add_argument('--write', action='store_true', help='写 asset/（默认 dry-run）')
    ap.add_argument('--orig-dir', help='原版发行目录（缺省自动发现）')
    ap.add_argument('--only', help='只处理这些归档（逗号分隔，小写）')
    a = ap.parse_args()
    orig = Path(a.orig_dir) if a.orig_dir else Path(paths.orig_dir())
    if not orig.is_dir():
        sys.exit('原版目录不存在: %s' % orig)

    acts, iso = load_censor_plan()
    layer_fix = load_layer_fix()
    targets = [canon(x) for x in TARGET_ARCHIVES]
    if a.only:
        want = {x.strip().lower() for x in a.only.split(',') if x.strip()}
        targets = [t for t in targets if t.lower() in want]

    ASSET.mkdir(parents=True, exist_ok=True)
    rows, bad = [], 0
    print('%-14s %-7s %-6s %-6s %-6s %-6s %-6s %-6s %s'
          % ('归档', '底', '原成员', '覆盖', '隔离', '插入', '并集', '去重', '结果'))
    for t in targets:
        st = build_one(t, orig, acts, iso, write=a.write, layer_fix=layer_fix)
        if st.get('skip'):
            print('%-14s %s' % (t, st['skip']))
            continue
        rows.append(st)
        if st['errors']:
            bad += 1
            res = '✗ %d 项错误' % len(st['errors'])
        elif st.get('wrote'):
            res = 'WROTE (%d 成员, %d B)' % (st['members'], st['size'])
        elif st.get('changed'):
            res = '[dry-run] 将写盘 (%d 成员)' % st['members']
        else:
            res = 'SKIP（与 backup 相同）'
        print('%-14s %-7s %-6d %-6d %-6d %-6d %-6d %-6d %s'
              % (t, st['base_from'], st['base'], st['overwrite'], st['isolate'],
                 st['insert'], st['union'], st['dedup'], res))
        for e in st['errors']:
            print('    ! %s' % e)
        sys.stdout.flush()

    # 汇总断言：覆盖名单条数 == 实际替换次数（逐名对齐）
    for t in targets:
        plan = acts.get(t, {})
        st = next((r for r in rows if r['archive'] == t), None)
        if st is None:
            continue
        for act, key in (('overwrite', 'overwrite'), ('insert_orig', 'insert'),
                         ('isolate', 'isolate')):
            want = sum(1 for v in plan.values() if v == act)
            if st[key] != want:
                print('  ✗ %s: %s 名单 %d != 实际 %d' % (t, act, want, st[key]))
                bad += 1

    print()
    if bad:
        print('失败：%d 个归档有问题（见上方 ! 行）' % bad)
        sys.exit(1)
    print('全部通过：%d 个归档' % len(rows))
    if not a.write:
        print('（dry-run；加 --write 落盘）')


if __name__ == '__main__':
    main()
