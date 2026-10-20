# -*- coding: utf-8 -*-
"""restore_scope.json 的文字性内容（与 build_scope.py 分离，避免单文件过大）。"""

FORMS = {
    'translation_artifact': '翻译拆行伪差异：Steam 英文格就是原版格的翻译，仅拆行/合行 => 无需还原',
    'rewrite': '改写：一一对应、位置没错、内容换成别的段子 => 该格取原版那一行（位置对位）',
    'mixed_censor': '混译+审查替换：区间内 Steam 格部分是原版格的翻译、部分是审查替换/删减（对应原版行无落点）=> 整区间取原版（翻译格随之回源，内容不丢失）',
    'para_delete_new_write': '整段删+新写：原版一段被删，Steam 在同位置写了新内容 => 新写保留；被删的走还原插入',
    'compress_summary': '压缩概述：原版一段被删，Steam 用几格概述压掉 => 几格改取原版首 N 行 + 其余行插入其后',
    'pure_delete': '纯删：Steam 侧无格 => 还原插入全部原版格',
    'pure_add': '纯增：原版侧无格（Steam 新增，非顶替）=> 保留',
}

ACTIONS = {
    'no_action': '保留 Steam 行（中文经官方 .lng 或本项目重译）',
    'replace_with_orig': '该格（位）内容替换为原版对应行',
    'keep_steam_insert_orig': '保留 Steam 新写行，并把被删的原版格还原插入到该位置之后',
    'cells_take_orig_firstN_insert_rest': '该几格取原版首 N 行，其余原版格插入其后',
    'insert_orig_all': '在该位置插入全部原版格',
    'keep': '原样保留',
}
SUMMARY_TEXT = {
    'patch_text_matching': '恰当——11 个 H 脚本补丁缝入的日文格与原版逐格一致（jp_cover 1.0），位置/顺序零错误',
    'patch_disposition_divergence': (
        '补丁把 Steam 新写行删掉再原位填原版（共删 681 行），与本项目「整段删+新写 => 新写保留+还原插入」规则相悖。'
        '经核验这些新写全部是同节拍审查改写（非独立新增），机械执行 keep_steam 会造成无害版+完整版重复；'
        '实现时以 keep_steam_insert_orig 为默认， tonal 重复处经逐处确认后可改 replace_with_orig。'
    ),
    'residual_deletions_not_restored_by_patch': [
        'H 脚本内 29 格未还原（KAN_3001_4 漏 9、BEF_004 漏 3、BEF_003 漏 3、AFT_007_3 漏 1、HUS_001 漏 7 格+5 语音）',
        'AFT_007_3 / BEF_004 / KAN_3001_3 的 EVRET 出口跳转补丁漏还原',
        '非 H 脚本：KAN_2001 处女话题段(49 格)+2 纯删、KAN_3001_5 澡堂戏(6 格)、BEF_005 胸部调侃(7 格)、KAN_2002 朱莉台词主语被改(1 格)、NOV_001 助词丢失',
        'CG_PAGE01-04 画廊未按原版重建（相对原版缺 71/101/114/113 条、顺序不同）',
    ],
}

WHOLE_SCRIPT_ACTIONS = {
    'AGS_001.ws2': {
        'action': 'restore_whole_script',
        'source': 'ORIG AGS_001.ws2（姫城あげは线，Steam 整条删除）',
        'orig_rows': 1121,
        'route_entry': 'mainmenu.ws2 分派表 var[98]==102 入口是活代码（无门控），只需 UI 按钮 7->8',
        'patch_reference': '补丁已整脚本搬入原版并注入 147 处 CG_ACHIEVEMENT（147/147 无漏），可作蓝本',
        'avoid_patch_deviations': [
            'A-1 每条对白多插空 0x15（1121->2242）',
            'A-2 0x46 图层参数 128->240（168 处）',
            'A-3 0x47 特效整型 128->192（34 处）',
            'A-4 0x39 参数 39->31（7 处）',
            'A-5 人名日->罗（635 处，NameTable 需要）',
            'A-6 正文内 碧->Aoi（57 处，不应改）',
            'A-7 0x14 的 u32 序号 0-based->1-based（须保持 0-based）',
        ],
    },
    'CG_PAGE01_E.ws2': {'action': 'rebuild_gallery_from_orig', 'note': '以原版条目集合与顺序重建画廊'},
    'CG_PAGE02_E.ws2': {'action': 'rebuild_gallery_from_orig'},
    'CG_PAGE03_E.ws2': {'action': 'rebuild_gallery_from_orig'},
    'CG_PAGE04_E.ws2': {'action': 'rebuild_gallery_from_orig'},
    'KAN_3002_3_E.ws2': {'action': 'keep', 'note': 'Steam 全年龄替代场景；KAN_3002_2 还原后尾跳须指向 KAN_3003_E 而非本脚本'},
    'CG_Achievement.ws2': {'action': 'keep', 'note': 'Steam 系统脚本，0 台词格'},
    'DDS_ANIME_ERASE.ws2': {'action': 'keep', 'note': 'Steam 系统脚本，0 台词格'},
    'LoadTipsCall.ws2': {'action': 'keep', 'note': 'Steam 系统脚本，0 台词格'},
}

ROUTE_UI = {
    'AGS_001 entry': 'mainmenu.ws2 分派表 var[98]==102 -> AGS_001 已是活代码，脚本层无需改',
    'story_menu_buttons': 'LegacyGame.lua -> openStory -> StoryMenuInit 按钮表 {108,101,103,104,105,106,107}（7 个，102 被移除、槽位复用给朱莉）→ 已改为 8 个并插回 102（142/8），MenuEffectStart 的逐按钮滑入动画上界同步 7→8（142/4）；按钮图形见 resource/route_entry/（定版）',
    'cast_highlight': 'StorySelCursor（142/9）原公式只覆盖 101..107 且 102 与 103 撞格 24 → 已补 id==102 分支显示新增 Cast 图层（记录 29）；initSubLayer（142/8）与两处 hide 循环（142/4、142/9）上界 22..28→22..29',
    'recall_entries': '回想条目 AGS_01/02/03 需补回（原版在 LegacyGame.lua，Steam 移除）——尚未补',
}

REDLINES = [
    '还原区间逐条对齐语音指令，不删任何原版语音条目；同场景统一用原版语音名（ASA_xxxx 而非 Steam VASAxxxx）',
    '还原区间每个 0x33（PNG）事件 CG 显示点（带固有 id 对）后补 04 "CG_ACHIEVEMENT" 00，按站点验收覆盖率',
    '逐脚本核对 0x07 目标：EVRET 出口跳转一个不能漏（AFT_007_3 / BEF_004 / KAN_3001_3）',
    '%LC 说话人名逐条转成 Steam NameTable.txt 的罗马字键（KAN_3002_2 的 307 处是补丁漏转的教训）',
    '0x14 的 u32 序号保持 0-based（补丁 AGS_001 改成 1-based 是偏差）',
    '中文一律走 zh-CN/Rio.arc 的 .lng（key 0x3E）+ NameTable.txt；每改一个脚本必须整体重建该脚本 .lng，不沿用官方条目',
    '还原中文以原版日文为唯一依据，不经英文中转（已发现 2 处英文语义反转/错译：HOT_004 部训、BEF_004 第 251 行）',
    '原版日文 OGG 语音必须随包发布（原版语音 100% 不在 Steam 语音包，缺包会静音）',
]
# <<<MORE>>>
