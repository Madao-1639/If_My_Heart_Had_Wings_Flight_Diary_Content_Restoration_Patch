# -*- coding: utf-8 -*-
"""还原计划生成（本作 Flight Diary，S2）。

输入：`resource/restore_scope.json`（逐剧本逐区间动作定案）+ `backup/`（Steam 基线）
      + 原版发行目录。
产出：`resource/restore_plan.json`（写盘器 `tool/writer.py` 的唯一输入）+ `tmp/restore_plan.md`。

对齐轴（与 `script/scope/scope_mech.py` 同一套，保证区间口径一致）
--------------------------------------------------------------
`0x14` 台词行 = 「格」。ORIG ↔ STEAM 的锚点 = **语音名 LCS**（Steam 未删改的格沿用原版
语音文件名 ⇒ 同名即同一格）。相邻锚点之间的行区间 = 一个 gap；gap 内两侧行数不等、或
等长但逐位语音名不符，才是**差分区间**（`restore_scope.json` 的 region 就是这些）。

计划语义
--------
* `kind='host'`：以 Steam `X_E.ws2` 为宿主，**删** acting 区间的 Steam 格（含其演出
  前缀），**插** 对应区间的原版格（经 `tool.ws2conv.CONV` 格式差转换）。
* `kind='whole'`：Steam 侧无同名脚本（`AGS_001`）⇒ 整脚本跨版本转换 + 注入成就。

插入块的成就注入
----------------
本作 Steam 侧**每一个** `0x33`（PNG 显示）+ 紧随两条 `0x0b`（固有 id 对）之后都有
`04 "CG_ACHIEVEMENT" 00`；原版同位置是 `04 "LAYER_ORDER"`。故还原块按同型补齐：
在「`0x33` + `0x0b` + `0x0b`」之后插 `04 "CG_ACHIEVEMENT" 00`。

`%LC` 说话人名
--------------
`0x15` 操作数 = `%LC<名>` + NUL（窄字节 cp932）。原版写日文名、Steam 写罗马字键
（`Rio.arc` 的 `NameTable.txt` 以键索引中文名）⇒ 还原块内的 `0x15` 必须逐条换成 Steam 键，
否则名字框失配。映射表由**全量对齐的未还原行**统计得出（同一 ORIG 名 → 多数 Steam 键）。
"""
import collections
import json
import os
import sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import paths, ws2, ws2dis, ws2conv, ws2fmt  # noqa: E402

OUT_JSON = os.path.join(ROOT, 'resource', 'restore_plan.json')
OUT_MD = os.path.join(ROOT, 'tmp', 'restore_plan.md')

ACH_CALL = (0x04, b'CG_ACHIEVEMENT\x00')


def load_arc(root, name):
    from galrev.advhd import arc
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(os.path.join(root, name))}


GALREV = os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')
if GALREV not in sys.path:
    sys.path.insert(0, GALREV)


def orig_table():
    t = ws2fmt.Table(os.path.join(ROOT, 'resource', 'ws2_formats_orig.json'))
    t.fmt.update({op: list(f) for op, f in ws2dis.ORIG_TABLE_PATCH.items()})
    return t


def rows(dec, tab):
    """[(off, name, text, voice)]；voice = 紧邻其前的 `0x28 char*` 的 OGG 名。"""
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
                        and not x.upper().endswith('.OGG') and x != 'char':
                    t = x
            out.append({'off': off, 'name': cur, 'text': t, 'voice': pending})
            pending = None
    for i, r in enumerate(out):
        r['i'] = i
    return out


def lcs_pairs(a, b):
    out = []
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if blk.size:
            out.extend((blk.a + k, blk.b + k) for k in range(blk.size))
    return out


def gaps(ro, rs):
    """相邻锚点之间的行区间 → [(o0, o1, s0, s1)]（闭区间；空侧以 o1<o0 / s1<s0 表示）。"""
    vo = [r['i'] for r in ro if r['voice']]
    vs = [r['i'] for r in rs if r['voice']]
    anchors = lcs_pairs([ro[i]['voice'].upper() for i in vo],
                        [rs[i]['voice'].upper() for i in vs])
    anchors = [(vo[a], vs[b]) for a, b in anchors]
    bnds = [(-1, -1)] + anchors + [(len(ro), len(rs))]
    out = []
    for k in range(len(bnds) - 1):
        (oa, sa), (ob, sb) = bnds[k], bnds[k + 1]
        out.append((oa + 1, ob - 1, sa + 1, sb - 1))
    return out, anchors


def load_perf_sync():
    """resource/perf_sync_map.json → {script: {slot: spec}}（st/bg 演出同步）。"""
    out = collections.defaultdict(dict)
    fp = os.path.join(ROOT, 'resource', 'perf_sync_map.json')
    if os.path.exists(fp):
        for site in json.load(open(fp, encoding='utf-8')).get('sites', []):
            act = site.get('action')
            if act == 'replace' and site.get('orig_row') is not None:
                out[site['script']][int(site['slot'])] = {'mode': 'replace',
                                                          'orig_row': int(site['orig_row'])}
            elif act == 'drop':
                out[site['script']][int(site['slot'])] = {'mode': 'drop',
                                                          'channels': site.get('channels') or []}
    return out


def load_perf_manual():
    """resource/perf_sync_manual.json → {script: {slot: spec}}（人工/闸驱动的处置）。"""
    out = collections.defaultdict(dict)
    fp = os.path.join(ROOT, 'resource', 'perf_sync_manual.json')
    if os.path.exists(fp):
        d = json.load(open(fp, encoding='utf-8'))
        for e in d.get('drops') or []:
            out[e['script']][int(e['slot'])] = {'mode': 'drop',
                                                'channels': [e.get('chan')] if e.get('chan') else e.get('channels') or []}
        for e in d.get('replaces') or []:
            out[e['script']][int(e['slot'])] = {'mode': 'replace',
                                                'orig_row': int(e['orig_row'])}
        for e in d.get('keeps') or []:
            k = int(e['slot'])
            spec = out[e['script']].setdefault(k, {'mode': 'drop', 'channels': []})
            spec.setdefault('keep', []).append(e['chan'])
    return out


def inject_achievements(instrs):
    """在「`0x33` + `0x0b` + `0x0b`」之后插 `04 CG_ACHIEVEMENT 00`。返回 (新列表, 注入数)。"""
    out, n, j = [], 0, 0
    while j < len(instrs):
        out.append(instrs[j])
        if instrs[j][0] == 0x33 and j + 2 < len(instrs) \
                and instrs[j + 1][0] == 0x0b and instrs[j + 2][0] == 0x0b:
            out.append(instrs[j + 1])
            out.append(instrs[j + 2])
            out.append(ACH_CALL)
            n += 1
            j += 3
            continue
        j += 1
    return out, n


def main():
    scope = json.load(open(os.path.join(ROOT, 'resource', 'restore_scope.json'), encoding='utf-8'))
    steam = load_arc(paths.STEAM, 'Rio.arc')
    orig = load_arc(paths.orig_dir(), 'Rio.arc')
    o_tab = orig_table()
    s_tab = ws2fmt.Table(os.path.join(ROOT, 'resource', 'ws2_formats.json'))
    orig_fmts = ws2conv.load_orig_formats(paths.orig_dir())
    PERF_SYNC = load_perf_sync()
    PERF_MANUAL = load_perf_manual()

    # ── 1) 全量对齐：统计 %LC 名映射 + 逐脚本 gap 表 ──────────────────────
    name_votes = collections.defaultdict(collections.Counter)
    per_script = {}
    for sc, rec in sorted(scope['scripts'].items()):
        of, sf = rec.get('orig_file'), rec.get('steam_file')
        if not of or not sf:
            continue
        ro = rows(ws2.decode(orig[of]), o_tab)
        rs = rows(ws2.decode(steam[sf]), s_tab)
        g, anchors = gaps(ro, rs)
        per_script[sc] = {'orig_file': of, 'steam_file': sf, 'ro': ro, 'rs': rs,
                          'gaps': g, 'anchors': len(anchors)}
        for (o0, o1, s0, s1) in g:
            if o1 < o0 or s1 < s0 or (o1 - o0) != (s1 - s0):
                continue
            for k in range(o1 - o0 + 1):
                on, sn = ro[o0 + k]['name'], rs[s0 + k]['name']
                if on and sn and on != sn:
                    name_votes[on][sn] += 1

    name_map = {on: c.most_common(1)[0][0] for on, c in name_votes.items()}
    # 兜底种子（AGS_001 无 Steam 对照，名字只能手工定；键必须存在于 NameTable）
    # `イスカ` / `亜紗・依瑠`：本作还原行里出现的原版名牌键（Steam 键为 `Isuka` /
    # `Asa, Yoru`，NameTable 已收录）——2026-10-20 全量演出评审发现漏映射。
    name_map.update({'あげは': 'Ageha', 'ほたる': 'Hotaru', '碧': 'Aoi', '亜紗': 'Asa',
                     '小鳥': 'Kotori', '依瑠': 'Yoru', '伊斯卡': 'Isuka', '天音': 'Amane',
                     '佳奈子': 'Kanako', '朱莉': 'Akari',
                     'イスカ': 'Isuka', '亜紗・依瑠': 'Asa, Yoru'})

    # ── 2) 逐脚本生成计划 ───────────────────────────────────────────────
    plans, md = {}, []
    for sc, rec in sorted(scope['scripts'].items()):
        acting = [r for r in rec['regions']
                  if r['action'] not in ('no_action', 'keep')]   # keep = 原样保留，不得进 drops
        if not acting:
            continue
        info = per_script[sc]
        gapset = set(info['gaps'])
        drops, inserts = [], []
        for r in acting:
            key = (r['orig_range'][0], r['orig_range'][1],
                   r['steam_range'][0], r['steam_range'][1])
            if key not in gapset:
                raise SystemExit('%s 区间 %r 与锚点 gap 不吻合' % (sc, key))
            if key[3] >= key[2]:
                drops.extend(range(key[2], key[3] + 1))
            if key[1] >= key[0]:
                inserts.append([key[2] - 1, key[0], key[1]])
        inserts.sort()

        raw = ws2.decode(orig[info['orig_file']])
        o_instrs, _tail = ws2conv.parse(raw, orig_fmts)
        # ⚠️ 不注入成就（ORIG 与 Steam 的 CG id 对交集为 0，注入是空操作）；
        #    此处只记 ORIG 侧站点数，供与 Steam 侧对照。
        n_sites = sum(1 for j, (op, _) in enumerate(o_instrs)
                      if op == 0x33 and j + 2 < len(o_instrs)
                      and o_instrs[j + 1][0] == 0x0b and o_instrs[j + 2][0] == 0x0b)
        ps = dict(PERF_SYNC.get(sc, {}))
        for _k, _v in PERF_MANUAL.get(sc, {}).items():
            ps[_k] = _v
        clash = set(ps) & set(drops)
        assert not clash, '%s: 演出同步槽 %s 同时登记为删格' % (sc, sorted(clash))
        plans[sc] = {'kind': 'host', 'steam_file': info['steam_file'],
                     'orig_file': info['orig_file'], 'drops': sorted(set(drops)),
                     'inserts': inserts, 'regions': len(acting), 'orig_cg_sites': n_sites,
                     'perf_sync': {str(k): v for k, v in sorted(ps.items())}}
        md.append('| %s | host | %s | 删 %d 格 | 插 %d 段 / %d 格 | ORIG CG 站点 %d（不注入） |'
                  % (sc, info['steam_file'], len(plans[sc]['drops']), len(inserts),
                     sum(r['orig_rows'] for r in acting), n_sites))

    # ── 3) AGS_001 整脚本 ──────────────────────────────────────────────
    for fn, spec in sorted(scope.get('whole_script_actions', {}).items()):
        if spec.get('action') != 'restore_whole_script':
            continue
        base = fn[:-4]
        raw = ws2.decode(orig[base + '.ws2'])
        o_instrs, _t = ws2conv.parse(raw, orig_fmts)
        n_sites = sum(1 for j, (op, _) in enumerate(o_instrs)
                      if op == 0x33 and j + 2 < len(o_instrs)
                      and o_instrs[j + 1][0] == 0x0b and o_instrs[j + 2][0] == 0x0b)
        plans[base] = {'kind': 'whole', 'orig_file': base + '.ws2', 'steam_file': None,
                       'orig_cg_sites': n_sites, 'target_member': base + '.ws2'}
        md.append('| %s | whole | — | — | 整脚本 %d 格 | ORIG CG 站点 %d（不注入） |'
                  % (base, sum(1 for op, _ in o_instrs if op == 0x14), n_sites))

    out = {'meta': {'orig_dir': paths.orig_dir(), 'steam_dir': paths.STEAM,
                    'name_map': name_map, 'scripts': len(plans)},
           'scripts': plans}
    with open(OUT_JSON, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w', encoding='utf-8') as fh:
        fh.write('# 还原计划（S2）\n\n| 脚本 | kind | 宿主 | 删格 | 插入 | 成就 |\n|---|---|---|---|---|---|\n')
        fh.write('\n'.join(md) + '\n\n## %%LC 名映射（%d 条）\n\n' % len(name_map))
        fh.write(json.dumps(name_map, ensure_ascii=False, indent=1) + '\n')
    print('写出 %s（%d 脚本）' % (OUT_JSON, len(plans)))
    print('\n'.join(md))
    print('\n%%LC 名映射 %d 条：%s' % (len(name_map), json.dumps(name_map, ensure_ascii=False)))


if __name__ == '__main__':
    main()
