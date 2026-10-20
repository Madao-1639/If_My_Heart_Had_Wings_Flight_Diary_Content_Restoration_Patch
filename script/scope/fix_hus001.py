# -*- coding: utf-8 -*-
"""修正 HUS_001 的 ORIG↔CN 对齐：原 anchor_map 的段内插值在「段内行数不等」时静默错位。
重映射规则：
  - 锚点行：直接映射（语音名相同）
  - 等长段：整段恒定偏移 p0-o0
  - 不等长段：左对齐作参考，但打 ambiguous 标记（该段以 jp 为唯一依据，CN 仅参考）
"""
import json
import os
import sys
from difflib import SequenceMatcher

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
sys.path.insert(0, FD + '/tmp')
sys.path.insert(0, FD + '/tool')
import scope_mech as M  # noqa: E402
from galrev.advhd import arc, ws2  # noqa: E402

CP = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch/Chinese_Localization_Patch')


def build_map(ro, rc):
    vo = [r['i'] for r in ro if r['voice']]
    vp = [r['i'] for r in rc if r['voice']]
    so = [ro[i]['voice'].upper() for i in vo]
    sp = [rc[i]['voice'].upper() for i in vp]
    sm = SequenceMatcher(None, so, sp, autojunk=False)
    pairs = []
    for b in sm.get_matching_blocks():
        if b.size:
            pairs.extend((vo[b.a + k], vp[b.b + k]) for k in range(b.size))
    amap = {}
    prev = (-1, -1)
    for a, b in pairs + [(len(ro), len(rc))]:
        o0, p0 = prev[0] + 1, prev[1] + 1
        o1, p1 = a - 1, b - 1
        no = max(0, o1 - o0 + 1)
        np_ = max(0, p1 - p0 + 1)
        if a < len(ro):
            amap[a] = (b, 'anchor')
        if no and no == np_:
            for k in range(no):
                amap[o0 + k] = (p0 + k, 'ok')
        elif no:
            # 不等长段：左对齐 + ambiguous
            for k in range(min(no, np_)):
                amap[o0 + k] = (p0 + k, 'ambiguous')
            if no > np_:
                for k in range(np_, no):
                    amap[o0 + k] = (None, 'missing')
        prev = (a, b)
    return amap


def main():
    o = M.load(M.ORIG, 'Rio.arc')
    cnp = {nb.decode('utf-16le'): d for nb, d in arc.read_raw(CP + '/Rio.arc')}
    sc = 'HUS_001'
    ro = M.rows(ws2.decode(o[sc + '.ws2']), M.TM)
    rc = M.rows(ws2.decode(cnp['HUS_001_E.ws2']), M.TF)
    amap = build_map(ro, rc)
    draft = {}
    for l in open(os.path.join(FD, 'resource', 'corpus', 'cn_draft', sc + '.jsonl'),
                  encoding='utf-8'):
        r = json.loads(l)
        draft[r['orig_row']] = r
    n_ok = n_amb = n_miss = 0
    out = []
    for oi in sorted(draft):
        r = draft[oi]
        pi, kind = amap.get(oi, (None, 'missing'))
        cn = rc[pi]['text'] if pi is not None else ''
        if kind == 'ok':
            n_ok += 1
        elif kind == 'ambiguous':
            n_amb += 1
        else:
            n_miss += 1
        out.append(dict(r, patch_row=pi, cn_gemini=cn, align=kind,
                        cn_lang='CN' if cn else 'MISSING'))
    with open(os.path.join(FD, 'resource', 'corpus', 'cn_draft', sc + '.jsonl'),
              'w', encoding='utf-8') as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('HUS_001 重映射：%d 行 = 精确 %d / 歧义参考 %d / 无对应 %d' %
          (len(out), n_ok, n_amb, n_miss))


if __name__ == '__main__':
    main()
