# -*- coding: utf-8 -*-
"""跨脚本接缝表生成器（产出端脚本）。

产出 `resource/seam_scope.json`：**跨脚本接缝的适用范围 + 逐脚本实测读数**。
判据与机制见 [doc/restoration-route.md](../../doc/restoration-route.md) §4.2、
`tool/perfsync.py`「跨脚本接缝」段；消费方 `script/checks/seam_check.py` 与
`script/final_verification.py` 4c。

为什么要有这张表
----------------
接缝的**范围**必须按结构枚举（`kind=whole` 整脚本回填 ∪ 首个改动槽位为 0 的宿主），
不能按「哪里测出残留」反推——按缺陷反推等于把筛子钉在已知缺陷上，换一处形态就静默漏检。
**判据用实测差集、范围用结构定义，两者分开**；表把两者都登记下来，好让「范围或定案
被改了却没重定案」当场报 HARD，而不是静默放行。

三层判据（逐层收窄；①② 只作诊断，③ 才是缺陷口径）
--------------------------------------------------
    ① 并集差 = ∪{前序末尾通道}(产物) − ∪{前序末尾通道}(原版)
    ② 残留   = 前序末尾通道中、目标**前缀区**（首条 `0x14` 之前）未被接管的
    ③ 携入   = 残留中、其值**原样活到目标首行**的              ← 缺陷（HARD）

`hard_channels` = 产物 ③ − 原版 ③（原版同脚本也携入同值 ⇒ 版本差，不算本项目的缺陷）。

输入
----
* `asset/Rio.arc`  —— 产物脚本（Steam 格式表）
* `backup/Rio.arc` —— 不需要；本表只比「产物 vs 原版」
* 原版发行目录（`--orig-dir` 或 `IMHFD_ORIG_DIR`，缺省 `tool.paths.orig_dir()`）——
  取原版 `Rio.arc` 与 `AdvHD.exe` 格式表
* `resource/restore_plan.json` —— 结构枚举范围的来源（`kind` / `inserts` / `drops` / `perf_sync`）

**幂等**：重复运行产出逐字节相同（不含时间戳等易变量）。
用法
----
    python script/build/build_seam_scope.py [--asset DIR] [--orig-dir DIR] [--emit PATH]
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

from tool import paths, perfsync, ws2conv  # noqa: E402

OUT = os.path.join(ROOT, 'resource', 'seam_scope.json')

NOTE = ('跨脚本接缝的适用范围与实测结论（产出端 script/build/build_seam_scope.py，'
        '消费方 script/checks/seam_check.py 与 script/final_verification.py 4c）。'
        '适用范围按**结构枚举**（why=whole 整脚本回填 ∪ why=head_slot0 首个改动槽位为 0 的宿主），'
        '不按「哪里测出残留」反推——按缺陷反推等于把筛子钉在已知缺陷上，换一处形态就静默漏检。'
        '字段分工：union_diff／residual 是诊断量（前序末尾不同 ≠ 玩家看得到差别，同一通道会被'
        '目标前缀区的显示覆盖）；carried／orig_carried 是缺陷判据的原料（前序残留原样活到'
        '目标首行），hard_channels = 产物 carried − 原版 carried 的定案值。'
        '**空集也列**：区分「查过且为空」与「没查」。')


def _why(plan_rec):
    """该脚本进 scope 的结构理由（与 `perfsync.seam_scope` 的枚举条件一一对应）。"""
    if plan_rec.get('kind') == 'whole':
        return 'whole'
    return 'head_slot0'


def build(asset_dir, odir):
    """→ (表 dict, 范围 list, 行 list)。不写盘。"""
    import importlib.util as ilu
    sp = ilu.spec_from_file_location(
        'seam_check', os.path.join(ROOT, 'script', 'checks', 'seam_check.py'))
    sx = ilu.module_from_spec(sp)
    sp.loader.exec_module(sx)          # 复用同一套载入/比对实现，避免口径漂移

    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    scope = perfsync.seam_scope(plan['scripts'])
    prod, prod_bad = sx.load_prod(os.path.join(asset_dir, 'Rio.arc'))
    ofmt = ws2conv.load_orig_formats(odir)
    orig, orig_bad = sx.load_orig(os.path.join(odir, 'Rio.arc'), ofmt)
    assert not prod_bad, '产物脚本线性解析失败：%r' % (prod_bad[:3],)
    rows, _hard, prof = sx.cmp_carried(prod, orig, scope, sx.canon)

    scripts = {}
    for r in rows:
        t = r['script']
        scripts[t] = {
            'why': _why(plan['scripts'][t]),
            'entry_sources': sorted(pre for pre, pf in prof.items()
                                    if t in pf['jumps'] and pre != t),
            'union_diff': r['union_diff'],
            'residual': r['prod_resid'],
            'carried': r['prod_carried'],
            'orig_carried': r['orig_carried'],
            'hard_channels': sorted(set(r['hard_new']) | set(r['hard_diff'])),
        }
    table = {'note': NOTE, 'scope': scripts}
    return table, scope, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description='跨脚本接缝表生成器')
    ap.add_argument('--asset', default=os.path.join(ROOT, 'asset'))
    ap.add_argument('--orig-dir', default=None)
    ap.add_argument('--emit', default=OUT)
    args = ap.parse_args(argv)

    odir = args.orig_dir or os.environ.get('IMHFD_ORIG_DIR') or paths.orig_dir()
    if not odir or not os.path.isdir(odir):
        sys.exit('需要原版目录：设环境变量 IMHFD_ORIG_DIR 或传 --orig-dir')

    table, scope, rows = build(args.asset, odir)
    with open(args.emit, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(table, fh, ensure_ascii=False, indent=1)
        fh.write('\n')

    hard = [r['script'] for r in rows
            if r['hard_new'] or r['hard_diff']]
    n_diag = sum(1 for r in rows if r['union_diff'] or r['prod_resid'])
    print('写出 %s' % args.emit)
    print('范围 %d 脚本：%s' % (len(scope), ', '.join(scope)))
    print('③ 携入 HARD %d；①② 诊断非空 %d' % (len(hard), n_diag))
    for r in rows:
        print('  %-12s ③=%-26s ①=%-16s ②=%s'
              % (r['script'], r['prod_carried'] or '-', r['union_diff'] or '-',
                 r['prod_resid'] or '-'))
    if hard:
        print('⚠️ ③ 非空：%s —— 还原内容在头部落座而宿主首条显示不接管前序通道，'
              '须让还原块自带清屏或在头部插 `37 <通道>`（见 route §4.2）' % hard)
    return 1 if hard else 0


if __name__ == '__main__':
    sys.exit(main())
