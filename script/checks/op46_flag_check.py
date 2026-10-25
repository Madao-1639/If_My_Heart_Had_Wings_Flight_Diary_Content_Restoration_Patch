# -*- coding: utf-8 -*-
"""`0x46` 子层槽绑定标志闸（产物须落在目标引擎自身的编码词表内）。

背景（2026-10-25，实机「立绘遮挡 CG」缺陷定案）：
  `0x46` 第一条（把 PNA 子层绑到引擎层槽，操作数含 4 个层槽 id 浮点）带 1 字节标志，
  **原版工具链写 `0x80`、Steam 工具链写 `0xf0`**（全库 ~7.6k 处零交叉；`0x00`＝纯坐标
  定位，两侧一致）。原版块带着 `0x80` 进 Steam 引擎会**欠绑定子层槽**——未重绑的槽
  保留上一次显示的子图 ⇒ 上一处的立绘残留在屏、压在后续 CG 上，直到清槽指令。
  `script/build/build_patch.py::prep_orig` 负责归一（`0x80 → 0xf0`）；本闸断言产物
  里不再存在 `0x80`（Steam 引擎自身从不产出该值）。
退出码：1 = 产物仍携带 `0x80` 标志。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis  # noqa: E402

ARCHIVE = os.path.join(ROOT, 'asset', 'Rio.arc')


def flag_of(ops):
    """`0x46` 操作数 → 标志字节（通道 NUL 后第 3 字节）；布局异常返回 None。"""
    rest = ops.split(b'\x00', 1)
    if len(rest) != 2 or len(rest[1]) < 3:
        return None
    return rest[1][2]


def main():
    members = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(ARCHIVE)}
    stat = {}
    bad = []
    for name in sorted(members):
        if not name.lower().endswith('.ws2'):
            continue
        ins, ok = ws2dis.disassemble(ws2.decode(members[name]))
        assert ok, '%s 线性解析不自洽' % name
        n = {}
        for _off, op, _sz, ops in ins:
            if op != 0x46:
                continue
            f = flag_of(ops)
            key = '0x%02x' % f if f is not None else '??'
            n[key] = n.get(key, 0) + 1
            if f == 0x80:
                bad.append(name)
        for k, v in n.items():
            stat[k] = stat.get(k, 0) + v
    print('0x46 标志字节分布：%s' % ('，'.join('%s=%d' % kv for kv in sorted(stat.items()))))
    if bad:
        print('❌ 产物仍携带原版 `0x80` 标志（Steam 引擎不认识）：%d 处，脚本 %r'
              % (len(bad), sorted(set(bad))[:10]))
        sys.exit(1)
    print('产物无 `0x80` 标志 ✅')


if __name__ == '__main__':
    main()
