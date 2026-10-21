# -*- coding: utf-8 -*-
"""闸门：**选项帧内不得出现 `0x16`**（Steam 侧会关闭输入门）。

实机证据（详见 doc/engine-mechanics.md「`0x16` 的副作用」与 doc/file-formats.md「选项编写规范」）：

* 本作 Steam 版若在「提示句 → 选项头」之间保留 `16 00 00`，选项期会出现
  `MenuInf.enabled == false` 且 `MenuInf.effect == true` —— 这一对值只有
  `closeMessageWindow`（`LegacyGame.lua/15/50`，内含 `WndDisp` 关窗特效）会产生。
* 输入门 `GetMenuMouseEnable`（`/15/5`）要求两者分别为 `true` / `false`，
  于是恒不通过 ⇒ 选项能画、无悬停、点不动、`selCursor` 不变（第 2 项恒高亮）。
* 删掉该 `0x16` 后：悬停/点击/两条分支全部正常，**且提示句留在框内与选项同屏**
  （即原版的"留框提示"语义）。
* 原版（老一代 Lua，无 `enabled/effect` 状态机）容忍这条 `0x16`；Steam 版不容忍
  ⇒ 属"代际差异"，还原时必须按目标引擎剔除。

实现：`tool/ws2.drop_choice_frame_op16()`（写盘期剔除，幂等），本闸门只做**产物检查**。

用法: python script/checks/choice_frame_check.py [--pay]
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
    fails = []
    n_choice = 0
    if not os.path.exists(path):
        return 0, []
    for nb, data in arcbuild.read_raw(path):
        name = nb.decode('utf-16le', 'replace')
        if not name.endswith('.ws2'):
            continue
        dec = ws2.decode(data)
        try:
            ins, _ok = ws2dis.disassemble(dec)
        except Exception:
            continue
        for i, (off, op, _sz, _ops) in enumerate(ins):
            if op != 0x0F:
                continue
            n_choice += 1
            stop = off
            if i > 0 and ins[i - 1][1] == 0x0E:
                stop = ins[i - 1][0]
            j = i - 1
            while j >= 0 and ins[j][1] != 0x14:
                j -= 1
            if j < 0:
                fails.append('%s: `0f` @0x%x 之前找不到提示句' % (name, off))
                continue
            prompt = ins[j][0]
            hit = [o for (o, o_op, _s, _p) in ins if o_op == 0x16 and prompt < o < stop]
            if hit:
                fails.append('%s: 选项帧内含 0x16 ×%d（首个 @0x%x，提示句 @0x%x，0f @0x%x）'
                             % (name, len(hit), hit[0], prompt, off))
    return n_choice, fails


def main(argv):
    stages = [('asset', os.path.join(ROOT, 'asset'))]
    if '--pay' in argv:
        stages.append(('payload', os.path.join(ROOT, 'payload')))
    all_fails, total = [], 0
    for tag, base in stages:
        for arc in ARCHIVES:
            n, f = check_archive(os.path.join(base, arc))
            total += n
            all_fails += ['[%s] %s' % (tag, x) for x in f]
    for x in all_fails:
        print('  FAIL', x)
    if all_fails:
        print('选项帧检查: FAIL %d 项（%d 张选项表）' % (len(all_fails), total))
        return 1
    print('选项帧检查: PASS（%d 张选项表：提示句→选项头之间无 0x16）' % total)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
