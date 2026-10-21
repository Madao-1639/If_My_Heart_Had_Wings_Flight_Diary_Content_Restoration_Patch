# -*- coding: utf-8 -*-
"""产物内容回读闸（构建后）：还原块落位 + lng 逐槽=语料 + pure_add 保留行在位。

用法：工程根目录 python script/checks/verify_restore_content.py
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.abspath('.'))
from tool import arcbuild, ws2, lng, ws2fmt  # noqa: E402

TAB = ws2fmt.Table('resource/ws2_formats.json')
STRIP = re.compile(r'(\\n|[\s%KP])')


def norm(s):
    return STRIP.sub('', s or '')


def rows_of(asset, member):
    out, cur = [], ''
    for off, op, sz, f in ws2fmt.disassemble(ws2.decode(asset[member]), TAB):
        a = f.get('args') or []
        if op == 0x15:
            s = a[0] if a and isinstance(a[0], str) else ''
            cur = s[3:] if s.startswith('%LC') else ''
        elif op == 0x14:
            t = next((x for x in a if isinstance(x, str) and not x.startswith('%LC')
                      and not x.upper().endswith('.OGG') and x != 'char'), '')
            out.append({'name': cur, 'text': t})
    return out


def main():
    asset = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw('asset/Rio.arc')}
    zh = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw('asset/zh-CN/Rio.arc')}
    scope = json.load(open('resource/restore_scope.json', encoding='utf-8'))
    slots_all = json.load(open('resource/slot_sources.json', encoding='utf-8'))
    corpus = {}
    fails = []
    n_reg = n_row = 0
    for sc, rec in sorted(scope['scripts'].items()):
        sf = rec.get('steam_file')
        if not sf or sc not in slots_all:
            continue
        out_rows = rows_of(asset, sf)
        slots = slots_all[sc]['slots']
        texts = lng.parse_lng(zh[sf[:-4] + '.lng'], lng.KEY_FD)
        if len(texts) != len(slots):
            fails.append('%s lng \u6761\u6570 %d != \u69fd\u8868 %d' % (sc, len(texts), len(slots)))
            continue
        for r in rec['regions']:
            if r['form'] != 'mixed_censor':
                continue
            olo, ohi = r['orig_range']
            inset = [i for i, (k, v) in enumerate(slots) if k == 'orig' and olo <= v <= ohi]
            if len(inset) != ohi - olo + 1:
                fails.append('%s idx%d \u63d2\u5165\u69fd\u6570 %d != \u539f\u7248\u884c\u6570 %d'
                             % (sc, r['id'], len(inset), ohi - olo + 1))
                continue
            n_reg += 1
            want = corpus.get(sc)
            if want is None:
                want = {}
                for line in open('resource/corpus/cn/%s.jsonl' % sc, encoding='utf-8'):
                    if line.strip():
                        rr = json.loads(line)
                        want[rr['orig_row']] = rr['cn']
                corpus[sc] = want
            for i in inset:
                n_row += 1
                if i >= len(out_rows) or not norm(out_rows[i]['text']):
                    fails.append('%s idx%d \u69fd %d \u4ea7\u7269\u6587\u672c\u7a7a/\u8d85\u754c' % (sc, r['id'], i))
                elif i in (inset[0], inset[-1]):
                    if norm(texts[i]) != norm(want.get(slots[i][1], '')):
                        fails.append('%s idx%d lng \u69fd %d \u4e2d\u6587\u4e0e\u8bed\u6599\u4e0d\u4e00\u81f4' % (sc, r['id'], i))
    print('mixed_censor \u533a\u95f4 %d \u4e2a / \u63d2\u5165\u69fd %d \u4e2a\u68c0\u67e5\u5b8c\u6210' % (n_reg, n_row))
    joined = '|'.join(norm(r['text']) for r in rows_of(asset, 'KAN_4001_E.ws2'))
    for frag in ('plucktheglider', 'whipupsomefood', 'picturetheirfaces'):
        if frag not in joined:
            fails.append('KAN_4001 \u4fdd\u7559\u65b0\u589e\u884c\u7f3a\u5931: %s' % frag)
    joined = '|'.join(norm(r['text']) for r in rows_of(asset, 'KAN_3002_1_E.ws2'))
    for frag in ('Flattered?What', 'jealoustype'):
        if frag not in joined:
            fails.append('KAN_3002_1 \u4fdd\u7559/\u90bb\u63a5\u884c\u7f3a\u5931: %s' % frag)
    if fails:
        print('\u56de\u8bfb\u5931\u8d25 %d \u6761:' % len(fails))
        for x in fails[:20]:
            print('  ', x)
        sys.exit(1)
    print('\u2705 \u5185\u5bb9\u56de\u8bfb\u901a\u8fc7')


if __name__ == '__main__':
    main()
