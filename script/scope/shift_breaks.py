# -*- coding: utf-8 -*-
"""把机械比例插入的 \n 挪到最近标点之后，避免读起来断错句。"""
import glob
import json
import os
import re

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
PUNCT_AFTER = '，。！？、…―」』）)'

fixed = 0
for f in sorted(glob.glob(os.path.join(FD, 'resource', 'corpus', 'cn', '*.jsonl'))):
    rows = []
    for l in open(f, encoding='utf-8'):
        r = json.loads(l)
        cn = r['cn']
        out = []
        i = 0
        while i < len(cn):
            if cn.startswith('\\n', i):
                prev = out[-1] if out else ''
                nxt = cn[i + 2:i + 8]
                if prev and prev not in PUNCT_AFTER:
                    m = re.search(r'[，。！？、…」』）)]', nxt)
                    if m and m.start() <= 5:
                        seg = cn[i + 2:i + 2 + m.start() + 1]
                        out.append(seg)
                        i = i + 2 + m.start() + 1
                        out.append('\\n')
                        fixed += 1
                        continue
                out.append('\\n')
                i += 2
            else:
                out.append(cn[i])
                i += 1
        r['cn'] = ''.join(out)
        rows.append(r)
    with open(f, 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
print('断点微调 %d 处' % fixed)
