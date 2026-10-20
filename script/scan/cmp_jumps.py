"""对比 Steam 与 PATCH 的剧本跳转差异（只看 0x07 JUMP / 0x04 CALL 中的剧本名）。"""
import re
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
from galrev.advhd import arc, ws2

STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'

J = re.compile(rb'\x07([A-Za-z0-9_]+)\x00')


def members(path):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(path)}


def jumps(d):
    return [m.group(1).decode('ascii') for m in J.finditer(ws2.decode(d)) if m.group(1).decode('ascii') != 'EVRET']


if __name__ == '__main__':
    s = members(STEAM + '/Rio.arc')
    p = members(PATCH + '/Rio.arc')
    names = sys.argv[1:] if len(sys.argv) > 1 else sorted(set(s) & set(p))
    for n in names:
        js, jp = jumps(s[n]), jumps(p[n])
        same = js == jp
        print('%-20s S=%d P=%d %s' % (n, len(s[n]), len(p[n]), 'SAME-JUMPS' if same else 'DIFF-JUMPS'))
        if not same:
            print('    S:', js)
            print('    P:', jp)
