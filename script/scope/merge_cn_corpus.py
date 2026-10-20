# -*- coding: utf-8 -*-
"""合并 subagent 审校结果 → resource/corpus/cn/<script>.jsonl + 质检报告。"""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
DRAFT = os.path.join(FD, 'resource', 'corpus', 'cn_draft')
REVIEW = os.path.join(FD, 'tmp', 'verify', 'cn')
OUT = os.path.join(FD, 'resource', 'corpus', 'cn')

KANA = re.compile(r'[\u3040-\u30ff]')
GARBLE = set('堯鶺瑤鞁槇鼕鵐鶫狢黐鼡鮹')
CHUNK_RE = re.compile(r'^c\d+_([A-Za-z0-9_]+?)_')


def markers(s):
    return (s.count('%K%P'), s.count('%P'), len(re.findall(r'\\d', s)), s.count('\n'))


def main():
    os.makedirs(OUT, exist_ok=True)
    drafts = {}
    for f in glob.glob(os.path.join(DRAFT, '*.jsonl')):
        sc = os.path.basename(f)[:-6]
        drafts[sc] = [json.loads(l) for l in open(f, encoding='utf-8')]

    rev = {}
    for f in glob.glob(os.path.join(REVIEW, '*.jsonl')):
        base = os.path.basename(f)
        m = CHUNK_RE.match(base)
        if not m:
            print('!! 无法从文件名解析脚本:', base)
            continue
        sc = m.group(1)
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            d = json.loads(l)
            rev[(sc, d['i'])] = d

    stats = Counter()
    issues = []
    for sc, rows in sorted(drafts.items()):
        out_rows = []
        for r in rows:
            key = (sc, r['orig_row'])
            d = rev.get(key)
            if d is None:
                stats['missing'] += 1
                issues.append('%s#%d 缺审校结果' % (sc, r['orig_row']))
                continue
            cn = d.get('cn', '')
            if not cn.strip():
                stats['empty'] += 1
                issues.append('%s#%d 空译文' % (sc, r['orig_row']))
            if KANA.search(cn):
                stats['kana'] += 1
                issues.append('%s#%d 残留假名: %s' % (sc, r['orig_row'], cn[:40]))
            g = GARBLE & set(cn)
            if g:
                stats['garble'] += 1
                issues.append('%s#%d 残留乱码字 %s' % (sc, r['orig_row'], ''.join(sorted(g))))
            mj, mc = markers(r['jp']), markers(cn)
            if mj != mc:
                stats['marker_mismatch'] += 1
                issues.append('%s#%d 控制标记不一致 jp=%s cn=%s' % (sc, r['orig_row'], mj, mc))
            if not r['cn_gemini']:
                stats['translated_from_scratch'] += 1
            elif cn != r['cn_gemini']:
                stats['modified'] += 1
            out_rows.append({
                'script': sc, 'orig_row': r['orig_row'], 'region': r['region'],
                'h_level': r['h_level'], 'jp': r['jp'], 'cn': cn,
                'note': d.get('note', ''),
                'src': 'gemini_reviewed' if r['cn_gemini'] else 'translated',
            })
        with open(os.path.join(OUT, sc + '.jsonl'), 'w', encoding='utf-8') as fh:
            for r in out_rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        stats['scripts'] += 1
        stats['rows'] += len(out_rows)

    print('合并完成：%d 脚本 / %d 行' % (stats['scripts'], stats['rows']))
    print('底稿已有、审校后改动：%d 行；无底稿整段翻译：%d 行' %
          (stats['modified'], stats['translated_from_scratch']))
    print('质检问题：缺结果 %d / 空 %d / 假名残留 %d / 乱码字残留 %d / 控制标记不一致 %d' %
          (stats['missing'], stats['empty'], stats['kana'], stats['garble'],
           stats['marker_mismatch']))
    if issues:
        with open(os.path.join(FD, 'tmp', 'scope', 'cn_qa_issues.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(issues))
        print('问题明细 → tmp/scope/cn_qa_issues.txt（%d 条）' % len(issues))
        for x in issues[:15]:
            print('   ', x[:110])


if __name__ == '__main__':
    main()
