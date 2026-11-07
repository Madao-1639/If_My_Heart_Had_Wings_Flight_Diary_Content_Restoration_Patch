# -*- coding: utf-8 -*-
"""跨引擎**标志字节**闸：`0x46` 子层槽绑定标志 + `0x47` 参数来源标志。

产物必须落在**目标引擎自身的编码词表**内。两侧工具链对这两条同族指令的取值零交叉：

| 指令 | 原版（v1.0）工具链 | Steam（新版）工具链 | 迁移规则 |
|---|---|---|---|
| `0x46 <通道>\\0 <i16> <u8 标志> <f32×4>` | `0x00` / `0x80` | `0x00` / `0xf0` | `0x80 → 0xf0` |
| `0x47 <通道>\\0 <特效>\\0 <u16 sel> <u8 A> <u8 B> …` | `0x00` / `0x80` | `0x00` / `0x10` / `0xc0` | `0x80 → 0x10`（上一条 `0x45` 的 type = 6）／`0x80 → 0xc0`（其余） |

`0x46` 带原版 `0x80` 进 Steam 引擎会**欠绑定子层槽**——未重绑的槽保留上一次显示的子图
⇒ 上一处的立绘残留在屏、压在后续内容上。`0x47` 的 B 字节是**参数来源**（bit7 =「后随 5 个
f32 是浮点变量索引」），新版工具链把这一位拆成「字面 `0x10` / 变量 `0xc0`」并跟随上一条
`0x45`（DragBackground）的 type；带着原版 `0x80` 进 Steam 引擎则落在目标引擎自身的词表外，
动画终点/参数绑定不可依赖。语义实证与参考实现见 `tool/writer.norm_orig_flags`、
`doc/engine-mechanics.md`「0x47 Effect1」。

退出码：1 = 产物仍携带原版取值（`0x46` 的 `0x80`、`0x47` 的 `0x80`）。
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

# 各指令在产物里的词表（Steam 引擎自身脚本的实测取值集合）
VOCAB_46 = {0x00, 0xf0}
VOCAB_47 = {0x00, 0x10, 0xc0}


def flag46_of(ops):
    """`0x46` 操作数 → 标志字节（通道 NUL 后第 3 字节）；布局异常返回 None。"""
    rest = ops.split(b'\x00', 1)
    if len(rest) != 2 or len(rest[1]) < 3:
        return None
    return rest[1][2]


def flag47_of(ops):
    """`0x47` 操作数 → 参数来源字节（特效名 NUL 之后：`u16 sel` `u8 A` `u8 B`）。"""
    i = ops.find(b'\x00')
    j = ops.find(b'\x00', i + 1) if i >= 0 else -1
    if j < 0 or len(ops) <= j + 4:
        return None
    return ops[j + 4]


def main():
    members = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(ARCHIVE)}
    stat46, stat47 = {}, {}
    bad = []
    for name in sorted(members):
        if not name.lower().endswith('.ws2'):
            continue
        ins, ok = ws2dis.disassemble(ws2.decode(members[name]))
        assert ok, '%s 线性解析不自洽' % name
        for _off, op, _sz, ops in ins:
            if op == 0x46:
                f = flag46_of(ops)
                key = '0x%02x' % f if f is not None else '??'
                stat46[key] = stat46.get(key, 0) + 1
                if f not in VOCAB_46:
                    bad.append('%s: 0x46 标志 %s（词表外）' % (name, key))
            elif op == 0x47:
                f = flag47_of(ops)
                key = '0x%02x' % f if f is not None else '??'
                stat47[key] = stat47.get(key, 0) + 1
                if f not in VOCAB_47:
                    bad.append('%s: 0x47 参数来源 %s（词表外）' % (name, key))
    print('0x46 标志字节分布：%s' % ('，'.join('%s=%d' % kv for kv in sorted(stat46.items()))))
    print('0x47 参数来源分布：%s' % ('，'.join('%s=%d' % kv for kv in sorted(stat47.items()))))
    if bad:
        print('❌ 产物携带原版工具链取值（Steam 引擎词表外）：%d 处' % len(bad))
        for b in bad[:20]:
            print('   ' + b)
        if len(bad) > 20:
            print('   …（共 %d 处）' % len(bad))
        sys.exit(1)
    print('产物两类标志均落在 Steam 词表内 ✅')


if __name__ == '__main__':
    main()
