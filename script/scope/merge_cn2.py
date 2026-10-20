# -*- coding: utf-8 -*-
"""合并复审 diff → resource/corpus/cn/<script>.jsonl + 质检。"""
import glob
import json
import os
import re
from collections import Counter

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
NORM = os.path.join(FD, 'resource', 'corpus', 'cn_norm')
DIFF = os.path.join(FD, 'tmp', 'verify', 'cn2')
OUT = os.path.join(FD, 'resource', 'corpus', 'cn')

KANA = re.compile(r'[\u3040-\u30ff]')
RARE = set('閖鯆鵤驫鐔鰊鱚鮹鷭駻鷁鰰鴃鮴駲苙鞐鱆鰤鯔鶸鷏鷆髞闍鵺爍鋺鰡麭齧鵞鰮鮠鐔繃')


def markers(s):
    return (s.count('%K%P'), s.count('%P'), len(re.findall(r'\\d', s)), s.count('\n'))


def main():
    os.makedirs(OUT, exist_ok=True)
    diffs = {}
    # 已知脚本名（来自 cn_draft 文件名），用于稳健解析 rNN_<SCRIPT>_<rows>.jsonl
    known = sorted({os.path.basename(f)[:-6] for f in
                    glob.glob(os.path.join(NORM, '*.jsonl'))}, key=len, reverse=True)
    for f in glob.glob(os.path.join(DIFF, '*.jsonl')):
        base = os.path.basename(f)[:-6]
        sc = None
        for k in known:
            if base.startswith('r') and ('_' + k + '_') in (base + '_'):
                # 精确匹配段：rNN_<K>_<digits>-<digits>
                import re as _re
                if _re.match(r'^r\d+_' + _re.escape(k) + r'_\d+-\d+$', base):
                    sc = k
                    break
        if sc is None:
            # 特例：r99_HUS_001_rows（补充复审包）
            if base == 'r99_HUS_001_rows':
                sc = 'HUS_001'
            else:
                print('!! 无法解析脚本名:', base)
                continue
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            d = json.loads(l)
            diffs[(sc, d['i'])] = d
    print('读入复审 diff：%d 处，来自 %d 个文件' % (len(diffs), len(glob.glob(os.path.join(DIFF, '*.jsonl')))))

    st = Counter()
    issues = []
    for f in sorted(glob.glob(os.path.join(NORM, '*.jsonl'))):
        sc = os.path.basename(f)[:-6]
        out = []
        for l in open(f, encoding='utf-8'):
            r = json.loads(l)
            cn = r['cn_norm']
            d = diffs.get((sc, r['orig_row']))
            if d is not None and d.get('cn'):
                cn = d['cn']
                st['diff_applied'] += 1
            elif r['cn_lang'] != 'CN':
                st['untranslated'] += 1
                issues.append('%s#%d 仍未翻译' % (sc, r['orig_row']))
            if not cn.strip():
                st['empty'] += 1
                issues.append('%s#%d 空' % (sc, r['orig_row']))
                continue
            if KANA.search(cn):
                st['kana'] += 1
                issues.append('%s#%d 假名残留 %s' % (sc, r['orig_row'], cn[:36]))
            if RARE & set(cn):
                st['rare'] += 1
                issues.append('%s#%d 乱码字残留 %s' % (sc, r['orig_row'],
                                                      ''.join(sorted(RARE & set(cn)))))
            mj, mc = markers(r['jp']), markers(cn)
            if mj != mc:
                st['marker'] += 1
                issues.append('%s#%d 控制标记不一致 jp=%s cn=%s' % (sc, r['orig_row'], mj, mc))
            out.append({'script': sc, 'orig_row': r['orig_row'], 'region': r['region'],
                        'h_level': r['h_level'], 'jp': r['jp'], 'cn': cn,
                        'note': (d or {}).get('note', ''),
                        'src': 'reviewed' if d is not None else ('gemini_norm' if r['cn_gemini'] else 'pending')})
        with open(os.path.join(OUT, sc + '.jsonl'), 'w', encoding='utf-8') as fh:
            for r in out:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        st['rows'] += len(out)
        st['scripts'] += 1

    print('合并：%d 脚本 / %d 行；应用复审 diff %d 处' % (st['scripts'], st['rows'], st['diff_applied']))
    print('质检：未译 %d / 空 %d / 假名残留 %d / 乱码字残留 %d / 控制标记不一致 %d' %
          (st['untranslated'], st['empty'], st['kana'], st['rare'], st['marker']))
    if issues:
        p = os.path.join(FD, 'tmp', 'scope', 'cn_qa_issues.txt')
        open(p, 'w', encoding='utf-8').write('\n'.join(issues))
        print('问题 %d 条 → tmp/scope/cn_qa_issues.txt' % len(issues))
        for x in issues[:12]:
            print('   ', x[:100])


if __name__ == '__main__':
    main()
