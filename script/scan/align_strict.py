"""英文行↔原版行 的严格对齐：用**精确文本匹配**做锚点（LCS），
在锚点之间检查 ORIG↔PATCH 是否 1:1（EN 译行），并报出插入/删除。

输出：每脚本
  - 锚点数（JP 逐字相同的行）
  - 锚点间区段的 (ORIG 行数, PATCH 行数)；不等 ⇒ 存在插入/删除
  - 插入/删除的具体位置与内容（供判断是否需要人工对齐）
"""
import json
import os
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
                   'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tool')
from galrev.advhd import arc, ws2
import ws2fmt

PATCHDIR = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
            'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'
OUT = PATCHDIR + '/tmp/align_en'

TO = ws2fmt.Table(PATCHDIR + '/resource/ws2_formats_orig.json')
TF = ws2fmt.Table(PATCHDIR + '/resource/ws2_formats.json')
# BEF_004 用混合表（原版表未定义 0x5f/0x80）
TM = ws2fmt.Table.__new__(ws2fmt.Table)
TM.fmt = dict(TO.fmt)
for op in (0x5f, 0x80):
    if op in TF.fmt:
        TM.fmt[op] = TF.fmt[op]

TARGETS = ['AFT_003', 'AFT_007_3', 'BEF_003', 'BEF_004', 'HOT_002', 'HOT_004', 'HUS_001',
           'KAN_3001_3', 'KAN_3001_4', 'KAN_3002_2', 'AGS_001']
_JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')


def load(root, an):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(root + '/' + an)}


def lines(dec, tab):
    out, cur = [], ''
    for off, op, sz, f in ws2fmt.disassemble(dec, tab):
        if op == 0x15:
            a = f.get('args') or []
            s = a[0] if a and isinstance(a[0], str) else ''
            cur = s[3:] if s.startswith('%LC') else ''
        elif op == 0x14:
            a = f.get('args') or []
            t = ''
            for x in a:
                if isinstance(x, str) and not x.startswith('%LC'):
                    t = x
            out.append((off, cur, t))
    return out


def isjp(s):
    return bool(_JP.search(s))


def norm(s):
    """去掉控制标记后用于锚点匹配（%K/%P/\\d 等保留会妨碍匹配时可选）。"""
    return s


def main():
    os.makedirs(OUT, exist_ok=True)
    o, p = load(ORIG, 'Rio.arc'), load(PATCH, 'Rio.arc')
    report = []
    for t in TARGETS:
        on, pn = t + '.ws2', (t + '.ws2' if t + '.ws2' in p else t + '_E.ws2')
        if on not in o or pn not in p:
            report.append((t, 'N/A', None))
            continue
        try:
            lo = lines(ws2.decode(o[on]), TM if t == 'BEF_004' else TO)
        except ws2fmt.Bad as e:
            report.append((t, 'ORIG 反汇编失败: %s' % e, None))
            continue
        lp = lines(ws2.decode(p[pn]), TF)
        A = [x[2] for x in lo]
        B = [x[2] for x in lp]
        sm = SequenceMatcher(None, A, B, autojunk=False)
        blocks = sm.get_matching_blocks()
        anchors = sum(b.size for b in blocks if b.size > 0)
        # 逐段检查
        segs = []
        prev_a = prev_b = 0
        for b in blocks:
            ga, gb = b.a - prev_a, b.b - prev_b
            if ga or gb:
                segs.append((prev_a, ga, prev_b, gb))
            prev_a, prev_b = b.a + b.size, b.b + b.size
        bad = [s for s in segs if s[1] != s[3]]
        report.append((t, 'OK' if not bad else 'MISMATCH', {
            'orig': len(A), 'patch': len(B), 'anchors': anchors,
            'segs': len(segs), 'bad_segs': bad[:6]}))
        print('=== %s ===' % t)
        print('  ORIG %d 行 / PATCH %d 行 / 锚点(逐字相同) %d' % (len(A), len(B), anchors))
        print('  锚点间区段 %d 个，其中 ORIG↔PATCH 行数不等的 %d 个' % (len(segs), len(bad)))
        for a0, ga, b0, gb in bad[:6]:
            print('    ORIG[%d:%d](%d) ↔ PATCH[%d:%d](%d)' % (a0, a0 + ga, ga, b0, b0 + gb, gb))
            for x in range(a0, min(a0 + ga, a0 + 3)):
                print('       ORIG %s' % A[x][:46])
            for y in range(b0, min(b0 + gb, b0 + 3)):
                print('       PATCH %s' % B[y][:46])
        print()
    with open(os.path.join(OUT, 'align_report.json'), 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
