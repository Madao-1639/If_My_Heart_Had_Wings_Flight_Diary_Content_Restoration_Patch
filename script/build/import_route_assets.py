# -*- coding: utf-8 -*-
"""把「只能从原版发行版取得」的二进制素材导入 `resource/route_entry/`（一次性 / 可重跑）。

**为什么要这一步**：`backup/`（Steam 基线）里没有这些图层（被删/被替换），它们的唯一
来源是**外部原版发行目录**（`tool.paths.orig_dir()`）。若让 `build_route_entry.py` 直接读
原版目录，构建就依赖一个可能不存在的仓库外路径。因此把它们落成 `resource/` 里的显式输入，
构建只读 `resource/`；本脚本负责「原版目录 → resource」的重建（幂等、逐字节保真）。

产物（规格见 `resource/route_entry.json`）：

| 文件 | 原版来源 | 用途 |
|---|---|---|
| `cast_highlight_ags.png` | 原版 `SysGraphic.arc` → `SYS_Story.pna` 记录 **23** | 角色高亮 Cast 图（AGS/姫城姉妹） |
| `base_entry_ags_on.png` | 同上 记录 **7** | base（英/默认）UI 第 8 个入口的亮态 |
| `base_entry_ags_def.png` | 同上 记录 **8** | 同上的暗态 |

用法：`python script/build/import_route_assets.py [--check]`
  - 默认：从原版目录重建 `resource/route_entry/*.png`；
  - `--check`：只校验 `resource/` 里的现有文件与原版逐字节一致（不写）。
"""
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

from tool import paths  # noqa: E402

sys.path.insert(0, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev'))
from galrev.advhd import arc, pna  # noqa: E402

RESOURCE = os.path.join(ROOT, 'resource')

def res_path(name):
    """规格里的路径相对 `resource/`。"""
    return os.path.join(RESOURCE, name.replace('/', os.sep))


def member(members, name):
    for n, d in members:
        if n.decode('utf-16le') == name:
            return d
    raise KeyError(name)


def plan(spec):
    """[(资源文件名, 原版归档, 原版 PNA 成员, 记录下标)]"""
    out = []
    cast = spec.get('cast_highlight')
    if cast:
        s = cast['source']
        out.append((cast['resource_file'], s['archive'], s['pna_member'], s['record']))
    base = spec.get('base_ui_entry')
    if base:
        s = base['source']
        for tag in ('on', 'def'):
            out.append((base['resource_files'][tag], s['archive'], s['pna_member'], s['records'][tag]))
    return out


def main(argv):
    check_only = '--check' in argv
    spec = json.load(open(os.path.join(ROOT, 'resource', 'route_entry.json'), encoding='utf-8'))
    src_dir = paths.orig_dir()
    cache = {}
    os.makedirs(os.path.dirname(res_path(plan(spec)[0][0])), exist_ok=True)
    bad = 0
    for name, archive, pna_member, record in plan(spec):
        key = (archive, pna_member)
        if key not in cache:
            members = arc.read_raw(os.path.join(src_dir, archive))
            cache[key] = pna.parse(member(members, pna_member))
        want = cache[key].layers[record].data
        if want is None:
            raise SystemExit('原版 %s 记录 %d 没有图像数据' % (pna_member, record))
        dst = res_path(name)
        if check_only:
            got = open(dst, 'rb').read() if os.path.exists(dst) else None
            ok = got == want
            print('%s %-28s <- %s 记录 %d' % ('[OK]  ' if ok else '[DIFF]', name, pna_member, record))
            bad += 0 if ok else 1
            continue
        # 幂等：内容相同就不重写（保留 mtime）
        if os.path.exists(dst) and open(dst, 'rb').read() == want:
            print('[skip] %-28s 已是最新（%d B）' % (name, len(want)))
            continue
        with open(dst, 'wb') as fh:
            fh.write(want)
        print('[ok]   %-28s <- %s 记录 %d（%d B）' % (name, pna_member, record, len(want)))
    if check_only:
        if bad:
            raise SystemExit('%d 个文件与原版不一致' % bad)
        print('resource 素材与原版逐字节一致。')


if __name__ == '__main__':
    main(sys.argv[1:])
