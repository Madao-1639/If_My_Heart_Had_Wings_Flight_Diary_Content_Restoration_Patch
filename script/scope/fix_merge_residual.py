# -*- coding: utf-8 -*-
"""合并后机械修残：① 纯标点行（JP==CN）直接采用 ② 字面 "\n"(反斜杠+n) 换成真换行 ③ 输出仍需补译的清单。"""
import glob
import json
import os
import re

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
OUT = os.path.join(FD, 'resource', 'corpus', 'cn')

TEXTY = re.compile(r'[\u3040-\u30ff\u4e00-\u9fffA-Za-z]')
KANA = re.compile(r'[\u3040-\u30ff]')


def main():
    need = []
    fixed_n = fixed_p = 0
    for f in sorted(glob.glob(os.path.join(OUT, '*.jsonl'))):
        sc = os.path.basename(f)[:-6]
        rows = []
        for l in open(f, encoding='utf-8'):
            r = json.loads(l)
            jp, cn = r['jp'], r['cn']
            # ② 真换行 → 字面 "\n"（ws2 的换行标记是两字符；JP 侧从无真换行）
            if '\n' in cn:
                cn = cn.replace('\n', '\\n')
                fixed_n += 1
            # ① 纯标点行：JP 无可读字符且 CN 与 JP 相同
            _M = re.compile(r'%K%P|%P|\\d.*?\\d|\\n')
            if not TEXTY.search(_M.sub('', jp)) and cn.strip() == jp.strip():
                r['cn'], r['src'] = jp, 'punct'
                fixed_p += 1
            else:
                r['cn'] = cn
            if (KANA.search(cn) or not TEXTY.search(_M.sub('', cn))) \
                    and TEXTY.search(_M.sub('', jp)) and r['src'] == 'pending':
                need.append((sc, r['orig_row']))
            rows.append(r)
        with open(f, 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('机械修残：字面 \\n 修正 %d 处；纯标点行采用 %d 行' % (fixed_n, fixed_p))
    print('仍需补译：%d 行' % len(need))
    json.dump(need, open(os.path.join(FD, 'tmp', 'scope', 'need_translate2.json'), 'w',
                         encoding='utf-8'), ensure_ascii=False)
    for sc, i in need:
        print('   %s#%d' % (sc, i))


if __name__ == '__main__':
    main()
