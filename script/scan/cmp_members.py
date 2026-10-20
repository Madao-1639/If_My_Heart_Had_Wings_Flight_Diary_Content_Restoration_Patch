"""成员级比对：给定两个 arc，输出 名字集合差异 + 同名成员内容差异（按 sha1）。"""
import hashlib
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
from galrev.advhd import arc

ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'


def name_of(nb):
    for enc in ('utf-16le', 'shift_jis', 'utf-8'):
        try:
            s = nb.decode(enc)
            if s and all(ord(c) >= 32 for c in s):
                return s
        except Exception:
            pass
    return repr(nb)


def load(path):
    out = {}
    for nb, data in arc.read_raw(path):
        out[name_of(nb).lower()] = (name_of(nb), len(data), hashlib.sha1(data).hexdigest())
    return out


def cmp(label, ap, bp, show_only=25):
    a, b = load(ap), load(bp)
    oa = sorted(set(a) - set(b))
    ob = sorted(set(b) - set(a))
    both = sorted(set(a) & set(b))
    diff = [k for k in both if a[k][2] != b[k][2]]
    print('### %s' % label)
    print('  A=%d B=%d | onlyA=%d onlyB=%d contentdiff=%d' % (len(a), len(b), len(oa), len(ob), len(diff)))
    if oa:
        print('  onlyA: %s%s' % (', '.join(a[k][0] for k in oa[:show_only]), ' ...' if len(oa) > show_only else ''))
    if ob:
        print('  onlyB: %s%s' % (', '.join(b[k][0] for k in ob[:show_only]), ' ...' if len(ob) > show_only else ''))
    if diff:
        print('  diff : %s%s' % (', '.join(a[k][0] for k in diff[:show_only]), ' ...' if len(diff) > show_only else ''))
    print()


if __name__ == '__main__':
    fn = sys.argv[1]
    if fn == 'chip':
        for c in ('Chip1.arc', 'Chip2.arc', 'Chip7.arc', 'Chip8.arc', 'Chip9.arc', 'Chip10.arc'):
            import os
            if not os.path.exists(os.path.join(PATCH, c)):
                print('### %s (patch 无)' % c)
                continue
            cmp('%s  ORIG vs PATCH' % c, ORIG + '/' + c, PATCH + '/' + c)
    elif fn == 'voice':
        cmp('Voice.arc ORIG vs STEAM', ORIG + '/Voice.arc', STEAM + '/Voice.arc')
        cmp('Voice.arc STEAM vs PATCH', STEAM + '/Voice.arc', PATCH + '/Voice.arc')
    elif fn == 'graphic':
        cmp('Graphic.arc ORIG vs STEAM', ORIG + '/Graphic.arc', STEAM + '/Graphic.arc')
        cmp('Graphic.arc STEAM vs PATCH', STEAM + '/Graphic.arc', PATCH + '/Graphic.arc')
    elif fn == 'rio':
        cmp('Rio.arc STEAM vs PATCH', STEAM + '/Rio.arc', PATCH + '/Rio.arc')
    elif fn == 'rio1':
        cmp('Rio1.arc STEAM vs PATCH', STEAM + '/Rio1.arc', PATCH + '/Rio1.arc')
