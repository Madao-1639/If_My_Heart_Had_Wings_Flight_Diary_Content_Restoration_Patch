"""把三个版本的同一脚本的「演出资源序列」导出为文本，供逐条比对。

用法：
    python res_seq.py <脚本名> [<脚本名> ...]        # 打印摘要
    python res_seq.py --dump <脚本名>               # 写出 tmp/seq_<tag>_<脚本>.txt

序列口径：按字节流出现顺序抽出所有 `*.PNA/PNG/OGG/WAV/BMP/MOS/JPG/AVI/DAT` 资源名
（ASCII 或 Shift-JIS），大写化。**不依赖 WS2 格式表**，因此对原版（不同引擎版本）同样可用。
"""
import re
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
                   'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tool')
from galrev.advhd import arc, ws2

ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'

NAME = re.compile(rb'([0-9A-Za-z_\-]{2,40}|(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]){1,20})'
                  rb'\.(?:PNA|PNG|OGG|WAV|BMP|MOS|JPG|AVI|DAT)', re.I)

_CACHE = {}


def _load(root, an):
    key = (root, an)
    if key not in _CACHE:
        _CACHE[key] = {nb.decode('utf-16le'): d for nb, d in arc.read_raw(root + '/' + an)}
    return _CACHE[key]


def names(dec):
    out = []
    for m in NAME.finditer(dec):
        raw = m.group(0)
        try:
            s = raw.decode('ascii')
        except UnicodeDecodeError:
            s = raw.decode('cp932', 'replace')
        out.append(s.upper())
    return out


def get(tag, script):
    """返回解码后的字节流；找不到返回 None。script 不带 .ws2。"""
    if tag == 'orig':
        m = _load(ORIG, 'Rio.arc')
        return ws2.decode(m[script + '.ws2']) if script + '.ws2' in m else None
    if tag == 'steam':
        for an in ('Rio.arc', 'Rio1.arc'):
            m = _load(STEAM, an)
            for cand in (script + '_E.ws2', script + '.ws2'):
                if cand in m:
                    return ws2.decode(m[cand])
        return None
    if tag == 'patch':
        for an in ('Rio.arc', 'Rio1.arc'):
            m = _load(PATCH, an)
            for cand in (script + '.ws2', script + '_E.ws2'):
                if cand in m:
                    return ws2.decode(m[cand])
        return None
    raise ValueError(tag)


def seq(tag, script):
    d = get(tag, script)
    return None if d is None else names(d)


if __name__ == '__main__':
    if '--dump' in sys.argv:
        for t in sys.argv[2:]:
            for tag in ('orig', 'steam', 'patch'):
                s = seq(tag, t)
                if s is None:
                    print('  %-5s %-14s N/A' % (tag, t))
                    continue
                p = 'tmp/seq_%s_%s.txt' % (tag, t)
                open(p, 'w', encoding='utf-8').write('\n'.join(s))
                print('  %-5s %-14s %d -> %s' % (tag, t, len(s), p))
    else:
        import collections
        for t in sys.argv[1:]:
            parts = []
            for tag in ('orig', 'steam', 'patch'):
                s = seq(tag, t)
                if s is None:
                    parts.append('%s=N/A' % tag)
                else:
                    c = collections.Counter(s)
                    parts.append('%s=%d[PNA %d/PNG %d/OGG %d]' % (
                        tag, len(s), sum(v for k, v in c.items() if k.endswith('.PNA')),
                        sum(v for k, v in c.items() if k.endswith('.PNG')),
                        sum(v for k, v in c.items() if k.endswith('.OGG'))))
            print('%-12s %s' % (t, '  '.join(parts)))
