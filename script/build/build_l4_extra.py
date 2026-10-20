# -*- coding: utf-8 -*-
"""L4 补漏：还原块引用到、但交付面缺失的原版成员 → 并集补入。

依据
----
`script/checks/restore_asset_coverage.py`（资源配对正确性闸）实测：还原块引用的 2413 个
资源名里，**12 个**在 `asset/ ∪ backup/` 找不到、而原版有 ⇒ 原 L4 的并集范围漏了 4 个归档：

| 归档 | 缺的成员 | 引用数 |
|---|---|---|
| `Chip1.arc` | `BG15_03B.PNG`、`BG24_01B.PNG` | 1 / 9 |
| `Chip2.arc` | `AGE_16_001S.PNG` | 1 |
| `Graphic.arc` | `CUTIN_98_05A.PNG`、`CUTIN_98_05B.PNG` | 2 / 2 |
| `Se.arc` | 7 个 `.OGG` | 各 1 |

做法
----
对这四个归档：**以 `asset/<归档>`（若存在）为底**（保留 L3 的画面覆盖结论），
把「原版有、底里没有」的成员**按原版顺序追加**；`.MOS` 成员不补（用户决策）。
**同名成员一律保留底里的字节**（= Steam 字节，或 L3 判定的原版覆盖字节）。

幂等；回读校验：成员数 == 底 + 新增；底里每个成员字节不变；新增成员 == 原版同名字节。

用法：`python script/build/build_l4_extra.py`
"""
import os
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

from tool import arcbuild, paths  # noqa: E402

TARGETS = ['chip1.arc', 'chip2.arc', 'graphic.arc', 'se.arc']


def canonical(fn):
    """按 `backup/` 里的**实际拼写**解析归档名。

    ⚠️ `build_l3.py` 的 `--archives` 默认值是硬编码大写（姊妹作拼写），会把产物写成
    `asset/GRAPHIC.arc`/`asset/CHIP2.arc`，而 `backup/` 是 `Graphic.arc`/`Chip2.arc`。
    Windows 文件系统不区分大小写、测试覆盖不受影响，但发布链按名匹配 ⇒ 一律以
    `backup/` 的拼写为准（本模块与 `asset/` 改名都遵此）。
    """
    for name in os.listdir(paths.STEAM):
        if name.lower() == fn:
            return name
    return fn


def canon(name_bytes):
    return name_bytes.decode('utf-16le').lower()


def main():
    orig_dir = paths.orig_dir()
    asset_dir = os.path.join(ROOT, 'asset')
    os.makedirs(asset_dir, exist_ok=True)
    for fn in TARGETS:
        fn = canonical(fn)
        o_path = os.path.join(orig_dir, fn)
        s_path = os.path.join(paths.STEAM, fn)
        a_path = os.path.join(asset_dir, fn)
        if not os.path.exists(o_path):
            print('%-14s 原版缺该归档，跳过' % fn)
            continue
        base_path = a_path if os.path.exists(a_path) else s_path
        base = arcbuild.read_raw(base_path)
        orig = arcbuild.read_raw(o_path)
        have = {canon(nb) for nb, _ in base}
        add = [(nb, d) for nb, d in orig
               if canon(nb) not in have and not nb.decode('utf-16le').lower().endswith('.mos')]
        if not add:
            print('%-14s 无新增（底 %d 成员）' % (fn, len(base)))
            continue
        members = list(base) + add
        arcbuild.write_arc(members, a_path)
        cnt, size, _end = arcbuild.verify(a_path, expect_count=len(members))
        # 回读校验
        back = arcbuild.read_raw(a_path)
        bd = {canon(nb): d for nb, d in back}
        assert len(back) == len(members), fn
        for nb, d in base:
            assert bd[canon(nb)] == d, '%s 底成员被改动: %r' % (fn, nb)
        od = {canon(nb): d for nb, d in orig}
        for nb, d in add:
            assert bd[canon(nb)] == od[canon(nb)], '%s 新增成员字节不符: %r' % (fn, nb)
        print('%-14s 底 %-4d + 新增 %-4d = %-4d 成员、%d B  (底=%s)'
              % (fn, len(base), len(add), cnt, size,
                 'asset' if base_path == a_path else 'backup'))
    print('完成。')


if __name__ == '__main__':
    main()
