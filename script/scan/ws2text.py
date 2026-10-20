"""从 ws2 解码后提取可读文本串（CP932 窄字节 + UTF-16LE），用于识别剧本内容。"""
import re
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
from galrev.advhd import arc, ws2

ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'


def members(path):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(path)}


def text_of(dec):
    """粗暴抽取：把连续 >=3 个可打印 CP932 字节的段解出来。"""
    out = []
    i = 0
    n = len(dec)
    cur = bytearray()
    while i < n:
        b = dec[i]
        if b == 0:
            if len(cur) >= 3:
                out.append(bytes(cur))
            cur = bytearray()
            i += 1
            continue
        cur.append(b)
        i += 1
    if len(cur) >= 3:
        out.append(bytes(cur))
    res = []
    for s in out:
        try:
            t = s.decode('cp932')
        except Exception:
            continue
        if len(t) >= 3 and any('\u3040' <= c <= '\u9fff' or '\uff66' <= c <= '\uff9f' for c in t):
            res.append(t)
    return res


if __name__ == '__main__':
    which = sys.argv[1]
    arcname = sys.argv[2]
    target = sys.argv[3] if len(sys.argv) > 3 else None
    paths = {'orig': ORIG, 'steam': STEAM, 'patch': PATCH}
    ms = members(paths[which] + '/' + arcname)
    names = [target] if target else sorted(ms)
    for nm in names:
        key = nm
        if key not in ms:
            cand = [k for k in ms if k.lower() == nm.lower()]
            if not cand:
                print('!! not found', nm)
                continue
            key = cand[0]
        dec = ws2.decode(ms[key])
        txt = text_of(dec)
        print('=== %s (%d bytes, %d strings) ===' % (nm, len(ms[key]), len(txt)))
        for t in txt[:40]:
            print('   ', t)
