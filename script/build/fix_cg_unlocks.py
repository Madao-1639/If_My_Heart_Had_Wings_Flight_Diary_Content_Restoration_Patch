# -*- coding: utf-8 -*-
"""就地修正 `asset/Rio.arc` 的**解锁组**（ASF 口径）。

用途：`script/build/build_patch.py` 已在**构建期**接上 `tool/cgunlock.py`（抛弃原版独有的
解锁对 + 同名反查）。本脚本是**同一套规则的幂等收尾**：给已存在的 `asset/Rio.arc` 用，
无需原版发行目录（只读 `backup/` 作 Steam 索引 + `asset/` 自身）。

规则与判据见 `tool/cgunlock.py` 文件头与 `doc/file-formats.md`「CG 显示的固有 id 对」：
  1. **抛弃**原版命名空间的解锁对（Steam 的画廊/计数表里没有这些 id；其 B 与 Steam 条目号
     重叠 ⇒ 误点亮没看过的缩略图、虚增 CG 完成度）；
  2. **同名反查**：原版显示的那张 CG 在 Steam 里也有同名显示点时，改写为 Steam 的解锁对。

纪律：
* 只动**相邻** `0b A 01 0b B 01`（CG 固有组）；不相邻的 `0b` 是场景旗标，一条不动；
* 删除后统一重定基 `0x01`/`0x02`/`0x06`（流内绝对偏移），并回读断言目标落在指令起点；
* 末尾 8 字节明文尾表按新指令流重算（`0x14`/`0x0f` 条数不因本改动变化，仍回写校验）；
* 幂等：已合规的脚本零改动；先备份 `asset/Rio.arc.before_cg_unlock`，回读逐字节校验。

用法：
    python script/build/fix_cg_unlocks.py            # dry-run，只报告
    python script/build/fix_cg_unlocks.py --apply    # 写入 asset/Rio.arc
"""
import argparse
import os
import shutil
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tool import arcbuild, cgunlock, ws2, ws2dis                    # noqa: E402

STEAM_RIO = os.path.join(ROOT, 'backup', 'Rio.arc')
PATCH_RIO = os.path.join(ROOT, 'asset', 'Rio.arc')


def ws2_members(path):
    return {nb.decode('utf-16le', 'replace').upper(): d
            for nb, d in arcbuild.read_raw(path)
            if nb.decode('utf-16le', 'replace').lower().endswith('.ws2')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='写入 asset/Rio.arc')
    a = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    steam = ws2_members(STEAM_RIO)
    index, native = cgunlock.steam_index(steam)
    patch = ws2_members(PATCH_RIO)
    spec = cgunlock.scan(patch, index, native)

    todo, total = {}, {'drop': 0, 'repoint': 0}
    for name in sorted(spec):
        st = spec[name]
        if not st['drop'] and not st['repoint']:
            continue
        raw, got = cgunlock.plan_bytes(patch[name], st)
        # 回读：线性解析自洽 + 无残留合规项
        ins, ok = ws2dis.disassemble(ws2.decode(raw))
        assert ok, '%s 改写后线性解析失步' % name
        left = [t for t in cgunlock.pair_instances(ins)
                if (t[1], t[2]) not in native and t[3] is not None]
        assert not left, '%s 仍有 %d 处待处置的解锁对' % (name, len(left))
        # 尾表（末尾 8 字节明文）必须与实算条数一致
        dec = ws2.decode(raw)
        body = dec[:-ws2.TAIL_LEN]
        want = ws2.tail_counts(body)
        got_tail = ws2.read_tail_counts(raw)
        if got_tail != want:
            raise AssertionError('%s 尾表 %s != 实算 %s' % (name, got_tail, want))
        todo[name] = raw
        total['drop'] += got['drop']
        total['repoint'] += got['repoint']
        print('  %-22s 抛弃 ORIG %2d / 同名反查 %2d（%d -> %d B）'
              % (name, got['drop'], got['repoint'], len(patch[name]), len(raw)))

    if not todo:
        print('无需改动（解锁组已符合 ASF 口径）')
        return 0
    print('\n合计：%d 个脚本；抛弃 ORIG 解锁对 %d 处、同名反查 %d 处'
          % (len(todo), total['drop'], total['repoint']))
    if not a.apply:
        print('（dry-run，未写入；加 --apply 执行）')
        return 0

    bak = PATCH_RIO + '.before_cg_unlock'
    if not os.path.exists(bak):
        shutil.copy2(PATCH_RIO, bak)
        print('已备份 %s' % os.path.basename(bak))
    members = [(nb, todo.get(nb.decode('utf-16le', 'replace').upper(), d))
               for nb, d in arcbuild.read_raw(PATCH_RIO)]
    arcbuild.write_arc(members, PATCH_RIO)
    arcbuild.verify(PATCH_RIO, expect_count=len(members))
    back = ws2_members(PATCH_RIO)
    for name, data in todo.items():
        assert back[name] == data, '%s 回读不一致' % name
    print('已写入 %d 个脚本；归档校验通过、回读一致' % len(todo))
    return 0


if __name__ == '__main__':
    sys.exit(main())
