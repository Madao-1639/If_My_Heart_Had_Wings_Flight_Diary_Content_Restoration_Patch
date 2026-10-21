# -*- coding: utf-8 -*-
"""构建前预检（内容面）：语料三项一致性 + 插入格覆盖 + 锚点安全。

用法：工程根目录 python script/checks/preflight_corpus.py
闸门语义（AGENTS.md「闸门要能验内容」）：
  A. 语料每条：控制标记（%K/%P）有无与 jp 一致；换行结构（字面 \n）与 jp 一致；
     jp 有实义内容而 cn 剥净后为空的判占位。
  B. restore_plan 全部插入原版行在语料中、非空、无假名。
  C. 插入锚点不落在删格集内。
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

KANA = re.compile('[\u3040-\u309f\u30a1-\u30fa]')
NL = chr(92) + 'n'
PUNCT = '\u3000-\u303f\uff00-\uffef\u2018-\u201d\u2026\u2014'
CORP = 'resource/corpus/cn'
STRIP_CN = re.compile('%%K%%P|%%K|%%P|[' + PUNCT + r'\W_]')
STRIP_JP = re.compile('%%K%%P|%%K|%%P|[぀-ヿ一-鿿' + PUNCT + r'\W_]')


def main():
    plan = json.load(open('resource/restore_plan.json', encoding='utf-8'))
    corpus = {}

    def load_corpus(sc):
        if sc not in corpus:
            d = {}
            p = os.path.join(CORP, sc + '.jsonl')
            if os.path.exists(p):
                for line in open(p, encoding='utf-8'):
                    if line.strip():
                        r = json.loads(line)
                        d[r['orig_row']] = r
            corpus[sc] = d
        return corpus[sc]

    fails = []
    n_all = 0
    for f in sorted(os.listdir(CORP)):
        if not f.endswith('.jsonl'):
            continue
        for line in open(os.path.join(CORP, f), encoding='utf-8'):
            if not line.strip():
                continue
            r = json.loads(line)
            n_all += 1
            cn, jp = str(r.get('cn', '')), str(r.get('jp', ''))
            tag = '%s O#%d' % (r['script'], r['orig_row'])
            if (('%K' in jp) or ('%P' in jp)) != (('%K' in cn) or ('%P' in cn)):
                fails.append('%s \u63a7\u5236\u6807\u8bb0\u4e0e jp \u4e0d\u4e00\u81f4' % tag)
            if (NL in jp) != (NL in cn):
                fails.append('%s \u6362\u884c\u7ed3\u6784\u4e0e jp \u4e0d\u4e00\u81f4' % tag)
            if STRIP_JP.sub('', jp) and not STRIP_CN.sub('', cn):
                fails.append('%s cn \u7591\u4f3c\u5360\u4f4d' % tag)
    print('\u8bed\u6599\u6761\u76ee %d\uff1a\u6807\u8bb0/\u6362\u884c/\u5360\u4f4d \u4e09\u9879\u4e00\u81f4\u6027\u68c0\u67e5\u5b8c\u6210' % n_all)

    n_ins = 0
    for sc, p in sorted(plan['scripts'].items()):
        if p['kind'] != 'host':
            continue
        drops = set(p['drops'])
        for a, r0, r1 in p['inserts']:
            if a in drops:
                fails.append('%s \u63d2\u5165\u951a\u70b9 %d \u843d\u5728\u5220\u683c\u96c6\u5185' % (sc, a))
            for row in range(r0, r1 + 1):
                n_ins += 1
                r = load_corpus(sc).get(row)
                if r is None:
                    fails.append('%s \u539f\u7248\u884c %d \u4e0d\u5728\u8bed\u6599' % (sc, row))
                    continue
                cn = str(r.get('cn', ''))
                if not cn.strip():
                    fails.append('%s \u539f\u7248\u884c %d \u8bed\u6599\u4e3a\u7a7a' % (sc, row))
                if KANA.search(cn):
                    fails.append('%s \u539f\u7248\u884c %d \u8bed\u6599\u542b\u5047\u540d' % (sc, row))
    print('\u8ba1\u5212\u63d2\u5165\u683c %d \u4e2a\uff0c\u8986\u76d6/\u975e\u7a7a/\u65e0\u5047\u540d \u68c0\u67e5\u5b8c\u6210' % n_ins)

    if fails:
        print('\u9884\u68c0\u5931\u8d25 %d \u6761:' % len(fails))
        for x in fails[:20]:
            print('  ', x)
        sys.exit(1)
    print('\u2705 \u9884\u68c0\u901a\u8fc7')


if __name__ == '__main__':
    main()
