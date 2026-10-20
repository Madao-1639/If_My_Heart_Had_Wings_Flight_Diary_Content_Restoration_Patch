"""还原范围 · 机械标定：ORIG ↔ STEAM ↔ PATCH 三方全量差分。

对齐方法
--------
1. `0x14` 台词行 = 「格」。每格带：speaker（%LC 名）、voice（紧邻其前的 `0x28 char*` 的 OGG 名）、text。
2. ORIG ↔ STEAM 锚点 = **语音名 LCS**（ Steam 未删改的格沿用原版语音文件名 ⇒ 同名即同一格）。
3. STEAM ↔ PATCH 锚点 = **台词文本 LCS**（补丁 = Steam 英文行原样 + 缝入日文块 ⇒ 英文行逐字相同）。
4. 两个锚点之间的行数不等 ⇒ 差分区间。逐区间记录两侧行数、语音名、是否落在 Steam 语音包内。
5. 通过 STEAM↔PATCH 锚点把区间映射到 PATCH，看补丁在该区间缝了多少日文行、这些行是否就是
   ORIG 缺口里的行（文本 LCS 匹配度）⇒ 判定补丁是否已还原、还原位置是否恰当。

形态候选（机械形状，仅供圈位置，不能定案）
----------------------------------------
- 纯删（无新写）  ns == 0
- 纯增（Steam 新写） no == 0
- 改写候选(1:1)  no == ns        —— 行号连续、格数 = 行数
- 压缩候选       0 < ns < no     —— 格数 < 行数
- 扩写候选       ns > no

输出：tmp/scope_mech.json（总表）+ tmp/scope/regions.jsonl（逐区间上下文，供语义核验）。
"""
import json
import os
import re
import sys
from difflib import SequenceMatcher

GAL = 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev'
PATCHDIR = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
            'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'
OUT = PATCHDIR + '/tmp/scope'

sys.path.insert(0, GAL)
sys.path.insert(0, PATCHDIR + '/tool')
from galrev.advhd import arc, ws2
import ws2fmt

TO = ws2fmt.Table(PATCHDIR + '/resource/ws2_formats_orig.json')
TF = ws2fmt.Table(PATCHDIR + '/resource/ws2_formats.json')
TM = ws2fmt.Table.__new__(ws2fmt.Table)
TM.fmt = dict(TO.fmt)
for _op in (0x5f, 0x80):
    if _op in TF.fmt:
        TM.fmt[_op] = TF.fmt[_op]

_JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
DUMP_ROWS = 30          # 每区间每侧最多导出的行数
TXT_CAP = 300


def load(root, an):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(root + '/' + an)}


def rows(dec, tab):
    """[(off, speaker, text, voice)]，voice = 紧邻其前的 `0x28 char*` 的 OGG 名。"""
    out, cur, pending = [], '', None
    for off, op, sz, f in ws2fmt.disassemble(dec, tab):
        a = f.get('args') or []
        if op == 0x28:
            slot = a[0] if a and isinstance(a[0], str) else ''
            ogg = ''
            for x in a:
                if isinstance(x, str) and x.upper().endswith('.OGG'):
                    ogg = x
            pending = ogg if slot.startswith('char') and ogg else None
        elif op == 0x15:
            s = a[0] if a and isinstance(a[0], str) else ''
            cur = s[3:] if s.startswith('%LC') else ''
        elif op == 0x14:
            t = ''
            for x in a:
                if isinstance(x, str) and not x.startswith('%LC') \
                        and not x.upper().endswith('.OGG') and x not in ('char',):
                    t = x
            out.append({'off': off, 'name': cur, 'text': t, 'voice': pending})
            pending = None
    for i, r in enumerate(out):
        r['i'] = i
    return out


def lcs_pairs(a, b):
    """返回 LCS 的逐对索引 [(ia, ib), ...]。"""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for blk in sm.get_matching_blocks():
        if blk.size:
            out.extend((blk.a + k, blk.b + k) for k in range(blk.size))
    return out


def isjp(s):
    """非 ASCII ⇒ 日文行（英文行只有 ASCII：正文 + %K%P / \\d 标记）。"""
    return any(ord(c) > 0x7F for c in s)


def cut(s, n=TXT_CAP):
    return s if len(s) <= n else s[:n] + '…'


def dump(rs, lo, hi):
    return [{'i': r['i'], 'name': r['name'], 'voice': r['voice'], 'text': cut(r['text'])}
            for r in rs[lo:hi + 1]]


def main():
    os.makedirs(OUT, exist_ok=True)
    o = load(ORIG, 'Rio.arc')
    s = load(STEAM, 'Rio.arc')
    p = load(PATCH, 'Rio.arc')
    ow = {nb.decode('utf-16le').upper() for nb, _ in arc.read_raw(ORIG + '/Voice.arc')}
    sw = {nb.decode('utf-16le').upper() for nb, _ in arc.read_raw(STEAM + '/Voice.arc')}

    def ws2names(d):
        return [n for n in d if n.lower().endswith('.ws2')]

    obases = sorted(n[:-4] for n in ws2names(o))
    sbases = sorted(n[:-4] for n in ws2names(s))
    pbases = sorted(n[:-4] for n in ws2names(p))

    def member(d, base):
        """按 base 找回真实成员名（扩展名大小写可能不一）。"""
        for n in d:
            if n[:-4] == base:
                return n
        return None

    pairs, deleted = [], []
    for b in obases:
        if b + '_E' in sbases:
            pairs.append((b, b + '_E'))
        elif b in sbases:
            pairs.append((b, b))
        else:
            deleted.append(b)
    used = {y for _, y in pairs}
    newsteam = [b for b in sbases if b not in used]

    regions_lines = []
    scripts = {}
    for ob, sb in pairs:
        rec = {'orig_file': member(o, ob), 'steam_file': member(s, sb)}
        try:
            ro = rows(ws2.decode(o[member(o, ob)]), TM)
        except ws2fmt.Bad as e:
            rec['error'] = 'ORIG 反汇编失败: %s' % e
            scripts[ob] = rec
            continue
        rs = rows(ws2.decode(s[member(s, sb)]), TF)
        pn = None
        if ob in pbases:
            pn = ob
        elif ob + '_E' in pbases:
            pn = ob + '_E'
        rp = rows(ws2.decode(p[member(p, pn)]), TF) if pn else None
        rec['patch_file'] = member(p, pn) if pn else None

        # ---- ORIG↔STEAM 锚点（语音名 LCS）----
        vo = [r['i'] for r in ro if r['voice']]
        vs = [r['i'] for r in rs if r['voice']]
        so = [ro[i]['voice'].upper() for i in vo]
        ss = [rs[i]['voice'].upper() for i in vs]
        anchors = [(vo[a], vs[b]) for a, b in lcs_pairs(so, ss)]
        rec.update(orig_rows=len(ro), steam_rows=len(rs), patch_rows=len(rp) if rp else None,
                   orig_voiced=len(vo), steam_voiced=len(vs),
                   patch_voiced=sum(1 for r in rp if r['voice']) if rp else None,
                   anchor_pairs=len(anchors))

        # ---- STEAM↔PATCH 锚点（文本 LCS）----
        sp = []
        dropped_steam, inserted_patch = set(), set()
        if rp is not None:
            sp = lcs_pairs([r['text'] for r in rs], [r['text'] for r in rp])
            for tag, i1, i2, j1, j2 in SequenceMatcher(
                    None, [r['text'] for r in rs], [r['text'] for r in rp],
                    autojunk=False).get_opcodes():
                if tag in ('delete', 'replace'):
                    dropped_steam.update(range(i1, i2))
                if tag in ('insert', 'replace'):
                    inserted_patch.update(range(j1, j2))
        sp_sorted = sorted(sp)

        def bracket(s0, s1):
            """STEAM 行区间 [s0..s1]（两侧为锚点行）映射到 PATCH 的 inclusive 区间。"""
            left = -1
            for si, pi in sp_sorted:
                if si <= s0 - 1:
                    left = pi
                else:
                    break
            right = len(rp)
            for si, pi in sp_sorted:
                if si >= s1 + 1:
                    right = pi
                    break
            return left + 1, right - 1

        steam_voice_set = {r['voice'].upper() for r in rs if r['voice']}
        bnds = [(-1, -1)] + anchors + [(len(ro), len(rs))]
        regs = []
        for k in range(len(bnds) - 1):
            (oa, sa), (ob2, sb2) = bnds[k], bnds[k + 1]
            o0, o1 = oa + 1, ob2 - 1
            s0, s1 = sa + 1, sb2 - 1
            no = max(0, o1 - o0 + 1)
            ns = max(0, s1 - s0 + 1)
            if not no and not ns:
                continue
            oor = ro[o0:o1 + 1]
            ssr = rs[s0:s1 + 1]

            # 等长区间逐位比对语音：位置对得上但语音名不同 ⇒ Steam 换装了这一行（改写候选）
            voice_rewrite = []
            if no and no == ns:
                for a, b in zip(oor, ssr):
                    va, vb = (a['voice'] or '').upper(), (b['voice'] or '').upper()
                    if va != vb:
                        voice_rewrite.append({'orig_i': a['i'], 'steam_i': b['i'],
                                              'orig_voice': a['voice'], 'steam_voice': b['voice']})
            # 只有「行数不等」或「等长但语音逐位不符」才算差分区间
            if no == ns and not voice_rewrite:
                continue

            if ns == 0:
                shape = '纯删(无新写)'
            elif no == 0:
                shape = '纯增(Steam新写)'
            elif no == ns:
                shape = '改写候选(1:1+换装)'
            elif ns < no:
                shape = '压缩候选'
            else:
                shape = '扩写候选'

            o_voices = [r['voice'] for r in oor if r['voice']]
            s_voices = [r['voice'] for r in ssr if r['voice']]
            o_noanchor = [v for v in o_voices if v.upper() not in sw]
            o_elsewhere = [v for v in o_voices if v.upper() in sw and v.upper() not in steam_voice_set]
            s_steamonly = [v for v in s_voices if v.upper() not in ow]

            # ---- PATCH 覆盖 ----
            patch_status, jp_cnt, jp_match, jp_ratio = 'n/a', 0, 0, None
            p0 = p1 = None
            if rp is not None and no:
                p0, p1 = bracket(s0, s1)
                prs = rp[p0:p1 + 1]
                jp = [r for r in prs if isjp(r['text'])]
                jp_cnt = len(jp)
                ot = [r['text'] for r in oor]
                jt = [r['text'] for r in jp]
                jp_match = len(lcs_pairs(ot, jt)) if jt else 0
                jp_ratio = round(jp_match / float(no), 4)
                if jp_cnt == 0:
                    patch_status = 'not_restored'
                elif jp_match >= 0.95 * no:
                    patch_status = 'restored'
                else:
                    patch_status = 'partial'
            elif rp is not None and no == 0:
                patch_status = 'n/a(纯增)'

            # 补丁对 Steam 侧行的处置：删了哪些（替换）、原位保留哪些
            dropped = [r['i'] for r in ssr if r['i'] in dropped_steam]
            ins_jp = 0
            if rp is not None and p0 is not None and p1 >= p0:
                ins_jp = sum(1 for j in range(p0, p1 + 1)
                             if j in inserted_patch and isjp(rp[j]['text']))

            reg = {
                'script': ob, 'kind': 'gap',
                'orig': [o0, o1], 'steam': [s0, s1], 'patch': [p0, p1] if rp else None,
                'no': no, 'ns': ns, 'np': (p1 - p0 + 1) if (rp and p0 is not None) else None,
                'shape': shape, 'patch_status': patch_status,
                'jp_rows_in_patch': jp_cnt, 'jp_text_match': jp_match, 'jp_cover': jp_ratio,
                'patch_inserted_jp': ins_jp,
                'steam_rows_dropped_by_patch': dropped,
                'voice_rewrite': voice_rewrite,
                'o_voices': o_voices, 's_voices': s_voices,
                'o_voices_not_in_steam_arc': o_noanchor,
                'o_voices_elsewhere_in_steam': o_elsewhere,
                's_voices_steam_only': s_steamonly,
                'orig_sample': dump(ro, o0, min(o1, o0 + DUMP_ROWS - 1)),
                'steam_sample': dump(rs, s0, min(s1, s0 + DUMP_ROWS - 1)),
                'truncated': (no > DUMP_ROWS) or (ns > DUMP_ROWS),
            }
            regs.append(reg)
            regions_lines.append(reg)

        rec['regions'] = [{k: v for k, v in r.items()
                           if k not in ('orig_sample', 'steam_sample')} for r in regs]
        scripts[ob] = rec
        print('%-14s ORIG=%-5d STEAM=%-5d PATCH=%-5s  锚点=%-4d 区间=%-3d %s' % (
            ob, len(ro), len(rs), len(rp) if rp else 'N/A', len(anchors), len(regs),
            'ERR' if 'error' in rec else ''))

    with open(os.path.join(OUT, 'scope_mech.json'), 'w', encoding='utf-8') as fh:
        json.dump({'meta': {'orig_scripts': len(obases), 'steam_scripts': len(sbases),
                            'patch_scripts': len(pbases), 'matched': len(pairs),
                            'deleted_whole': deleted, 'new_steam': newsteam},
                   'scripts': scripts}, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'regions.jsonl'), 'w', encoding='utf-8') as fh:
        for r in regions_lines:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('\n整条被删的 ORIG 脚本 %d 个：%s' % (len(deleted), deleted))
    print('Steam 新增脚本 %d 个：%s' % (len(newsteam), newsteam))
    print('差分区间合计 %d 个 → tmp/scope/regions.jsonl' % len(regions_lines))


if __name__ == '__main__':
    main()
