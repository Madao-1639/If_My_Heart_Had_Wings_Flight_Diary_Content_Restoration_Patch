"""L4 素材补齐构建器 —— Voice / Chip7 / Chip8 / Chip9 并集归档。

还原的 H 场景引用了**原版才有的语音/素材**，必须随包发布，否则还原场景静音/缺图。
本脚本对四个归档产出 `asset/<同名>.arc`：

  Voice.arc   Steam 全部成员 + 原版独有成员（并集）
  Chip7.arc   同上
  Chip8.arc   同上
  Chip9.arc   同上

规则（用户决策）：
  * **同名成员一律保留 Steam 的字节**：两版同名内容实测 99.97% 相同，差异是重编码
    噪声，不动（见 AGENTS.md §工程约定 5 / doc/resource-naming.md）。
  * 原版独有成员里扩展名为 `.MOS` 的**跳过**，不补入。
  * **只在确有差异时才写**：并集结果与 `backup/` 同名归档逐字节相同则不落盘
    （`asset/` 只放相对 backup 有差异的文件）。
  * 成员顺序 = Steam 原序在前，原版独有成员按原版原序追加在后 ⇒ 输出确定、幂等。

机制/依据：doc/restoration-targets.md、doc/resource-naming.md。
素材来源：`backup/`（Steam 只读基线）+ `paths.orig_dir()`（原版发行目录）。
"""
import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
# 引擎逆向库（ARC 读写保留成员名原始字节、相对偏移）：GalRevserse/GalRev 与
# 本作目录同级，相对推导，避免硬编码绝对路径。
sys.path.insert(0, str(BASE.parents[1] / 'GalRevserse' / 'GalRev'))

from galrev.advhd import arc  # noqa: E402
from tool import paths  # noqa: E402

OUT_DIR = BASE / 'asset'
ARCHIVES = ['Voice.arc', 'Chip7.arc', 'Chip8.arc', 'Chip9.arc']


def name_str(nb):
    """归档成员名按 UTF-16LE 解码（磁盘原始字节，未被文件系统改写）。"""
    return nb.decode('utf-16-le')


def build_one(archive_name, orig_dir):
    """构建单个归档并回读校验，返回统计 dict（未写盘时 wrote=False）。"""
    steam_members = arc.read_raw(Path(paths.STEAM) / archive_name)
    orig_members = arc.read_raw(Path(orig_dir) / archive_name)
    steam_names = {name_str(nb) for nb, _ in steam_members}

    out = list(steam_members)
    added = []          # 实际补入的原版独有成员 [(name_bytes, data)]
    skipped_mos = 0
    for nb, data in orig_members:
        n = name_str(nb)
        if n in steam_names:
            continue        # 同名：保留 Steam 字节
        if Path(n).suffix.lower() == '.mos':
            skipped_mos += 1
            continue        # .MOS：用户决策跳过
        out.append((nb, data))
        added.append((nb, data))

    stat = dict(archive=archive_name, steam=len(steam_members),
                orig=len(orig_members), union=len(out),
                added=len(added), skipped_mos=skipped_mos, wrote=False, size=0)

    if not added:
        # 无原版独有成员 ⇒ 并集逐字节等于 backup，不写盘。
        return stat

    out_path = OUT_DIR / archive_name
    arc.write_arc(out, out_path)
    arc.verify(out_path, expect_count=len(out))

    # 回读校验：成员数 == 并集数；Steam 成员字节与 backup 同名成员逐字节相同；
    # 原版独有成员字节与原版同名成员逐字节相同。
    got = {name_str(nb): data for nb, data in arc.read_raw(out_path)}
    assert len(got) == len(out), '%s: member count %d != union %d' % (
        archive_name, len(got), len(out))
    for nb, data in steam_members:
        assert got[name_str(nb)] == data, '%s: steam member altered: %s' % (
            archive_name, name_str(nb).encode('unicode_escape').decode())
    for nb, data in added:
        assert got[name_str(nb)] == data, '%s: added member differs: %s' % (
            archive_name, name_str(nb).encode('unicode_escape').decode())

    stat['wrote'] = True
    stat['size'] = out_path.stat().st_size
    return stat


def build(orig_dir):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for a in ARCHIVES:
        s = build_one(a, orig_dir)
        tag = 'WROTE' if s['wrote'] else 'SKIP (identical to backup)'
        print('%-10s steam=%-6d orig=%-6d union=%-6d added=%-5d '
              'skip.mos=%-4d size=%-10d %s'
              % (s['archive'], s['steam'], s['orig'], s['union'],
                 s['added'], s['skipped_mos'], s['size'], tag))
        sys.stdout.flush()
    print('L4 assets done -> %s' % OUT_DIR)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(
        description='L4 素材补齐：Voice/Chip7/Chip8/Chip9 并集归档')
    ap.add_argument('--orig-dir',
                    help='原版发行目录（缺省用 tool.paths.orig_dir() 自动发现）')
    a = ap.parse_args()
    orig = Path(a.orig_dir) if a.orig_dir else Path(paths.orig_dir())
    if not orig.is_dir():
        sys.exit('原版目录不存在: %s' % orig)
    build(orig)
