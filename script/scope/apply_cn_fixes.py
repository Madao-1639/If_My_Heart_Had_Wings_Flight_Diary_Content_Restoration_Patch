# -*- coding: utf-8 -*-
"""应用中文语料的**残留错字**修正（幂等）。

输入（由逐行判定产出）：
  * `resource/corpus/char_fix2.json` —— 字级修正表 `{错字: 正字}`（全局替换）
  * `resource/corpus/row_fix.json`   —— 逐行修正表 `{"<script>#<row>": "<修正后的完整 cn>"}`
    （用于「同一错字在不同上下文要改成不同字」的情形，如句末 `龟`→吗/嘛/吧/呢、`遥`→呢/呀）

顺序：**先全局套 `char_fix2`，再套 `row_fix`**（row_fix 的值已含字级修正，自洽）。
刻意排除的合法例外（不得进字级表）：`龟头`、`遥远`。

用法：`python script/scope/apply_cn_fixes.py`（重复运行无副作用）
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    cf_path = os.path.join(ROOT, 'resource', 'corpus', 'char_fix2.json')
    rf_path = os.path.join(ROOT, 'resource', 'corpus', 'row_fix.json')
    cf = json.load(open(cf_path, encoding='utf-8')) if os.path.exists(cf_path) else {}
    rf = json.load(open(rf_path, encoding='utf-8')) if os.path.exists(rf_path) else {}

    n_char = n_row = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'resource', 'corpus', 'cn', '*.jsonl'))):
        sc = os.path.basename(f)[:-6]
        rows = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
        for r in rows:
            t = r['cn']
            for a, b in cf.items():
                if a in t:
                    t = t.replace(a, b)
            if t != r['cn']:
                r['cn'] = t
                n_char += 1
            key = '%s#%d' % (sc, r['orig_row'])
            if key in rf:
                if rf[key] != r['cn']:
                    n_row += 1
                r['cn'] = rf[key]
        with open(f, 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('字级替换 %d 行；逐行覆盖 %d 行（幂等：已应用则再跑为 0/0）' % (n_char, n_row))


if __name__ == '__main__':
    main()
