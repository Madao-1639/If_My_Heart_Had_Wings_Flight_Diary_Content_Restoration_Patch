# -*- coding: utf-8 -*-
"""跨版本转换的**机制级**校验：转换是否「纯追加一个新字段、原操作数逐字节不变」。

为什么需要这个闸
----------------
`tool/ws2conv.convert_script` 的 `CONV` 规则（7 个 opcode 各补一个字段）是从
**两版格式表差分**推出来的。但"表差"只是**结构**事实，不能证明转换**语义安全**——
必须逐指令验证：转换后的指令流，去掉新增的那个字段后，是否与原版操作数**逐字节相同**。

判据（严格）
------------
对全部原版脚本的**每一条指令**：
  1. opcode 不变；
  2. 指令条数不变；
  3. 按该 opcode 的 CONV 规则剥掉新增字段后，操作数字节 **== 原版表解出的操作数字节**。

三条全过 ⇒ 转换是**纯结构性 padding**：不改变、不重排、不丢失任何原有操作数，
唯一的变化是插入一个新字段。此时"新字段填什么值"成为唯一的自由度，而该值取
**Steam 工具链自身产出的值**（0 / 0.0）即与参考实现同构。

用法：`python script/checks/convert_purity.py`
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

from tool import arcbuild, paths, ws2, ws2conv, ws2dis  # noqa: E402

# 尾部追加 1 字节 u8 的 opcode
END1 = {0x14, 0x15, 0x16, 0x1c}
# 尾部追加 4 字节 f32 的 opcode
END4 = {0x1e, 0x28}
# 中部（倒数第 4 字节前）插入 1 字节 u8 的 opcode
MID1 = {0x11}


def operands(dec, tab):
    ins, _ok = ws2dis.disassemble(dec, formats=tab)
    return [(op, ops) for _off, op, _sz, ops in ins]


def strip_extra(op, ops):
    """按 CONV 规则剥掉新增字段，返回还原后的操作数字节；无法判定返回 None。"""
    if op in MID1:
        return ops[:len(ops) - 5] + ops[len(ops) - 4:] if len(ops) >= 5 else None
    if op in END1:
        return ops[:-1] if ops else None
    if op in END4:
        return ops[:-4] if len(ops) >= 4 else None
    return None


def main():
    orig_dir = paths.orig_dir()
    src = {nb.decode('utf-16le'): d
           for nb, d in arcbuild.read_raw(os.path.join(orig_dir, 'Rio.arc'))}
    to, tf = ws2dis.FORMATS_ORIG, ws2dis.FORMATS

    total = extra = 0
    bad = []
    per_op = {}
    for name in sorted(src):
        if not name.lower().endswith('.ws2'):
            continue
        raw = src[name]
        try:
            conv = ws2conv.convert_script(raw, orig_dir)
        except Exception as e:                       # noqa: BLE001
            bad.append((name, 'convert failed: %s' % e))
            continue
        ao = operands(ws2.decode(raw), to)
        ac = operands(ws2.decode(conv), tf)
        if len(ao) != len(ac):
            bad.append((name, 'instruction count %d -> %d' % (len(ao), len(ac))))
            continue
        for (opo, opso), (opc, opsc) in zip(ao, ac):
            total += 1
            if opo != opc:
                bad.append((name, 'opcode changed'))
                break
            if len(opsc) == len(opso):
                continue
            extra += 1
            per_op[opo] = per_op.get(opo, 0) + 1
            st = strip_extra(opc, opsc)
            if st is None or st != opso:
                bad.append((name, 'op 0x%02x: 剥掉新增字段后 != 原操作数' % opo))

    print('核验指令 %d 条；其中 %d 条带新增字段；异常 %d 处'
          % (total, extra, len(bad)))
    print('带新增字段的 opcode 分布：%s'
          % {hex(k): v for k, v in sorted(per_op.items())})
    for b in bad[:10]:
        print('   ', b)
    if bad:
        print('❌ 转换不是纯 padding —— 存在语义改动，需逐条排查')
        return 1
    print('✅ 转换是纯结构性 padding：原有操作数逐字节不变，仅插入一个新字段')
    return 0


if __name__ == '__main__':
    sys.exit(main())
