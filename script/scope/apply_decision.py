# -*- coding: utf-8 -*-
"""应用用户决策：① tonal 重复一律「直接替换」；② Gemini 译文做底稿（走 lng，禁窄字节机制）。"""
import json
import os
from collections import Counter

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
P = os.path.join(FD, 'resource', 'restore_scope.json')

d = json.load(open(P, encoding='utf-8'))

# ① keep_steam_insert_orig → replace_with_orig（tonal 重复，用户决策：直接替换）
n = 0
for sc, v in d['scripts'].items():
    for r in v['regions']:
        if r['action'] == 'keep_steam_insert_orig':
            r['action'] = 'replace_with_orig'
            r['note'] = ('[用户决策：tonal 重复一律直接替换] ' + r['note'])
            n += 1
print('改写 action 的区间数：', n)

d['summary']['regions_by_action'] = dict(Counter(
    r['action'] for v in d['scripts'].values() for r in v['regions']))
d['summary']['disposition_decision'] = (
    '用户决策（2026-10-15）：Steam 审查新写与原版 H 段二选一时**一律直接替换为原版**'
    '（不保留全年龄替代场景，避免 tonal 重复）。⇒ 形态仍记为 para_delete_new_write（那是 Steam 的行为），'
    '但处置动作统一为 replace_with_orig。此与国外补丁做法一致（它也是删新写、原位填原版）。'
)
d['summary']['patch_disposition_divergence'] = (
    '补丁删 Steam 新写行再原位填原版（共 681 行）——**本项目已决策照此办理**（直接替换），'
    '故不再视为与规则相悖。'
)

# ② Gemini 译文取用方式
g = d['gemini_patch_coverage']
g['adoption_decision'] = (
    '用户决策（2026-10-15）：**以 Gemini 译文为中文底稿**，只取其文本；'
    '**禁止沿用其生效机制**（窄字节 CP932 直写 ws2 是妥协），中文一律走 zh-CN/Rio.arc 的 .lng（key 0x3E）+ NameTable.txt。'
    '必经流程：归一（繁/日字形→规范简体）+ 补译（约 54 格未译 + 2 格日文乱码）+ 清洗（乱码字）+ 统一（人名按 NameTable）+ 全量审校。'
)
g['output_target'] = 'resource/corpus/cn/<script>.jsonl（逐格中文，lng 生成器的输入）'

with open(P, 'w', encoding='utf-8') as fh:
    json.dump(d, fh, ensure_ascii=False, indent=1)
print('已更新', P, os.path.getsize(P) // 1024, 'KB')
print('动作分布:', d['summary']['regions_by_action'])
