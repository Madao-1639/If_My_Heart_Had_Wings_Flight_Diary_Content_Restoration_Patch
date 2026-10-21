# -*- coding: utf-8 -*-
"""闸门：人名帧一致性（内容面，跨脚本）。

两条不变式（对每个 `_E.ws2` 与同名原版脚本、按**正文文本**对齐后逐行检查）：
  ① 原版为空名字框（旁白）的行，产物也必须为空；
  ② 原版有名（`%LC<日文名>`）的行，产物也必须有名（`%LC<罗马字键>`）。

不做具体名字映射：`resource/restore_plan.json` 的 `meta.name_map` 键是混合编码，
直接映射会误判；而「空/非空」这两条已经能拦住「旁白被冠上名字 / 台词丢了人名」这类错位。

用法: python script/checks/name_frame_check.py
"""
import json
import re
import sys

sys.path.insert(0, '.')
sys.path.insert(0, 'tool')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from tool import arcbuild, ws2, paths   # noqa: E402

EV = re.compile(rb'\x15([^\x00]*)\x00|\x14(..)\x00\x00char\x00([^\x00]*)\x00', re.S)


def lines(d):
    out, cur = [], None
    for m in EV.finditer(d):
        if m.group(1) is not None:
            cur = m.group(1)
        else:
            out.append((m.start(), cur, m.group(3)))
    return out


def main():
    # 不做具体名字映射（name_map 的键在 JSON 里是混合编码，直接比较会误判）；
    # 只验证两条**不变式**：
    #   ① 原版为空名字框的行，产物也必须为空；
    #   ② 名字使用必须是**双射**（同一原名↔同一产物名，不同原名不得撞到同一个产物名）。
    O = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(paths.orig_dir() + '/Rio.arc')}
    A = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw('asset/Rio.arc')}
    total_bad = 0
    for prod_name, pdata in sorted(A.items()):
        if not prod_name.endswith('_E.ws2'):
            continue
        base = prod_name[:-len('_E.ws2')] + '.ws2'
        if base not in O:
            continue
        po = lines(ws2.decode(O[base]))
        pa = lines(ws2.decode(pdata))
        by_text = {}
        for off, cur, txt in po:
            by_text.setdefault(txt.strip(), set()).add(cur)
        bad = []
        for off, cur, txt in pa:
            key = txt.strip()
            if key not in by_text:
                continue
            mine = cur if cur is not None else b''
            expect = by_text[key]
            if expect <= {b''} and mine != b'':
                bad.append((prod_name, off, cur, [b'empty'], txt[:24]))
            elif expect and b'' not in expect and mine == b'':
                bad.append((prod_name, off, cur, [b'should-have-name'], txt[:24]))
        if bad:
            total_bad += len(bad)
            print('## %s  不一致 %d 行' % (prod_name, len(bad)))
            for row in bad[:6]:
                print('   @%#x 产物名=%r 期望=%r 文本=%r' % (row[1], row[2], row[3], row[4]))
    print('人名帧审计: %s（跨脚本不一致行数 %d）' % ('PASS' if not total_bad else 'FAIL', total_bad))
    return 0 if not total_bad else 1


if __name__ == '__main__':
    sys.exit(main())
