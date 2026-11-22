# -*- coding: utf-8 -*-
"""跨脚本接缝闸（seam check）—— 在屏状态跨 `0x07` 跳转是否连续。

机制
----
`0x07 <脚本名>` 只是「换一个脚本接着跑」，**不重置在屏图层**。所以「某脚本第一行
看到什么」取决于**谁跳进来**（前序脚本末尾的画面会被带进目标脚本），而单脚本视角
（`perfsync.row_setters` / `perf_rows` 从空屏起算）在结构上看不见这件事。

姊妹作实测的缺陷形态：Steam 在被删段收场处新增一幕全黑图（`st03 = BG00_01S.PNG`），
该脚本被整脚本回填后，黑幕无人接管、一路盖住新还原的场景 ⇒ **黑屏**。
判据与处置见 doc/restoration-route.md §4.1、doc/lessons-learned.md「跨脚本跳转不重置
在屏状态」条；本作实测结论见 `resource/seam_scope.json`。

适用范围＝**结构枚举**（不靠「哪里测出残留」反推，否则下一批新增内容会静默复发）
------------------------------------------------------------------------------
    scope = { 整脚本回填的脚本（`kind=whole`）}
          ∪ { 首个改动槽位为 0 的宿主（插入区间／删格／演出同步落在脚本最前面）}

两者合起来恰好是「还原内容的**前缀**落在脚本最前面」的位置——那里的第一行画面完全由
前序决定，宿主自身没有任何前缀指令兜住接缝。范围内**所有入边全查**，不看它当前有没有
差异。

三层判据（逐层收窄；①② 只作诊断，③ 才是缺陷）
----------------------------------------------
    ① 并集差 = ∪{前序末尾通道}(产物) − ∪{前序末尾通道}(原版)
    ② 残留   = 前序末尾通道中、目标**前缀区**（首条 `0x14` 之前）未被接管的
    ③ 携入   = 残留中、其值**原样活到目标首行**的            ← 缺陷（HARD）

为什么不直接拿 ① 判：本作实测有 3 处 ① 非空、③ 全空。例 `KAN_2001` 的前序
`KAN_1004` 末尾留着 `bg01=BG00_01S`（纯黑幕），但 `KAN_2001` 前缀区在第 3 条指令就
`33 bg01=BG00_02S`、随后 `SKY04_01B`、`CLEAR bg01`、`BG08_01S` —— 首行时刻
产物与原版**完全相同**（都是 `BG08_01S`）。① 只说明「前序末尾不同」，不说明「玩家
看得到差别」。按 ① 判会为了 0 收益插入清屏，反而改变首帧淡入。

分级
----
* **HARD**：③ 非空（前序的图一路留到目标首行）——含「产物有、原版无」与「两侧都有
  但图名不同」两种。
* **HARD（范围自检）**：结构枚举出的 scope 与 `resource/seam_scope.json` 登记值不符
  （防「判据自己漂移后静默放行」；scope 变了必须重新定案并写进表）。
* **PASS**：③ 为空。①② 的读数照常打印（供人工核对「差集为何无害」）。

用法：`python script/checks/seam_check.py [--product asset] [--orig-dir DIR] [--quiet]`
明细写 `tmp/seam_check.md`；HARD ⇒ 退出码 1。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, paths, perfsync, ws2, ws2conv, ws2dis  # noqa: E402

TABLE = os.path.join(ROOT, 'resource', 'seam_scope.json')
REPORT = os.path.join(ROOT, 'tmp', 'seam_check.md')


def canon(name):
    """脚本名归一：大写、去 `.ws2`、去 Steam 的 `_E` 后缀（两侧命名空间对齐）。

    ⚠️ 归一**只用于对边**，不用于取文件：产物侧成员名仍是 `X_E.ws2`、原版仍是 `X.ws2`。
    """
    n = name.upper()
    if n.endswith('.WS2'):
        n = n[:-4]
    if n.endswith('_E'):
        n = n[:-2]
    return n


def read_members(arc_path):
    """{大写成员名: 成员字节}（不限扩展名，由调用方筛）。"""
    out = {}
    for nb, d in arcbuild.read_raw(arc_path):
        try:
            out[nb.decode('utf-16le').upper()] = d
        except UnicodeDecodeError:
            continue
    return out


def load_prod(arc_path):
    """产物 → {归一脚本名: instrs}（Steam 格式表，解码后线性反汇编）。"""
    out, bad = {}, []
    for name, raw in read_members(arc_path).items():
        if not name.endswith('.WS2'):
            continue
        ins, ok = ws2dis.disassemble(ws2.decode(raw))
        if not ok:
            bad.append(name)
            continue
        out[canon(name)] = [(x[1], x[3]) for x in ins]
    return out, bad


def load_orig(arc_path, ofmt):
    """原版 → {归一脚本名: instrs}（原版格式表）。内嵌数据表脚本解析失败即跳过并记录。"""
    out, bad = {}, []
    for name, raw in read_members(arc_path).items():
        if not name.endswith('.WS2'):
            continue
        try:
            insts, _tail = ws2conv.parse(ws2.decode(raw), ofmt)
        except AssertionError as ex:
            bad.append((name, str(ex)[:60]))
            continue
        out[canon(name)] = insts
    return out, bad


def cmp_carried(prod, orig, scope, canon=canon):
    """→ (rows, hard, profiles)。rows 逐脚本带三层读数与两侧状态明细。"""
    pp = {k: perfsync.script_profile(v, canon) for k, v in prod.items()}
    po = {k: perfsync.script_profile(v, canon) for k, v in orig.items()}
    ep = perfsync.seam_entry(pp, scope)
    eo = perfsync.seam_entry(po, scope)
    rp = perfsync.seam_resid(pp, scope)
    ro = perfsync.seam_resid(po, scope)
    cp = perfsync.seam_carried(prod, pp, scope)
    co = perfsync.seam_carried(orig, po, scope)

    rows, hard = [], []
    for t in scope:
        rec = {
            'script': t,
            'prod_entry': {k: sorted(v) for k, v in sorted(ep.get(t, {}).items())},
            'orig_entry': {k: sorted(v) for k, v in sorted(eo.get(t, {}).items())},
            'union_diff': sorted(c for c in ep.get(t, {}) if c not in eo.get(t, {})),
            'prod_resid': {k: sorted(v) for k, v in sorted(rp.get(t, {}).items())},
            'orig_resid': {k: sorted(v) for k, v in sorted(ro.get(t, {}).items())},
            'prod_carried': dict(sorted(cp.get(t, {}).items())),
            'orig_carried': dict(sorted(co.get(t, {}).items())),
            'in_prod': t in prod,
            'in_orig': t in orig,
        }
        new = sorted(c for c in rec['prod_carried'] if c not in rec['orig_carried'])
        dif = sorted(c for c in rec['prod_carried']
                     if c in rec['orig_carried']
                     and rec['prod_carried'][c] != rec['orig_carried'][c])
        rec['hard_new'], rec['hard_diff'] = new, dif
        rows.append(rec)
        if new or dif:
            hard.append(rec)
    return rows, hard, pp


def main(argv=None):
    ap = argparse.ArgumentParser(description='跨脚本接缝闸')
    ap.add_argument('--product', default=os.path.join(ROOT, 'asset'))
    ap.add_argument('--orig-dir', default=None)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args(argv)

    odir = args.orig_dir or os.environ.get('IMHFD_ORIG_DIR') or paths.orig_dir()
    if not odir or not os.path.isdir(odir):
        sys.exit('需要原版目录：设环境变量 IMHFD_ORIG_DIR 或传 --orig-dir')

    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    scope = perfsync.seam_scope(plan['scripts'])
    decl = {}
    if os.path.exists(TABLE):
        decl = json.load(open(TABLE, encoding='utf-8')).get('scope') or {}

    prod, prod_bad = load_prod(os.path.join(args.product, 'Rio.arc'))
    ofmt = ws2conv.load_orig_formats(odir)
    orig, orig_bad = load_orig(os.path.join(odir, 'Rio.arc'), ofmt)

    rows, hard, prof = cmp_carried(prod, orig, scope)
    # 范围自检：结构枚举出的 scope 必须与入库表一致（表变了要重新定案）
    drift = []
    if decl:
        if sorted(decl) != sorted(scope):
            drift.append(('scope 成员', sorted(decl), sorted(scope)))
        else:
            for t in scope:
                r = next((x for x in rows if x['script'] == t), None)
                if r is None:
                    continue
                want = set(decl[t].get('hard_channels') or [])
                got = set(r['hard_new']) | set(r['hard_diff'])
                if want != got:
                    drift.append((t, sorted(want), sorted(got)))

    # ── 报告 ──
    L = ['# 跨脚本接缝闸（seam check）', '',
         '判据与适用范围见 `script/checks/seam_check.py` 文件头、'
         '`doc/restoration-route.md` §4.1。', '',
         '## 适用范围（结构枚举，%d 脚本）' % len(scope), '']
    for t in scope:
        kind = '整脚本回填' if plan['scripts'][t]['kind'] == 'whole' else '首改动槽位=0 的宿主'
        L.append('- `%s` —— %s' % (t, kind))
    L.append('')
    L.append('## 逐脚本三层读数')
    L.append('')
    for r in rows:
        L.append('### `%s`' % r['script'])
        L.append('')
        L.append('| 层 | 读数 |')
        L.append('|---|---|')
        L.append('| ① 并集差（诊断） | %s |' % (r['union_diff'] or '空'))
        L.append('| ② 残留（诊断） | 产物 %s ／ 原版 %s |'
                 % (r['prod_resid'] or '空', r['orig_resid'] or '空'))
        L.append('| ③ 携入（**缺陷判据**） | 产物 %s ／ 原版 %s |'
                 % (r['prod_carried'] or '空', r['orig_carried'] or '空'))
        L.append('')
        if r['hard_new'] or r['hard_diff']:
            L.append('**HARD**：')
            if r['hard_new']:
                L.append('- 产物携入、原版同脚本没有：`%s` %s'
                         % (r['hard_new'],
                            {c: r['prod_carried'][c] for c in r['hard_new']}))
            if r['hard_diff']:
                L.append('- 两侧都携入但图名不同：`%s` 产物 %s ／ 原版 %s'
                         % (r['hard_diff'],
                            {c: r['prod_carried'][c] for c in r['hard_diff']},
                            {c: r['orig_carried'][c] for c in r['hard_diff']}))
            L.append('')
        else:
            L.append('PASS（③ 空：前序残留没有一路留到首行）')
            L.append('')
        # 入边两侧状态（逐条带状态，便于人工核对「差集为何无害」）
        L.append('| 入边前序 | 前序末尾（产物） |')
        L.append('|---|---|')
        ins = [(pre, pf) for pre, pf in sorted(prof.items())
               if r['script'] in pf['jumps'] and pre != r['script']]
        for pre, pf in ins:
            L.append('| `%s` | %s |' % (pre, pf['end'] or '空'))
        if not ins:
            L.append('| （无产物侧入边） | — |')
        L.append('')
        L.append('目标前缀区接管通道：`%s`'
                 % sorted(prof[r['script']]['took'] if r['script'] in prof else set()))
        L.append('')

    L.append('## 结论')
    L.append('')
    L.append('- 范围（结构枚举）：%d 脚本' % len(scope))
    L.append('- ③ 携入 HARD：**%d** 脚本' % len(hard))
    L.append('- ①② 诊断非空：%d 脚本（见上表逐条读数）'
             % sum(1 for r in rows if r['union_diff'] or r['prod_resid']))
    L.append('- 范围 ⇄ 入库表漂移：%d' % len(drift))
    L.append('- 解析失败：产物 %d / 原版 %d' % (len(prod_bad), len(orig_bad)))
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L) + '\n')

    if not args.quiet:
        print('接缝范围（结构枚举 %d）：%s' % (len(scope), ', '.join(scope)))
        for r in rows:
            mark = 'HARD' if (r['hard_new'] or r['hard_diff']) else 'PASS'
            print(' %-5s %-12s ③携入=%-28s ①并集差=%-16s ②残留=%s'
                  % (mark, r['script'],
                     r['prod_carried'] or '-', r['union_diff'] or '-',
                     r['prod_resid'] or '-'))
        if drift:
            print()
            for t, want, got in drift:
                print(' HARD %-12s 入库表=%s 实算=%s' % (t, want, got))
        if prod_bad:
            print(' ! 产物解析失败：%s' % prod_bad[:5])
        if orig_bad:
            print(' ! 原版解析失败（内嵌数据表脚本，跨脚本边不可解析）：%s'
                  % [x[0] for x in orig_bad][:5])
        print()
        print('总结: 范围 %d / HARD %d / 表漂移 %d  →  %s'
              % (len(scope), len(hard), len(drift), REPORT))

    return 1 if (hard or drift) else 0


if __name__ == '__main__':
    sys.exit(main())
