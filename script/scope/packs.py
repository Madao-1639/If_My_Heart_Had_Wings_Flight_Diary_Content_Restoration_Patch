"""为语义核验生成逐剧本 review pack（markdown，直接从语料取全文）。

每个有差分区间的剧本一个文件：区间元信息 + 两侧全文（去控制标记）。
大区间取「前 45 + 后 12」行，另附计数。
"""
import json
import os
import re
import sys

PATCHDIR = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
            'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
OUT = PATCHDIR + '/tmp/scope/packs'
SRC = PATCHDIR + '/tmp/scope/regions.jsonl'
META = PATCHDIR + '/tmp/scope/scope_mech.json'

sys.path.insert(0, PATCHDIR + '/tmp')
import scope_mech as M  # noqa: E402

_CTRL = re.compile(r'%K%P|\\d|\\p')


def clean(s):
    s = _CTRL.sub('', s)
    return s.replace('\n', '⏎')


def sel_rows(rows, lo, hi, head=45, tail=12):
    n = hi - lo + 1
    if n <= head + tail:
        return list(range(lo, hi + 1)), False
    return list(range(lo, lo + head)) + list(range(hi - tail + 1, hi + 1)), True


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = json.load(open(META, encoding='utf-8'))
    byscript = {}
    for l in open(SRC, encoding='utf-8'):
        r = json.loads(l)
        byscript.setdefault(r['script'], []).append(r)

    cache = {}

    def get_rows(tag, script, fname):
        key = (tag, fname)
        if key not in cache:
            if tag == 'orig':
                d = M.load(M.ORIG, 'Rio.arc')[fname]
                cache[key] = M.rows(M.ws2.decode(d), M.TM)
            elif tag == 'steam':
                d = M.load(M.STEAM, 'Rio.arc')[fname]
                cache[key] = M.rows(M.ws2.decode(d), M.TF)
            else:
                d = M.load(M.PATCH, 'Rio.arc')[fname]
                cache[key] = M.rows(M.ws2.decode(d), M.TF)
        return cache[key]

    for sc, regs in byscript.items():
        m = meta['scripts'].get(sc, {})
        of, sf = m.get('orig_file'), m.get('steam_file')
        ro = get_rows('orig', sc, of) if of else []
        rs = get_rows('steam', sc, sf) if sf else []
        out = ['# %s —— 差分区间 %d 个' % (sc, len(regs)), '',
               '- 文件：ORIG `%s` / STEAM `%s` / PATCH `%s`' % (of, sf, m.get('patch_file')),
               '- 行数（0x14 格）：ORIG %s / STEAM %s / PATCH %s；语音锚点 %s 对'
               % (m.get('orig_rows'), m.get('steam_rows'), m.get('patch_rows'),
                  m.get('anchor_pairs')),
               '- 有语音格：ORIG %s / STEAM %s / PATCH %s'
               % (m.get('orig_voiced'), m.get('steam_voiced'), m.get('patch_voiced')), '']
        for idx, r in enumerate(regs):
            out.append('## 区间 %d · %s' % (idx, r['shape']))
            out.append('')
            out.append('- 位置：ORIG[%d..%d] %d 格 ↔ STEAM[%d..%d] %d 格 ↔ PATCH%s'
                       % (r['orig'][0], r['orig'][1], r['no'],
                          r['steam'][0], r['steam'][1], r['ns'], r['patch']))
            out.append('- 补丁状态：`%s`；PATCH 区间内日文行 %s、与原版文本匹配 %s/%s（覆盖 %s）'
                       % (r['patch_status'], r['jp_rows_in_patch'], r['jp_text_match'],
                          r['no'], r['jp_cover']))
            out.append('- 补丁删除的 Steam 行 %d 条；补丁新插日文行 %d 条'
                       % (len(r['steam_rows_dropped_by_patch']), r['patch_inserted_jp']))
            if r['voice_rewrite']:
                out.append('- **等长逐位换装**（同位语音名不同）：%s'
                           % '; '.join('%s→%s' % (v['orig_voice'], v['steam_voice'])
                                      for v in r['voice_rewrite'][:8]))
            if r['o_voices_not_in_steam_arc']:
                out.append('- 原版侧有 %d 条语音不在 Steam 语音包内（全表无锚点）：%s …'
                           % (len(r['o_voices_not_in_steam_arc']),
                              ', '.join(r['o_voices_not_in_steam_arc'][:8])))
            out.append('- 原版侧语音 %d 条 / Steam 侧语音 %d 条（Steam 独有 %d 条）'
                       % (len(r['o_voices']), len(r['s_voices']),
                          len(r['s_voices_steam_only'])))
            out.append('')
            for tag, rows_, lo, hi, label in (
                    ('ORIG', ro, r['orig'][0], r['orig'][1], '原版'),
                    ('STEAM', rs, r['steam'][0], r['steam'][1], 'Steam')):
                if hi < lo:
                    out.append('**%s（%s）：无行**' % (tag, label))
                    out.append('')
                    continue
                sel, trunc = sel_rows(rows_, lo, hi)
                out.append('**%s（%s）[%d..%d] 共 %d 格%s**'
                           % (tag, label, lo, hi, hi - lo + 1,
                              '，仅显示前 45+后 12' if trunc else ''))
                prev = None
                for i in sel:
                    if prev is not None and i > prev + 1:
                        out.append('-   …… （省略 %d 格）' % (i - prev - 1))
                    x = rows_[i]
                    out.append('- %s#%d %s%s| %s' % (
                        'O' if tag == 'ORIG' else 'S', i, x['voice'] or '　',
                        ('『%s』' % x['name']) if x['name'] else '', clean(x['text'])[:160]))
                    prev = i
                out.append('')
        path = os.path.join(OUT, 'pack_%s.md' % sc)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(out))
        print('%-14s %2d 区间 → %s (%d KB)' % (sc, len(regs), os.path.basename(path),
                                               os.path.getsize(path) // 1024))


if __name__ == '__main__':
    main()
