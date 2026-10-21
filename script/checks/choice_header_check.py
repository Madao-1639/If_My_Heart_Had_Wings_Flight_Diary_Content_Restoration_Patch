# -*- coding: utf-8 -*-
"""闸门：产物里每一张选项表（`0x0f`）之前必须有形态正确的**选项头** `0e 0b 00 <count> 00 01`。

判据来源（`[语料]`，见 tmp/choice_header_spec.txt）
--------------------------------------------
* 同代且**选项实机可用**的本篇（IMHHW）Steam 版：6 个含选项的脚本里，
  `CO1_020` = `0e 0b 00 04 00 01` + `0f 04`、`HUT_005` = `0e 0b 00 02 00 01` + `0f 02`；
  另有 4 个是「无 `0f` 文本表」的条件式变体（`0e` 后面跟 `01`/`0b` 条件组）。
* 本作 Steam 侧没有任何选项、原版（更早一代）也不用这条头 ⇒ 这条头只能由**我们**发，
  漏发就只能靠实机发现，故设为闸门。

规则
----
1. 每个 `0f` 的**前一条指令**必须是 `0x0e`，操作数为 `0b 00 <count> 00 01`；
2. `<count>` 必须等于 `0f` 的 count；
3. 全文件线性反汇编必须自洽（`0x0e` 的 6 字节形态不能被当成别的长度）。

用法
----
    python script/checks/choice_header_check.py            # 检查 asset/ 下全部归档
    python script/checks/choice_header_check.py --pay    # 加上 payload/ 里的归档
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis   # noqa: E402

ARCHIVES = ('Rio.arc',)


def check_archive(path):
    """→ (检查的 .ws2 数, 选项表数, 失败清单)"""
    fails, n_ws2, n_choice = [], 0, 0
    if not os.path.exists(path):
        return 0, 0, []
    for nb, data in arcbuild.read_raw(path):
        name = nb.decode('utf-16le', 'replace')
        if not name.endswith('.ws2'):
            continue
        n_ws2 += 1
        dec = ws2.decode(data)
        try:
            ins, ok = ws2dis.disassemble(dec)
        except Exception as e:
            fails.append('%s: 线性反汇编失败 %s' % (name, e))
            continue
        if not ok:
            fails.append('%s: 未在 0xff 处收尾/尾部残余' % name)
        for idx, (off, op, size, ops) in enumerate(ins):
            if op != 0x0F:
                continue
            n_choice += 1
            count = ops[0]
            if idx == 0:
                fails.append('%s: `0f` @0x%x 是文件首条指令，缺选项头' % (name, off))
                continue
            poff, pop, psize, pops = ins[idx - 1]
            if pop != 0x0E:
                fails.append('%s: `0f` @0x%x 前一条是 op %#04x（不是 `0e` 选项头）'
                             % (name, off, pop))
                continue
            if psize != 6 or pops[0] != 0x0B or pops[1] != 0x00 or pops[3] != 0x00 or pops[4] != 0x01:
                fails.append('%s: `0f` @0x%x 的选项头形态不对：%s'
                             % (name, off, pops.hex(' ')))
                continue
            if pops[2] != count:
                fails.append('%s: `0f` @0x%x 头内 count=%d ≠ 表内 count=%d'
                             % (name, off, pops[2], count))
    return n_ws2, n_choice, fails


def main(argv):
    stages = [('asset', os.path.join(ROOT, 'asset'))]
    if '--pay' in argv:
        stages.append(('payload', os.path.join(ROOT, 'payload')))
    all_fails, total_ws2, total_choice = [], 0, 0
    for tag, base in stages:
        for arc in ARCHIVES:
            n, c, f = check_archive(os.path.join(base, arc))
            total_ws2 += n
            total_choice += c
            all_fails += ['[%s] %s' % (tag, x) for x in f]
    for x in all_fails:
        print('  FAIL', x)
    if all_fails:
        print('选项头检查: FAIL %d 项（%.0f 个 .ws2 / %d 张选项表）'
              % (len(all_fails), total_ws2, total_choice))
        return 1
    print('选项头检查: PASS（%.0f 个 .ws2 / %d 张选项表，每张都有 `0e 0b 00 <count> 00 01`）'
          % (total_ws2, total_choice))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
