"""核对国外还原补丁的每一处改动：该处是否真是原版↔Steam 的语义分歧点，改动是否还原了原版。

对 Steam 与 PATCH 都能用本作格式表 100% 反汇编 ⇒ 逐脚本比指令结构；
ORIG 用正则统计（其引擎版本不同，格式表不通用）。
"""
import re
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
                   'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tool')
from galrev.advhd import arc, ws2
import ws2fmt

ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'

TARGETS = ['AFT_003', 'AFT_007_3', 'BEF_003', 'BEF_004', 'HOT_002', 'HOT_004', 'HUS_001',
           'KAN_3001_3', 'KAN_3001_4', 'KAN_3002_1', 'CG_PAGE01', 'CG_PAGE02',
           'CG_PAGE03', 'CG_PAGE04', 'AGS_001', 'KAN_3002_2']


def load(root, arcname='Rio.arc'):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(root + '/' + arcname)}


def stats(dec, name):
    """返回 (可反汇编?, {op: 次数}, 跳转表)。不可反汇编时退化为正则计数。"""
    try:
        ins = ws2fmt.disassemble(dec)
        c = {}
        jumps = []
        for off, op, sz, f in ins:
            c[op] = c.get(op, 0) + 1
            if op == 0x07:
                jumps.append(f['args'][0])
            if op == 0x0f:
                jumps.append('CHOICE(%s)' % f['args'])
        return True, c, jumps
    except ws2fmt.Bad:
        c = {}
        for op in (0x14, 0x0f, 0x2e, 0x04, 0x07, 0x34, 0x33, 0x39):
            c[op] = len(re.findall(bytes([op]), dec))
        return False, c, []


def main():
    o, s, p = load(ORIG), load(STEAM), load(PATCH)
    print('%-12s %-28s %-28s %s' % ('script', 'ORIG(regex)', 'STEAM(disasm)', 'PATCH(disasm)'))
    for t in TARGETS:
        for suf, tag in (('.ws2', 'orig'), ('_E.ws2', 'steam')):
            pass
        # 三侧文件名
        on = t + '.ws2'
        sn = t + '_E.ws2'
        pn = t + '_E.ws2' if t + '_E.ws2' in p else t + '.ws2'
        if on not in o and sn not in s:
            print('%-12s -- 跳过（不在原版/Steam）' % t)
            continue
        ro = stats(ws2.decode(o[on]), on) if on in o else (None, {}, [])
        rs = stats(ws2.decode(s[sn]), sn) if sn in s else (None, {}, [])
        rp = stats(ws2.decode(p[pn]), pn) if pn in p else (None, {}, [])
        def fmt(r):
            ok, c, j = r
            return '0x14=%s 0x0f=%s 0x2e=%s 0x34=%s%s' % (
                c.get(0x14, '-'), c.get(0x0f, '-'), c.get(0x2e, '-'), c.get(0x34, '-'),
                '' if ok else ' [regex]')
        print('%-12s %-28s %-28s %s' % (t, fmt(ro), fmt(rs), fmt(rp)))
        if rs[2] != rp[2]:
            print('      JUMP: STEAM=%s' % rs[2])
            print('      JUMP: PATCH=%s' % rp[2])
        print()


if __name__ == '__main__':
    main()
