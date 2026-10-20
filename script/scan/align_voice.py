"""语音锚点对齐：用 `0x28 char*`（语音）作为锚，建立 ORIG 行 ↔ PATCH 行的**逐行映射**，
并报出锚点之间行数不等的区间（即"位置对齐不可靠、需要语义对齐"的位置）。

绑定关系（实测）：`0x28 charXXX <VOICE.OGG> …` → `0x15 %LC<名>` → `0x14 <台词>`
"""
import json
import os
import re
import sys

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


def rows(dec, tab):
    """返回 [(off, name, text, voice)]，voice 为紧邻其前的 `0x28 char*` 的 OGG 名（无则 None）。"""
    out, cur, pending = [], '', None
    for off, op, sz, f in ws2fmt.disassemble(dec, tab):
        a = f.get('args') or []
        if op == 0x28:
            slot = a[0] if a and isinstance(a[0], str) else ''
            ogg = ''
            for x in a:
                if isinstance(x, str) and x.upper().endswith('.OGG'):
                    ogg = x
            pending = ogg if slot.startswith('char') and ogg else None
        elif op == 0x15:
            s = a[0] if a and isinstance(a[0], str) else ''
            cur = s[3:] if s.startswith('%LC') else ''
        elif op == 0x14:
            t = ''
            for x in a:
                if isinstance(x, str) and not x.startswith('%LC') and not x.endswith('.OGG') \
                        and x not in ('char',):
                    t = x
            out.append((off, cur, t, pending))
            pending = None
        elif op in (0x33, 0x34, 0x39, 0x46, 0x47, 0x48, 0x65):
            pass
    return out


def isjp(s):
    return bool(_JP.search(s))


def main():
    os.makedirs(OUT, exist_ok=True)
    o, p = load(ORIG, 'Rio.arc'), load(PATCH, 'Rio.arc')
    summary = []
    for t in TARGETS:
        on, pn = t + '.ws2', (t + '.ws2' if t + '.ws2' in p else t + '_E.ws2')
        if on not in o or pn not in p:
            print('%-12s N/A' % t)
            continue
        try:
            lo = rows(ws2.decode(o[on]), TM if t == 'BEF_004' else TO)
        except ws2fmt.Bad as e:
            print('%-12s ORIG 失败 %s' % (t, e))
            continue
        lp = rows(ws2.decode(p[pn]), TF)
        vo = [i for i, r in enumerate(lo) if r[3]]
        vp = [i for i, r in enumerate(lp) if r[3]]
        # 语音名逐位是否一致
        so = [lo[i][3].upper() for i in vo]
        sp = [lp[i][3].upper() for i in vp]
        same = so == sp
        # 锚点区间：以语音行下标为锚，检查区间内 ORIG/PATCH 行数
        gaps = []
        a = b = -1
        for k in range(max(len(vo), len(vp))):
            ai = vo[k] if k < len(vo) else len(lo)
            bi = vp[k] if k < len(vp) else len(lp)
            na, nb = ai - a - 1, bi - b - 1
            if na != nb:
                gaps.append((a + 1, na, b + 1, nb))
            a, b = ai, bi
        summary.append({'script': t, 'orig_lines': len(lo), 'patch_lines': len(lp),
                        'orig_voiced': len(vo), 'patch_voiced': len(vp),
                        'voice_seq_same': same, 'gap_mismatch': gaps})
        print('=== %s ===' % t)
        print('  ORIG %d 行（有语音 %d）/ PATCH %d 行（有语音 %d）/ 语音序列逐位一致=%s'
              % (len(lo), len(vo), len(lp), len(vp), same))
        if gaps:
            print('  ⚠️ 锚点之间行数不等的区间 %d 处（位置对齐不可靠）：' % len(gaps))
            for g in gaps[:8]:
                print('     ORIG[%d..](%d 行) ↔ PATCH[%d..](%d 行)' % (g[0], g[1], g[2], g[3]))
                for x in range(g[0], min(g[0] + g[1], g[0] + 2)):
                    print('        ORIG %s' % lo[x][2][:44])
                for y in range(g[2], min(g[2] + g[3], g[2] + 2)):
                    print('        PATCH %s' % lp[y][2][:44])
        else:
            print('  ✅ 所有锚点区间 ORIG↔PATCH 行数相等 ⇒ 位置对齐成立')
        print()
    with open(os.path.join(OUT, 'voice_anchor.json'), 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
