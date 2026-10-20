"""列出 Arc 成员（名 / 大小 / sha1），供跨版本比对。用法：
    python dump_arc.py <arc> [--json out.json]
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
from galrev.advhd import arc


def name_of(nb):
    for enc in ('utf-16le', 'shift_jis', 'utf-8'):
        try:
            s = nb.decode(enc)
            if all(ord(c) >= 32 or c in '\t' for c in s):
                return s
        except Exception:
            pass
    return repr(nb)


def dump(path):
    members = arc.read_raw(path)
    out = []
    for nb, data in members:
        out.append({
            'name': name_of(nb),
            'raw_name_hex': nb.hex(),
            'size': len(data),
            'sha1': hashlib.sha1(data).hexdigest()[:16],
        })
    return out


def main():
    path = sys.argv[1]
    js = '--json' in sys.argv
    m = dump(path)
    if js:
        i = sys.argv.index('--json')
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.path.splitext(os.path.basename(path))[0] + '.json'
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(m, fh, ensure_ascii=False, indent=1)
        print('wrote', out, len(m), 'members')
        return
    print('%s: %d members' % (os.path.basename(path), len(m)))
    for e in m:
        print('  %-40s %10d  %s' % (e['name'], e['size'], e['sha1']))


if __name__ == '__main__':
    main()
