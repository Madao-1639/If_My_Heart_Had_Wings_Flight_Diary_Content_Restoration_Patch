# -*- coding: utf-8 -*-
"""构建中文语料：ORIG 日文格 ↔ Gemini 中格（语音锚点对齐）。
输出 resource/corpus/cn_draft/<script>.jsonl + 乱码诊断。
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
sys.path.insert(0, FD + '/tmp')
sys.path.insert(0, FD + '/tool')
import scope_mech as M  # noqa: E402
from galrev.advhd import arc, ws2  # noqa: E402

CP = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch/Chinese_Localization_Patch')
KANA = re.compile(r'[\u3040-\u30ff]')
HAN = re.compile(r'[\u4e00-\u9fff]')
OUT = os.path.join(FD, 'resource', 'corpus', 'cn_draft')

GEM_SCRIPTS = ['AFT_003', 'AFT_007_3', 'AGS_001', 'BEF_003', 'BEF_004', 'HOT_002', 'HOT_004',
               'HUS_001', 'KAN_3001_3', 'KAN_3001_4', 'KAN_3002_1', 'KAN_3002_2',
               # 以下 4 个非 H 改写脚本汉化补丁未译（是 Steam 英文），需整段补译
               'KAN_2001', 'KAN_3001_5', 'BEF_005', 'KAN_2002']


def lang(s):
    if KANA.search(s):
        return 'JP'
    if HAN.search(s):
        return 'CN'
    return 'EN'


def anchor_map(ro, rp):
    """ORIG 行 ↔ PATCH 行 的语音锚点对齐，返回 dict orig_i -> patch_i（含锚点间插值）。"""
    vo = [r['i'] for r in ro if r['voice']]
    vp = [r['i'] for r in rp if r['voice']]
    so = [ro[i]['voice'].upper() for i in vo]
    sp = [rp[i]['voice'].upper() for i in vp]
    from difflib import SequenceMatcher
    sm = SequenceMatcher(None, so, sp, autojunk=False)
    pairs = []
    for b in sm.get_matching_blocks():
        if b.size:
            pairs.extend((vo[b.a + k], vp[b.b + k]) for k in range(b.size))
    out = {}
    prev = (-1, -1)
    for a, b in pairs + [(len(ro), len(rp))]:
        # 锚点本身
        if a < len(ro):
            out[a] = b
        # 锚点之间的行按偏移插值
        na, pa = prev[0] + 1, prev[1] + 1
        k = 0
        while na + k < a and pa + k < b:
            out[na + k] = pa + k
            k += 1
        prev = (a, b)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    cn = {nb.decode('utf-16le'): d for nb, d in arc.read_raw(CP + '/Rio.arc')}
    fp = M.load(M.PATCH, 'Rio.arc')
    o = M.load(M.ORIG, 'Rio.arc')
    scope = json.load(open(os.path.join(FD, 'resource', 'restore_scope.json'), encoding='utf-8'))

    garble = Counter()
    total = 0
    for sc in GEM_SCRIPTS:
        ent = scope['scripts'].get(sc, {})
        pf = ent.get('patch_file')
        if pf is None and sc == 'AGS_001':
            pf = 'AGS_001.ws2'
        if pf is None or pf not in cn:
            print('%-12s 跳过（无汉化对应文件）' % sc)
            continue
        ro = M.rows(ws2.decode(o[sc + '.ws2']), M.TM) if sc + '.ws2' in o else []
        rp = M.rows(ws2.decode(fp[pf]), M.TF)
        rc = M.rows(ws2.decode(cn[pf]), M.TF)
        amap = anchor_map(ro, rp) if ro else {}
        # 区域内 ORIG 行 → in-scope
        regions = [r for r in ent.get('regions', [])
                   if r['action'] in ('replace_with_orig', 'insert_orig_all')]
        if sc == 'AGS_001':
            regions = [{'id': 'whole', 'action': 'replace_with_orig', 'h_level': 'H',
                        'orig_range': [0, len(ro) - 1]}]
        inspan = []
        for r in regions:
            inspan.append((r['id'], r['action'], r['h_level'], r['orig_range']))
        rows = []
        for rid, act, h, (lo, hi) in inspan:
            for oi in range(lo, hi + 1):
                pi = amap.get(oi)
                cn_txt = rc[pi]['text'] if pi is not None and pi < len(rc) else ''
                rows.append({
                    'script': sc, 'region': rid, 'action': act, 'h_level': h,
                    'orig_row': oi, 'patch_row': pi,
                    'jp': ro[oi]['text'] if oi < len(ro) else '',
                    'speaker': ro[oi]['name'] if oi < len(ro) else '',
                    'voice': ro[oi]['voice'] if oi < len(ro) else '',
                    'cn_gemini': cn_txt,
                    'cn_lang': lang(cn_txt) if cn_txt else 'MISSING',
                })
                total += 1
                if cn_txt and lang(cn_txt) == 'CN':
                    for ch in cn_txt:
                        if HAN.match(ch) and ch in '堯鶺瑤鞁鼕槇鼡黐鵐鮹':
                            garble[ch] += 1
        rows.sort(key=lambda x: (x['orig_row']))
        with open(os.path.join(OUT, sc + '.jsonl'), 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        need = sum(1 for r in rows if r['cn_lang'] != 'CN')
        print('%-12s in-scope %4d 行；已有中文 %4d；需补译 %3d' %
              (sc, len(rows), len(rows) - need, need))
    print('\n合计 in-scope 行：', total)
    print('可疑高频字（候选乱码/异名）：', dict(garble))
    # 乱码字上下文
    print('\n=== 可疑字上下文 ===')
    for probe in ('堯', '鶺', '瑤'):
        for sc in ('HOT_004', 'HUS_001', 'KAN_3001_3'):
            pf = sc + '_E.ws2'
            for r in M.rows(ws2.decode(cn[pf]), M.TF):
                if probe in r['text']:
                    print('  %s %s: %s' % (sc, probe, r['text'][:70].replace('\n', '⏎')))
                    break


if __name__ == '__main__':
    main()
