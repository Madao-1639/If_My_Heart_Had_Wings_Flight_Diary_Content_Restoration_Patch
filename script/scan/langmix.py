"""提取 ws2 中所有 >=4 字符的可读串（CP932），分类 JP / ASCII。"""
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
from galrev.advhd import arc, ws2

STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'
ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'


def strings(dec, minlen=4):
    out, cur = [], bytearray()
    for b in dec:
        if b == 0:
            if len(cur) >= minlen:
                out.append(bytes(cur))
            cur = bytearray()
        else:
            cur.append(b)
    if len(cur) >= minlen:
        out.append(bytes(cur))
    res = []
    for s in out:
        try:
            res.append(s.decode('cp932'))
        except Exception:
            pass
    return res


def classify(lst):
    jp, en = [], []
    for t in lst:
        if any('\u3040' <= c <= '\u9fff' for c in t):
            jp.append(t)
        elif sum(1 for c in t if c.isascii() and c.isalpha()) >= 6:
            en.append(t)
    return jp, en


def members(path):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(path)}


if __name__ == '__main__':
    arcname = sys.argv[1]
    targets = sys.argv[2:]
    for tag, root in (('ORIG', ORIG), ('STEAM', STEAM), ('PATCH', PATCH)):
        ms = members(root + '/' + arcname)
        for t in targets:
            key = [k for k in ms if k.lower() == t.lower()]
            if not key:
                continue
            jp, en = classify(strings(ws2.decode(ms[key[0]])))
            print('%-6s %-22s jp=%-4d en=%-4d  | %s' % (tag, key[0], len(jp), len(en), (jp[0][:40] if jp else (en[0][:40] if en else ''))))
