# -*- coding: utf-8 -*-
"""中文语料**短语级**收尾修正（幂等）。

背景
----
`resource/corpus/cn/` 由「Gemini 底稿 → `normalize_cn.py` 逐字映射」产出。逐字映射对
**一形对多义**的窄字节损坏字无能为力：底稿里同一个损坏字形，在不同上下文应对应不同的
简体字。实测残留（共 51 行）：

| 残留 | 正确 | 依据 |
|---|---|---|
| `鹅` | `撑` | 「双手鹅地」← 両手を突く／「别鹅开」← 押し開く／「鹅不住」← 持ちこたえられない |
| `鳖` | `桌` | 「课鳖」「鳖子」← 机（つくえ） |
| `龄` | `办` / `么` | 「没龄法」← 仕方ない／「怎么龄」← どうしたの |

（`髓`＝脑髓、`鸭`＝冲鸭、`鸽`＝放鸽子 是**正确**中文，不在修正范围。）

用法：`python script/scope/fix_cn_phrases.py`（重复运行无副作用）。
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# **顺序敏感**：长串在前，避免 `没龄法` 被 `没龄` 先截。
FIXES = [
    ('鹅', '撑'),
    ('鳖', '桌'),
    ('没龄法', '没办法'),
    ('没龄', '没办'),
    ('怎么龄', '怎么了'),
]


def main():
    n = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'resource', 'corpus', 'cn', '*.jsonl'))):
        rows = [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
        for r in rows:
            t = r['cn']
            for a, b in FIXES:
                if a in t:
                    t = t.replace(a, b)
            if t != r['cn']:
                r['cn'] = t
                n += 1
        with open(f, 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('短语级修正 %d 行（幂等：已修正则再跑为 0）' % n)


if __name__ == '__main__':
    main()
