"""三版本成员级比对（ORIG / STEAM / PATCH），按归档逐个输出。"""
import hashlib
import os
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


def three(name):
    paths = {'O': ORIG + '/' + name, 'S': STEAM + '/' + name, 'P': PATCH + '/' + name}
    data = {}
    for k, p in paths.items():
        data[k] = load(p) if os.path.exists(p) else None
    print('### %s' % name)
    for k in 'OSP':
        print('   %s: %s members' % (k, len(data[k]) if data[k] else 'N/A'))
    if not data['P']:
        print()
        return
    # 以 PATCH 为基准
    for other in ('O', 'S'):
        if not data[other]:
            continue
        a, b = data[other], data['P']
        onlyA = sorted(set(a) - set(b))
        onlyB = sorted(set(b) - set(a))
        diff = [k for k in set(a) & set(b) if a[k][2] != b[k][2]]
        print('   %s-vs-P: onlyIn%s=%d onlyInP=%d contentdiff=%d' % (other, other, len(onlyA), len(onlyB), len(diff)))
        if onlyA:
            print('      onlyIn%s: %s%s' % (other, ', '.join(a[k][0] for k in onlyA[:15]), ' ...' if len(onlyA) > 15 else ''))
        if onlyB:
            print('      onlyInP : %s%s' % (', '.join(b[k][0] for k in onlyB[:15]), ' ...' if len(onlyB) > 15 else ''))
    # 共同成员中 三版本都不同 的数量
    if data['O'] and data['S']:
        common = set(data['O']) & set(data['S']) & set(data['P'])
        allsame = sum(1 for k in common if data['O'][k][2] == data['S'][k][2] == data['P'][k][2])
        samesame = sum(1 for k in common if data['O'][k][2] != data['S'][k][2] and data['S'][k][2] == data['P'][k][2])
        print('   共同成员 %d：三者全同=%d，S==P(未改动)=%d' % (len(common), allsame, samesame))
    print()


if __name__ == '__main__':
    for n in sys.argv[1:]:
        three(n)
