# -*- coding: utf-8 -*-
"""汇总机械标定 + 语义判定 -> resource/restore_scope.json（还原范围定案）。

输入：tmp/scope/scope_mech.json（机械区间）、tmp/scope/regions.jsonl、tmp/scope/verdicts.py（134 条判定）
输出：resource/restore_scope.json
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from verdicts import V            # noqa: E402
import scope_extra as X          # noqa: E402


def main():
    mech = json.load(open(os.path.join(HERE, 'scope_mech.json'), encoding='utf-8'))
    regs = [json.loads(l) for l in open(os.path.join(HERE, 'regions.jsonl'), encoding='utf-8')]
    idx = defaultdict(list)
    for r in regs:
        idx[r['script']].append(r)

    meta = mech['meta']
    scripts = {}
    for sc, m in sorted(mech['scripts'].items()):
        if not m.get('orig_rows') and not m.get('steam_rows'):
            continue
        out_regions = []
        for i, r in enumerate(idx.get(sc, [])):
            form, action, h, note = V[(sc, i)]
            out_regions.append({
                'id': i, 'form': form, 'action': action, 'h_level': h,
                'orig_range': r['orig'], 'steam_range': r['steam'],
                'orig_rows': r['no'], 'steam_rows': r['ns'],
                'patch_status': r['patch_status'], 'patch_jp_cover': r['jp_cover'],
                'patch_dropped_steam_rows': len(r['steam_rows_dropped_by_patch']),
                'note': note,
            })
        scripts[sc] = {
            'orig_file': m.get('orig_file'), 'steam_file': m.get('steam_file'),
            'patch_file': m.get('patch_file'),
            'orig_rows': m.get('orig_rows'), 'steam_rows': m.get('steam_rows'),
            'patch_rows': m.get('patch_rows'),
            'voice_anchor_pairs': m.get('anchor_pairs'),
            'regions': out_regions,
        }

    by_form = Counter(v[0] for v in V.values())
    by_act = Counter(v[1] for v in V.values())
    by_h = Counter(v[2] for v in V.values())
    verdict_of = {(r['script'], i): V[(r['script'], i)]
                  for sc, rs in idx.items() for i, r in enumerate(rs)}
    restore_rows = sum(r['no'] for r in regs if verdict_of[(r['script'], idx[r['script']].index(r))][1] != 'no_action')
    h_rows = sum(r['no'] for r in regs if verdict_of[(r['script'], idx[r['script']].index(r))][2] in ('H', '性暗示'))

    scope = {
        'meta': {
            'project': 'If My Heart Had Wings FLIGHT DIARY 内容恢复补丁',
            'generated': '2026-10-13',
            'purpose': '还原范围定案：逐剧本逐区间处置动作。写盘器与计划生成器的唯一输入。',
            'method': (
                '1) 机械标定：ORIG<->STEAM 用语音名 LCS 锚点、STEAM<->PATCH 用台词文本 LCS 锚点，'
                '圈出 134 个差分区间（tmp/scope/scope_mech.py）；'
                '2) 语义核验：4 个 subagent 对 134 区间逐处判定形态（报告 tmp/verify/scope_*.md）；'
                '3) 主控独立复核：原版格式表反汇编两侧、官中 lng 逐槽比对、关键行直接取证。'
            ),
            'forms': X.FORMS,
            'actions': X.ACTIONS,
            'sources': {
                'orig': 'If_My_Heart_Had_Wings_Flight_Diary_Original（2013 日文原版）',
                'steam': 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY（Steam 英文版）',
                'patch': 'If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch（国外还原补丁，参照物）',
                'zh_cn': 'Steam zh-CN/{Rio.arc, Script.arc, Fonts.arc, AdvHDLang.dll}（官中，中文正文来源）',
            },
        },
        'summary': {
            'matched_scripts': meta['matched'],
            'deleted_whole_scripts': meta['deleted_whole'],
            'steam_new_scripts': meta['new_steam'],
            'regions_total': len(regs),
            'regions_by_form': dict(by_form),
            'regions_by_action': dict(by_act),
            'regions_by_h_level': dict(by_h),
            'restore_rows_total': restore_rows,
            'h_or_ecchi_rows': h_rows,
            'patch_text_matching': X.SUMMARY_TEXT['patch_text_matching'],
            'patch_disposition_divergence': X.SUMMARY_TEXT['patch_disposition_divergence'],
            'residual_deletions_not_restored_by_patch': X.SUMMARY_TEXT['residual_deletions_not_restored_by_patch'],
        },
        'scripts': scripts,
        'whole_script_actions': X.WHOLE_SCRIPT_ACTIONS,
        'route_ui': X.ROUTE_UI,
        'julie_guard': 'AKA_*（Rio1.arc / Chip10.arc）内容全部来自 Steam 且自带官中——不动、不校对。',
        'implementation_redlines': X.REDLINES,
    }

    out = os.path.join(PROJ, 'resource', 'restore_scope.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(scope, fh, ensure_ascii=False, indent=1)
    print('写出 %s（%d KB）' % (out, os.path.getsize(out) // 1024))
    print('形态:', dict(by_form))
    print('动作:', dict(by_act))
    print('分级:', dict(by_h))
    print('需还原原版格合计:', restore_rows, '；其中 H/性暗示:', h_rows)


if __name__ == '__main__':
    main()
