# -*- coding: utf-8 -*-
"""收尾修残：① 删掉失效的复审 diff（r12#557，映射已修正）② \\n 数量对齐（少则按比例补、多则删）
③ 零星乱码字/破折号 ④ 重新合并后跑最终质检。"""
import glob
import json
import os
import re
import sys

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
sys.path.insert(0, FD + '/tmp/scope')
import merge_cn2  # noqa: E402  (复用其常量)

DROP_DIFFS = {('BEF_003', 557)}   # r12 的这条基于旧错位映射，已失效
CHAR_FIX = [
    ('鰰', '糟'),      # HUS_001#353 糟鰰 → 糟糕
    ('鷏险', '险些'),  # HUS_001#525
    ('咬门子', '哪门子'),
    ('――', '──'),     # KAN_3002_2#38：与原版的 ── 对齐
    ('齧', '哪'),      # 齧門子 → 哪门子
]
KANA = re.compile(r'[\u3040-\u30ff]')
RARE = set('閖鯆鵤驫鐔鰊鱚鮹鷭駻鷁鰰鴃鮴駲苙鞐鱆鰤鯔鶸鷏鷆髞闍鵺爍鋺鰡麭齧鵞鰮鮠繋')


def n_breaks(s):
    return s.count('\\n')


def fix_breaks(jp, cn):
    """把 cn 的字面 \\n 数量对齐到 jp：少则按 jp 断点比例补，多则从后往前删。"""
    kj, kc = n_breaks(jp), n_breaks(cn)
    if kj == kc:
        return cn
    if kj > kc:
        parts = jp.split('\\n')
        total = sum(len(p) for p in parts)
        points = []
        acc = 0
        for p in parts[:-1]:
            acc += len(p)
            points.append(acc / float(total))
        need = kj - kc
        L = len(cn)
        for k in range(need):
            pos = int(L * points[min(kc + k, len(points) - 1)])
            pos = max(1, min(pos, L - 1))
            cn = cn[:pos] + '\\n' + cn[pos:]
        return cn
    # kj < kc：从后往前删多余的
    while n_breaks(cn) > kj:
        i = cn.rfind('\\n')
        cn = cn[:i] + cn[i + 2:]
    return cn


def main():
    # ① 清掉失效 diff
    p = os.path.join(FD, 'tmp', 'verify', 'cn2', 'r12_BEF_003_557-559.jsonl')
    if os.path.exists(p):
        rows = [json.loads(l) for l in open(p, encoding='utf-8')]
        keep = [r for r in rows if ('BEF_003', r['i']) not in DROP_DIFFS]
        with open(p, 'w', encoding='utf-8') as fh:
            for r in keep:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        print('清理失效 diff：%d → %d 行' % (len(rows), len(keep)))

    # ② 先跑合并 + 修残
    merge_cn2.main()
    import fix_merge_residual as F
    F.main()

    # ③ \\n 对齐 + 零星字符修
    n_br = n_ch = 0
    for f in sorted(glob.glob(os.path.join(merge_cn2.OUT, '*.jsonl'))):
        rows = []
        for l in open(f, encoding='utf-8'):
            r = json.loads(l)
            cn = r['cn']
            for a, b in CHAR_FIX:
                if a in cn:
                    cn = cn.replace(a, b)
                    n_ch += 1
            new = fix_breaks(r['jp'], cn)
            if new != cn:
                n_br += 1
                cn = new
            r['cn'] = cn
            rows.append(r)
        with open(f, 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('\\n 对齐 %d 行；零星字符修 %d 处' % (n_br, n_ch))

    # ④ 最终质检
    ok = punct = 0
    issues = []
    for f in sorted(glob.glob(os.path.join(merge_cn2.OUT, '*.jsonl'))):
        sc = os.path.basename(f)[:-6]
        for l in open(f, encoding='utf-8'):
            r = json.loads(l)
            jp, cn = r['jp'], r['cn']
            _M = re.compile(r'%K%P|%P|\\d.*?\\d|\\n')
            if not re.search(r'[\u3040-\u30ff\u4e00-\u9fffA-Za-z]', _M.sub('', jp)) \
                    and cn.strip() == jp.strip():
                punct += 1
                continue
            if not re.search(r'[\u4e00-\u9fff]', cn):
                issues.append('%s#%d 无中文' % (sc, r['orig_row']))
                continue
            if (jp.count('%K%P'), jp.count('\\n')) != (cn.count('%K%P'), cn.count('\\n')):
                issues.append('%s#%d 标记不一致 jp=%s cn=%s' % (
                    sc, r['orig_row'], (jp.count('%K%P'), jp.count('\\n')),
                    (cn.count('%K%P'), cn.count('\\n'))))
            elif KANA.search(cn):
                issues.append('%s#%d 假名残留' % (sc, r['orig_row']))
            elif RARE & set(cn):
                issues.append('%s#%d 乱码字 %s' % (sc, r['orig_row'], ''.join(sorted(RARE & set(cn)))))
            else:
                ok += 1
    print('最终质检：合格 %d；纯标点 %d；问题 %d' % (ok, punct, len(issues)))
    for x in issues[:20]:
        print('   ', x)


if __name__ == '__main__':
    main()
