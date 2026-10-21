# -*- coding: utf-8 -*-
"""闸门：WS2 跳转自洽 + `.lng` 槽位等式（选项机制的两条硬约束）。

1. **跳转自洽**：所有"解码流内绝对偏移"的操作数都必须落在**指令起点**上。
   - `0x01`（Condition）字段 7 / 11；`0x02` 字段 0；`0x06`（Jump）字段 0；
   - `0x0f` 条目的 `06 <u32>`（内联在操作数里，见 `tool.ws2.choice_entries`）。
   另外整条流必须线性自洽（恰好在 `0xff` 结束、其后仅尾表 8 字节）。
   依据：补选项头/插入行都会移动后续指令；`rel` 算错就会"跳进指令中间"，实机表现为随机失控。
2. **槽位等式**：`lng 条数 == 0x14 条数 + Σ(0f count)`。
   依据：`0x14` 的 id 与 `0x0f` 条目的 `strid` 共用一个计数器（见 doc/file-formats.md）。

用法: python script/checks/choice_jump_check.py [--pay]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis, lng            # noqa: E402
from tool.ws2conv import REBASE_OPS                    # noqa: E402

TAIL_LEN = 8


def check_script(name, data):
    fails = []
    dec = ws2.decode(data)
    try:
        ins, ok = ws2dis.disassemble(dec)
    except Exception as e:
        return ['%s: 线性反汇编失败 %s' % (name, e)], 0, 0
    if not ok:
        fails.append('%s: 未在 0xff 收尾或尾表长度不为 %d' % (name, TAIL_LEN))
    starts = {x[0] for x in ins}
    n14 = 0
    nchoice = 0
    for off, op, size, ops in ins:
        if op == 0x14:
            n14 += 1
        if op == 0x0F:
            nchoice += ops[0]
            for _so, _to, _lo, _jo, kind, val in ws2.choice_entries(dec, off):
                if kind == 'abs' and val and val not in starts:
                    fails.append('%s: `0f` @0x%x 条目跳转 %#x 不在指令起点'
                                 % (name, off, val))
        for k in REBASE_OPS.get(op, ()):
            if len(ops) < k + 4:
                continue
            import struct
            v = struct.unpack_from('<I', ops, k)[0]
            if v and v not in starts:
                fails.append('%s: op %#x @0x%x 字段 %d 目标 %#x 不在指令起点'
                             % (name, op, off, k, v))
    return fails, n14, nchoice


def check_lng(base, per_script):
    fails = []
    zdir = os.path.join(base, 'zh-CN')
    zp = os.path.join(zdir, 'Rio.arc')
    if not os.path.exists(zp):
        return fails
    members = {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(zp)}
    for script, (n14, nch) in sorted(per_script.items()):
        lng_name = script[:-len('.ws2')] + '.lng' if script.endswith('.ws2') else None
        if not lng_name or lng_name not in members:
            continue
        try:
            rows = lng.parse_lng(members[lng_name])
        except Exception as e:
            fails.append('%s: .lng 解析失败 %s' % (lng_name, e))
            continue
        if len(rows) != n14 + nch:
            fails.append('%s: lng 条数 %d != 0x14(%d) + Σ(0f count)(%d)'
                         % (lng_name, len(rows), n14, nch))
    return fails


def main(argv):
    stages = [('asset', os.path.join(ROOT, 'asset'))]
    if '--pay' in argv:
        stages.append(('payload', os.path.join(ROOT, 'payload')))
    all_fails = []
    n_ws2 = n_choice = 0
    for tag, base in stages:
        arc = os.path.join(base, 'Rio.arc')
        if not os.path.exists(arc):
            continue
        per_script = {}
        for nb, data in arcbuild.read_raw(arc):
            name = nb.decode('utf-16le', 'replace')
            if not name.endswith('.ws2'):
                continue
            n_ws2 += 1
            f, n14, nch = check_script(name, data)
            n_choice += nch
            per_script[name] = (n14, nch)
            all_fails += ['[%s] %s' % (tag, x) for x in f]
        all_fails += ['[%s] %s' % (tag, x) for x in check_lng(base, per_script)]
    for x in all_fails:
        print('  FAIL', x)
    if all_fails:
        print('跳转/槽位检查: FAIL %d 项（%d 个 .ws2 / %d 个选项条目）'
              % (len(all_fails), n_ws2, n_choice))
        return 1
    print('跳转/槽位检查: PASS（%d 个 .ws2 跳转全部落在指令起点；.lng 槽位等式成立；%d 个选项条目）'
          % (n_ws2, n_choice))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
