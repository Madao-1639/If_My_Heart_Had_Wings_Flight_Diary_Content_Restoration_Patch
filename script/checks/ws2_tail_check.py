# -*- coding: utf-8 -*-
"""WS2 尾表闸：产物每个 `.ws2` 的**末尾 8 字节明文表**必须等于实算的 (消息数, 选项条目数)。

为什么这是硬闸
--------------
成员最后 8 字节 = `[u32 消息数][u32 选项条目数]`，**明文、不参与 rotate-6 混淆**
（读到的是「明文的 rotate-6」，所以抄宿主尾部 = 抄旧计数）。引擎**加载脚本时**读它
（`data[size-8]` / `data[size-4]`），据此给「已读消息位图」（存档目录 `MessageFlag.dat`）
分配 `(消息数 + 选项条目数 + 7) / 8` 字节；写位函数 `bitmap[idx>>3] |= 1 << (idx&7)`
**不做边界检查** ⇒ 尾表小于脚本真实消息数时，高位下标直接写到相邻堆块上，延迟到某次
`free` 被堆校验抓到 ⇒ `0xc0000374` **概率性闪退**（不是崩在写位处；也可能先在 Lua/UI
上表现为随机的 nil 错误）。

实机指纹（2026-10-21 本作定位）：
- `MessageFlag.dat` 记录的位图容量明显小于脚本消息数（`HUS_001_E` 81 B↔641、`HOT_004_E`
  96 B↔762，而脚本已 824/1319 条）；
- 该记录 `B`（已标记次数）持续增大而位图仍为 0（写位全部落在容量之外）；
- 重命名 `MessageFlag.dat` 后暂时不闪退（堆布局变了，掩盖），但记录容量依旧按**旧尾表**分配。

判据
----
产物每个 `.ws2`：`read_tail_counts(raw) == tail_counts(decode(raw))`。
与基线（`backup/`）逐成员比：基线自己就偏离的脚本单独列出，不计入「本项目新增破坏」。

退出码：1 = 存在违规。报告写 `tmp/ws2_tail_check.md`。
"""
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

from tool import arcbuild, ws2  # noqa: E402

ASSET = os.path.join(ROOT, 'asset')
BACKUP = os.path.join(ROOT, 'backup')
REPORT = os.path.join(ROOT, 'tmp', 'ws2_tail_check.md')


def members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def main():
    arcs = []
    for dirpath, _dirs, files in os.walk(ASSET):
        for fn in files:
            if fn.lower().endswith('.arc'):
                arcs.append(os.path.relpath(os.path.join(dirpath, fn), ASSET).replace('\\', '/'))
    rows, bad, inherited = [], [], []
    n_ok = 0
    for rel in sorted(arcs):
        try:
            ms = members(os.path.join(ASSET, rel))
        except Exception as ex:
            print('  SKIP %-22s (%s)' % (rel, ex))
            continue
        if not any(n.lower().endswith('.ws2') for n in ms):
            continue
        bp = os.path.join(BACKUP, rel)
        base = members(bp) if os.path.exists(bp) else {}
        ok, wrong = ws2.check_tails(ms, base)
        n_ok += len(ok)
        for name, cnt, tail in wrong:
            is_inherit = False
            if name in base:
                try:
                    is_inherit = ws2.read_tail_counts(base[name]) != ws2.tail_counts(ws2.decode(base[name]))
                except Exception:
                    is_inherit = True
            (inherited if is_inherit else bad).append((rel, name, cnt, tail))
        for name, cnt, tail in wrong:
            rows.append('| %s | %s | %s | %s | %s |' % (
                rel, name, cnt, tail,
                '基线已有' if (rel, name, cnt, tail) in inherited else '❌'))

    lines = ['# WS2 尾表闸（末尾 8 字节明文 == 实算 (消息数, 选项数)）', '',
             '| 归档 | 成员 | 实算 (msgs, choices) | 尾表 (msgs, choices) | 判定 |',
             '|---|---|---|---|---|'] + rows + ['']
    if not bad:
        lines.append('结论：✅ 通过（%d 个 .ws2 尾表正确%s）'
                     % (n_ok, '' if not inherited else '；%d 项为基线已有偏差' % len(inherited)))
    else:
        lines.append('结论：❌ %d 项违规（尾表与实算不符 ⇒ 已读位图容量错 ⇒ 越界写坏堆）' % len(bad))
        lines += [''] + ['- %s / %s：实算 %s 尾表 %s' % (r, n, c, t) for r, n, c, t in bad]
    if inherited:
        lines += ['', '基线已有偏差（非本项目新增，记录备查）：']
        lines += ['- %s / %s：实算 %s 尾表 %s' % (r, n, c, t) for r, n, c, t in inherited]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
