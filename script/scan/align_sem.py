"""语义抽样：用**语音锚点**保证 ORIG 行 ↔ PATCH 行对应正确，抽取 JP↔EN 配对供语义判定。

- A 类（可靠）：落在「语音锚点区间内 ORIG/PATCH 行数相等」的位置 ⇒ 位置对应由语音锚点保证。
- B 类（不可靠）：落在行数不等的区间（Steam 译文拆行/合行）⇒ 需人工/模型对齐，单独列出。
"""
import json
import os
import random
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
                   'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tool')
sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
                   'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tmp')
import align_voice as V

OUT = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
       'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tmp/align_en')
TARGETS = ['AFT_003', 'AFT_007_3', 'BEF_003', 'BEF_004', 'HOT_002', 'HOT_004', 'HUS_001',
           'KAN_3001_3', 'KAN_3001_4', 'KAN_3002_2', 'AGS_001']


def build(script):
    on = script + '.ws2'
    o = V.load(V.ORIG, 'Rio.arc')
    p = V.load(V.PATCH, 'Rio.arc')
    pn = on if on in p else script + '_E.ws2'
    if on not in o or pn not in p:
        return None
    lo = V.rows(V.ws2.decode(o[on]), V.TM if script == 'BEF_004' else V.TO)
    lp = V.rows(V.ws2.decode(p[pn]), V.TF)
    vo = [i for i, r in enumerate(lo) if r[3]]
    vp = [i for i, r in enumerate(lp) if r[3]]
    if [lo[i][3].upper() for i in vo] != [lp[i][3].upper() for i in vp]:
        return {'script': script, 'voice_aligned': False, 'pairs': [], 'bad': []}
    pairs, bad = [], []
    a = b = -1
    for k in range(max(len(vo), len(vp))):
        ai = vo[k] if k < len(vo) else len(lo)
        bi = vp[k] if k < len(vp) else len(lp)
        na, nb = ai - a - 1, bi - b - 1
        spans_o = list(range(a + 1, ai))
        spans_p = list(range(b + 1, bi))
        if na == nb:
            for x, y in zip(spans_o, spans_p):
                pairs.append({'i': x, 'j': y, 'o': lo[x][2], 'p': lp[y][2],
                              'voice': lo[x][3] or lo[ai][3]})
        elif na and nb:
            bad.append({'o_range': [a + 1, ai], 'p_range': [b + 1, bi],
                        'o': [lo[x][2] for x in spans_o], 'p': [lp[y][2] for y in spans_p],
                        'reason': 'split/merge（行数不等，需对齐）'})
        elif nb and not na:
            bad.append({'o_range': [a + 1, ai], 'p_range': [b + 1, bi], 'o': [],
                        'p': [lp[y][2] for y in spans_p], 'reason': 'PATCH 多出的英文行'})
        elif na and not nb:
            bad.append({'o_range': [a + 1, ai], 'p_range': [b + 1, bi],
                        'o': [lo[x][2] for x in spans_o], 'p': [],
                        'reason': 'ORIG 独有的行（PATCH 无对应）'})
        a, b = ai, bi
    return {'script': script, 'voice_aligned': True, 'pairs': pairs, 'bad': bad}


def main():
    os.makedirs(OUT, exist_ok=True)
    data = {}
    for t in TARGETS:
        r = build(t)
        if r:
            data[t] = r
    # 抽样：每脚本从 A 类里均匀抽 12 条 JP↔EN
    rng = random.Random(20261013)
    samples = []
    for t, r in data.items():
        mix = [x for x in r['pairs'] if V.isjp(x['o']) and not V.isjp(x['p'])]
        jpjp = [x for x in r['pairs'] if V.isjp(x['o']) and V.isjp(x['p'])]
        pick = []
        if mix:
            pick += rng.sample(mix, min(10, len(mix)))
        if jpjp:
            pick += rng.sample(jpjp, min(2, len(jpjp)))
        for x in pick:
            samples.append({'script': t, 'kind': 'jp-en' if not V.isjp(x['p']) else 'jp-jp',
                            'orig_line': x['i'], 'patch_line': x['j'], 'voice': x['voice'],
                            'orig': x['o'], 'patch': x['p']})
    with open(os.path.join(OUT, 'sem_samples.jsonl'), 'w', encoding='utf-8') as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + '\n')
    with open(os.path.join(OUT, 'pairs.json'), 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    # 汇总
    print('%-12s %-8s %-8s %-8s %s' % ('script', '语音对齐', 'A类可靠对', 'B类缺口', '缺口摘要'))
    for t in TARGETS:
        r = data.get(t)
        if not r:
            print('%-12s N/A' % t)
            continue
        print('%-12s %-8s %-8d %-8d %s' % (t, r['voice_aligned'], len(r['pairs']), len(r['bad']),
              ('；'.join(b['reason'] for b in r['bad'][:3])[:60] if r['bad'] else '—')))
    print('\n抽样 %d 条 -> tmp/align_en/sem_samples.jsonl' % len(samples))


if __name__ == '__main__':
    main()
