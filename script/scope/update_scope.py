# -*- coding: utf-8 -*-
"""把 Gemini 汉化补丁覆盖评估 + 画廊降级 合入 resource/restore_scope.json。"""
import json
import os
import sys

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
P = os.path.join(FD, 'resource', 'restore_scope.json')

d = json.load(open(P, encoding='utf-8'))

# ---------- 1. Gemini 汉化补丁覆盖评估 ----------
d['gemini_patch_coverage'] = {
    'source': '国外补丁目录 Chinese_Localization_Patch/（Rio.arc 根档 + zh-CN/Rio.arc 40 lng + 字体替换三件套）',
    'what_it_is': (
        '在**国外补丁的 12 个 ws2** 上做了整脚本 Gemini 中文化（其余脚本 = 国外补丁原样 = Steam 英文）。'
        '这 12 个正是国外补丁改过的脚本：10 个 H 脚本 + KAN_3002_1_E + KAN_3002_2。'
        '中文写在 ws2 窄字节（CP932），自带的 zh-CN/Rio.arc 是官方 50 lng 中**剔除这 10 个脚本后**的 40 个。'
    ),
    'translation_source_verified': (
        '**以原版日文为译源**（两处判别测试：① HOT_004 部训，Steam 英文 "Nobody flies alone" 语义反转，'
        '汉化补丁作「最終目標，是讓凜能独自飛行」= 原版语义；② BEF_004 #251 感受主体翻转，'
        '汉化补丁作「在他們身上，我感受到了……厚着臉皮留在他們身邊」= 原版语义）。'
        'Steam 新增行（原版没有的）才回退用英文译（如 HOT_002#674 "We\'ll compete with our feminine charms!" →「武器，就是女人的魅力♪」）。'
        '⇒ 它天然绕开了 Steam 的审查改写与英译错误，与本项目「以原版日文为唯一依据」一致。'
    ),
    'coverage_vs_scope': {
        'H 场景还原范围': '**全覆盖**。我们 scope 的 H 还原格在汉化补丁对应位置几乎都是中文（AFT_003 503/511、AFT_007_3 363/366、BEF_003 306/307、BEF_004 377/390、HOT_002 404+402、HOT_004 635（覆盖全部 7 区间）、HUS_001 391+402、KAN_3001_3 474/483、KAN_3001_4 104/104、KAN_3002_2 392/397、AGS_001 1110/1121）。连 replace_with_orig 小区间也覆盖（它是整脚本翻译）。',
        '非 H 改写还原范围': '**不覆盖**。KAN_2001（5 区间）/ KAN_3001_5（3 区间）/ BEF_005（2 区间）/ KAN_2002（1 区间）不在 12 个脚本内；这些脚本靠官方 zh-CN lng，但 lng 译的是**改写后的英文**（如 KAN_2002#78 官中「我要找的不是滑翔机社，而是水濑和佳奈子」跟着英文，原版是「水瀬碧くん個人に対して」）⇒ 仍需按原版日文重译。',
        '总量': '12 脚本 9512 格中：中文 9325、英文未译 187、日文残留 2（其中落在我们还原区间内的未译约 54 格）。',
    },
    'defects': [
        '窄字节 CP932 ⇒ 文本实为**繁体 + 日文字形混排**（覚/辺/髪/変/醤/軽/裃/両/処/満/咲…），简体专用字写不进去；取用需 OpenCC 链式归一（jp2t→tw2s 或自建映射表），姊妹作无现成表可抄。',
        '约 54 格（还原区间内）未译英文 + 2 格日文乱码残留（BEF_003#906「凜・想・進・去・対・槇・？」、KAN_3001_3#132）⇒ 需补译。',
        '人名/称呼不统一：同脚本内名签用蛍、正文用凜；HUS_001 出现「碧前輩」等与官方 NameTable 不一致的称呼 ⇒ 需按 NameTable 统一。',
        '个别乱码字（鶺/瑶/鞁/鼕 等高频出现，疑窄字节写入损坏）⇒ 需清洗。',
    ],
    'verdict': '**可作还原中文的初译底稿（H 部分），不可直接采用**：覆盖 H 还原范围、译源正确（原版日文）、质量尚可；但需①字形/繁简归一 ②补齐 54 格未译 ③清洗乱码 ④人名统一 ⑤全量审校。非 H 改写部分它不覆盖，仍需自行翻译。',
}

# ---------- 2. 画廊降到最低优先级 ----------
wa = d['whole_script_actions']
for k in ('CG_PAGE01_E.ws2', 'CG_PAGE02_E.ws2', 'CG_PAGE03_E.ws2', 'CG_PAGE04_E.ws2'):
    if k in wa:
        wa[k]['priority'] = 'P3-lowest'
        wa[k]['note'] = '以原版条目集合与顺序重建画廊；**用户决策：当前专注于内容还原，画廊机制优先级放最末**'
for k in ('AGS_001.ws2',):
    wa[k]['priority'] = 'P1'
d.setdefault('priorities', {
    'P1': '内容还原（H 场景 + 非 H 改写 + 姬城线入口）',
    'P2': '中文落地（lng 重建、字形归一、审校）',
    'P3-lowest': '画廊（CG_PAGE01-04）重建——不阻塞内容还原',
})

# ---------- 3. KAN_2002 朱莉线的判定补注 ----------
for sc in ('KAN_2002',):
    for r in d['scripts'][sc]['regions']:
        if r['id'] == 1:
            r['note'] += ('；三版对照：JP「用があるのはソアリング部ではなく、水瀬碧くん個人に対してよ」（商谈对象=碧本人）→ '
                          'EN "something personal between Aoi and Kanako"（改写为碧×佳奈子之间）→ '
                          '官中「我要找的不是滑翔机社，而是水濑和佳奈子」（跟着英文）；该行被 Steam 换装重录（VAKA0018，'
                          '邻行仍用 AKARI_0072/0074）')

with open(P, 'w', encoding='utf-8') as fh:
    json.dump(d, fh, ensure_ascii=False, indent=1)
print('已更新', P, os.path.getsize(P) // 1024, 'KB')
