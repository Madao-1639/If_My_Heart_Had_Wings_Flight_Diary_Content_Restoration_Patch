# -*- coding: utf-8 -*-
"""同名 CG 的「9XX 号段命名隔离」闸。

判据（用户 2026-10-27 定案，见 `tool/censormap.py` / `doc/resource-naming.md`）：
1. **成员齐备**：每个 `isolate` 条目在 `asset/<归档>` 里都有 9XX 成员，且字节 == 原版同名成员；
   同时**原名成员必须 == Steam 字节**（原名归 Steam 演绎路径）。
2. **引用归属**：9XX 名只允许被**产品侧**（A 路径 / 共享内容）引用；
   变体脚本的 **B 体（Steam 原生体）里不得出现 9XX 名**——那里必须用原名（Steam 画）。
3. **不留死成员**：每个 9XX 名至少被一个脚本引用（否则素材白加）。
4. **不改语义**：9XX 名与原名**等长**（同长度改名才不需要重定基）。

退出码 1 = 任一判据失败。
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, censormap, paths, variants, ws2, ws2dis  # noqa: E402


def members(p):
    try:
        return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(p)}
    except FileNotFoundError:
        return {}


def zone_fn(prod, sc, sp, dec):
    """产物内偏移 → 'A' / 'B' / 'shared'（与 variants.apply 的布局一致）。"""
    ins = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)[0]
    starts = [x[0] for x in ins]
    if sp['kind'] == 'choice':
        slots = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'),
                               encoding='utf-8'))[sc]
        tg = slots['variant']['targets']
        lo, hi, end = tg['brA'], tg['brB'], tg['conf']
    else:
        lo, hi, end = 0, struct.unpack_from('<I', dec, 12)[0], len(dec)

    def z(off):
        k = max(x for x in starts if x <= off)
        return 'A' if lo <= k < hi else ('B' if hi <= k < end else 'shared')
    return z


def main():
    iso, reset = censormap.load()
    if not iso:
        print('命名隔离：台账无 isolate 条目（无需处理）✅')
        return 0
    # 归档归属（censor_map.members 里带 archive）
    cm = json.load(open(os.path.join(ROOT, 'resource', 'censor_map.json'), encoding='utf-8'))
    arch_of = {m['name'].lower(): m['archive'] for m in cm.get('members') or []
               if m.get('isolate')}
    fails = []
    # ① 成员齐备 + ② 原名归 Steam
    by_arch = {}
    for low, iso_name in reset.items():
        by_arch.setdefault(arch_of[low], []).append((low, iso_name))
    for arch, items in sorted(by_arch.items()):
        a = members(os.path.join(ROOT, 'asset', arch))
        s = members(os.path.join(ROOT, 'backup', arch))
        o = members(os.path.join(paths.orig_dir(), arch))
        afold = {k.lower(): (k, v) for k, v in a.items()}
        sfold = {k.lower(): v for k, v in s.items()}
        ofold = {k.lower(): v for k, v in o.items()}
        for low, iso_name in items:
            if len(low) != len(iso_name):
                fails.append('%s：9XX 名与原名不等长（%s → %s）' % (arch, low, iso_name))
            if iso_name.lower() not in afold:
                fails.append('%s：缺隔离成员 %s' % (arch, iso_name))
            elif afold[iso_name.lower()][1] != ofold.get(low):
                fails.append('%s：隔离成员 %s != 原版同名成员字节' % (arch, iso_name))
            if low in afold and low in sfold and afold[low][1] != sfold[low]:
                fails.append('%s：原名成员 %s != Steam 字节（应归 Steam 演绎）' % (arch, low))
    # ③ 引用归属 + ④ 不留死成员
    prod = members(os.path.join(ROOT, 'asset', 'Rio.arc'))
    spec = variants.load()['scripts']
    by_steam = {sp['steam_file']: (sc, sp) for sc, sp in spec.items()}
    used = {k: 0 for k in iso}
    for n, raw in sorted(prod.items()):
        if not n.lower().endswith('.ws2'):
            continue
        dec = ws2.decode(raw)
        hit = by_steam.get(n)
        z = zone_fn(prod, *hit, dec) if hit else (lambda off: 'shared')
        ins = ws2dis.disassemble(dec, formats=ws2dis.FORMATS)[0]
        for off, op, _sz, ops in ins:
            if op not in (0x33, 0x34):
                continue
            parts = [x for x in ops.split(b'\x00') if x]
            if len(parts) < 2:
                continue
            nm = parts[1].decode('ascii', 'replace').upper()
            if nm not in iso:
                continue
            used[nm] += 1
            if hit and z(off) == 'B':
                fails.append('%s：B 体（Steam 原生体）里出现隔离名 %s @0x%x —— '
                             'Steam 演绎必须用原名（Steam 画）' % (n, nm, off))
    for nm, cnt in sorted(used.items()):
        if cnt == 0:
            fails.append('隔离名 %s 没有被任何脚本引用（死成员）' % nm)
    if fails:
        print('命名隔离闸: FAIL %d 项' % len(fails))
        for f in fails[:20]:
            print('  -', f)
        return 1
    print('命名隔离闸: PASS（%d 个隔离名；原名归 Steam 画、9XX 归产品侧、无 B 体误用、无死成员）'
          % len(iso))
    for nm, cnt in sorted(used.items()):
        print('   %-22s ← %s  引用 %d 处' % (nm, iso[nm], cnt))
    return 0


if __name__ == '__main__':
    sys.exit(main())
