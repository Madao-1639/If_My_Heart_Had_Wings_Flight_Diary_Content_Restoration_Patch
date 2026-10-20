# -*- coding: utf-8 -*-
"""134 个差分区间的形态判定（机械标定 + 4 subagent 语义核验 + 主控独立复核）。
键 = (script, region_idx)；值 = (form, action, h_level, note)
"""

V = {}

def add(script, idx, form, action, h, note):
    V[(script, idx)] = (form, action, h, note)

# ============ H 场景脚本（补丁已还原的一批） ============
add('AFT_003', 0, 'translation_artifact', 'no_action', '普通',
    '伪新增：S#205 是原版 O#204 长句的拆行尾部（O#204 含「手術をして、立って歩けるようになった」）⇒ EN 拆行 ⇒ 不动作')
add('AFT_003', 1, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 把原版 511 格 H 段同节拍审查改写成 38 格吻戏；补丁删光 38 格原位填原版(覆盖1.0)。形态规则：新写保留+被删还原插入')
add('AFT_003', 2, 'rewrite', 'replace_with_orig', '普通',
    'CUTIN_02_06→CUTIN_02_04 特写改放（继承自 Steam），同位换装 VKOT0297 ⇒ 该格取原版那一行（补丁未还原）')

add('AFT_007_3', 0, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 50 格审查改写顶替原版 366 格星空 H；补丁删 49 存 1、插 365（漏 ORIG#75）；EVRET 出口跳转补丁漏还原，实现时须补')

add('BEF_003', 0, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 34 格审查改写顶替原版 307 格教室 H；补丁删 32 存 2、插 305（漏 ORIG#234/#535/#538）')
add('BEF_003', 1, 'translation_artifact', 'no_action', '普通',
    'O#546-550(5)↔S#273-278(6) 两侧无语音锚，EN 拆行覆盖全部日文 ⇒ 翻译伪差异')
add('BEF_003', 2, 'rewrite', 'replace_with_orig', '性暗示',
    'O#552-554(3)↔S#280-282(3) 同位换装 VAMA0013：原版露骨性玩笑被改写成含蓄指代(Doing what, exactly?) ⇒ 该格取原版（补丁未还原）')
add('BEF_003', 3, 'para_delete_new_write', 'keep_steam_insert_orig', '性暗示',
    'O#556-559(4)↔S#284-286(3) 性暗示台词压缩改写、无语音锚 ⇒ 新写保留+被删还原插入（补丁未还原）')

add('BEF_004', 0, 'translation_artifact', 'no_action', '普通',
    'O#215(1)↔S#215-216(2)：长句英译拆两行，EN=日文翻译 ⇒ 伪差异')
add('BEF_004', 1, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 44 格审查改写顶替原版 390 格 H；补丁删 43 存 1、插 387（漏 ORIG#564/#832/#839）；EVRET 补丁漏还原')

add('KAN_3001_3', 0, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 223 格审查改写(膝枕)顶替原版 483 格初次 H；补丁整脚本换回原版(1.0)；EVRET 补丁漏还原')

add('KAN_3001_4', 0, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 把 104 格 H 段扩写成 164 格审查改写(枕臂+早安吻)；补丁整脚本换回原版(1.0)')

add('KAN_3002_2', 0, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 用 KAN_3002_2_E+3002_3_E 新内容顶替；补丁整脚本搬入原版(1.0)。尾跳须改为 KAN_3003_E，否则接播全年龄场景')

add('HOT_002', 0, 'translation_artifact', 'no_action', '普通', 'EN 扩写/拆行覆盖对应日文')
add('HOT_002', 1, 'translation_artifact', 'no_action', '普通', 'EN 拆行覆盖对应日文')
add('HOT_002', 2, 'translation_artifact', 'no_action', '普通', 'EN 拆行覆盖对应日文')
add('HOT_002', 3, 'translation_artifact', 'no_action', '普通', 'EN 扩写覆盖对应日文')
add('HOT_002', 4, 'translation_artifact', 'no_action', '普通', '伪新增：S#674 是原版 O#669 的拆行尾部（O#669「武器は、女の魅力♪」= feminine charms）⇒ EN 拆行 ⇒ 不动作')
add('HOT_002', 5, 'translation_artifact', 'no_action', '普通', '伪新增：S#761 是原版 O#755 长句的拆行尾部（O#755 含「騒いで、盛り上がるのは全然好きじゃない」）⇒ EN 拆行 ⇒ 不动作')
add('HOT_002', 6, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 44 格(VHOT0001A/B、0002-0008 新录音)顶替原版 391 格 H；补丁删 42 存 2、插 404')
add('HOT_002', 7, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 15 格(VHOT0009/0010 新录音，扩写告白场景)顶替原版 14 格；补丁删 15、插 14(1.0)')

# ============ HOT_004 / HUS_001 ============
add('HOT_004', 0, 'rewrite', 'replace_with_orig', '普通',
    '★部训语义反转：原版「最終的には、一人でも飛べるようになること。それがうちの部の目標だ」→ Steam "Nobody flies alone… one of our club\'s most sacred laws"（独自飞翔被译成禁止独自飞行）。官中 slot323-324 已按原版译（最终要做到独立飞行）但 Steam 拆成 2 格 ⇒ 该格取原版那一行')
add('HOT_004', 1, 'translation_artifact', 'no_action', '普通', 'O#329-331(3)↔S#330-333(4) EN 拆行')
add('HOT_004', 2, 'translation_artifact', 'no_action', '普通', 'O#375-377(3)↔S#377-380(4) EN 拆行')
add('HOT_004', 3, 'translation_artifact', 'no_action', '普通', 'O#630(1)↔S#633-634(2) EN 拆行')
add('HOT_004', 4, 'translation_artifact', 'no_action', '普通', 'O#635-640(6)↔S#639-645(7) EN 拆行')
add('HOT_004', 5, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 9 格审查改写顶替原版 14 格；补丁已还原(1.0)')
add('HOT_004', 6, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 8 格顶替原版 21 格；补丁已还原(1.0)')
add('HOT_004', 7, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 5 格顶替原版 34 格；补丁已还原(1.0)')
add('HOT_004', 8, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 20 格顶替原版 243 格主 H 段；补丁已还原(1.0)')
add('HOT_004', 9, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 2 格顶替原版 34 格；补丁已还原(1.0)')
add('HOT_004', 10, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 7 格顶替原版 262 格；补丁已还原(1.0)')
add('HOT_004', 11, 'pure_delete', 'insert_orig_all', 'H',
    'O#1301「柱、立った。大黒柱。わたしの中に、どーんと」Steam 侧无格；补丁已插入该行')

add('HUS_001', 0, 'rewrite', 'replace_with_orig', 'H',
    'O#73-75(3)↔S#73-75(3) 位对齐但内容被改：原版「亜紗ちゃんのお尻の割れ目にそっと差し込む」→ "And placed them softly on her butt"，官中 slot73 也跟着译成「将书轻轻放在了亚纱的臀部」⇒ 该格取原版，中文按原版重译')
add('HUS_001', 1, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#120 后半「こちらに非はないだろう、うん」无落点（S#120 只合行覆盖 O#120 前半+O#121 自爆）⇒ 整区间取原版')
add('HUS_001', 2, 'translation_artifact', 'no_action', '普通', 'O#180-181(2)↔S#179-180(2) 忠实翻译+换装')
add('HUS_001', 3, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#186「まぁでも、これでご飯食べに降りた時には涼しくなる筈だから、一安心だね」(ASA_0425 有配音) 整句无落点，S#185 只对应 O#187 ⇒ 整区间取原版')
add('HUS_001', 4, 'rewrite', 'replace_with_orig', 'H',
    'O#199-208(10)↔S#197-207(11)：Steam 补入 VTAT0000 反应行「~Thanks~」原版无 ⇒ 该格取原版')
add('HUS_001', 5, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 19 格顶替原版 29 格（删 HP 内容，VTAT0003）；补丁 partial')
add('HUS_001', 6, 'rewrite', 'replace_with_orig', 'H',
    'O#241-243(3)↔S#230-232(3)：原版裸女抱挱 → Steam "The girls were in their swimsuits"（泳装化审查）⇒ 该格取原版')
add('HUS_001', 7, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 17 格顶替原版 18 格（删 HP）；补丁 partial')
add('HUS_001', 8, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 56 格顶替原版 62 格（删 HP）；补丁 partial')
add('HUS_001', 9, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'Steam 113 格顶替原版 270 格 H 主段；补丁 partial（漏 7 格）')
add('HUS_001', 10, 'para_delete_new_write', 'keep_steam_insert_orig', 'H', 'Steam 18 格顶替原版 19 格（删 HP）；补丁 partial')
add('HUS_001', 11, 'para_delete_new_write', 'keep_steam_insert_orig', 'H',
    'H 块尾段 O#749-758(10)↔S#573-575(3)：Steam 删到只剩一句，补丁未还原（缺 4 条 HP 语音 + 2 字幕音 + ASA_0425 + 11 处 V*** 未换回）')

# ============ BEF_005 / NOV_001 ============
add('BEF_005', 0, 'translation_artifact', 'no_action', '普通', 'O#120-122(3)↔S#120-123(4) EN 拆行')
add('BEF_005', 1, 'translation_artifact', 'no_action', '普通', 'O#261-263(3)↔S#262-264(3) 忠实翻译+换装 VTAT0001')
add('BEF_005', 2, 'translation_artifact', 'no_action', '普通', '伪新增：S#690 是原版 O#688 长句的拆行尾部（O#688 尾「恋人関係は成立しない」= won\'t be in a relationship）⇒ EN 拆行 ⇒ 不动作')
add('BEF_005', 3, 'rewrite', 'replace_with_orig', '性暗示',
    '胸部调侃段 O#823-825(3)↔S#825-831(7)：Steam 改写扩写(VAMA0028/29、VISU0000/0001 新录音)，把「碧も好きなんだ、おっぱいが」改成 "Ageha and the others were saying…"；官中跟着英译 ⇒ 该格取原版，中文按原版重译')
add('BEF_005', 4, 'rewrite', 'replace_with_orig', '性暗示',
    'O#827-830(4)↔S#833-835(3)：○ッコロ玩笑被改写 + 天音吐槽行(O#830)被删 ⇒ 该块取原版（O#830 需插入）')

for i in range(11):
    add('NOV_001', i, 'translation_artifact', 'no_action', '普通',
        'EN 拆行/扩写覆盖对应日文' if i != 9 else
        'EN 拆行覆盖；另注：此处英译漏掉原版一个助词「と」，属译文质量，不影响中文交付')

# ============ KAN_2001（处女话题阉割，非 H 脚本里最大的一块） ============
add('KAN_2001', 0, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#9「素裸で」在 S#10 中脱落；O#10「抱えた衣類で肌を隠そうとした…丸見え」被换成 S#11 猫爬意象 "back arched like a cat"（原版无此内容）⇒ 整区间取原版')
add('KAN_2001', 1, 'para_delete_new_write', 'keep_steam_insert_orig', '普通',
    'O#13-17(5)↔S#14-25(12)：原版「佳奈子感冒躺床」被 Steam 同位置换成「进房撞见+寒暄」12 格新写；段级对不上+原版录音 KANA_0203-0204 全表无锚点 ⇒ 新写保留+被删还原插入')
add('KAN_2001', 2, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#21「俺も裸になっていることに気づいた」无落点；O#27-34（格好 Critique+性妄想段，含 O#32「たわわな胸が柔らかそうにひしゃげて」）整体被换成 S#35-39 感谢段（fixing a window 等原版无内容）⇒ 整区间取原版')
add('KAN_2001', 3, 'rewrite', 'replace_with_orig', '性暗示',
    'O#51-56(6)↔S#56-61(6)：内裤调侃被软化——原版「そんなにいつも下着だったっけ……？」→ "Have my outfits really been that skimpy lately?"；同位换装 VKAN0014 ⇒ 该格取原版')
add('KAN_2001', 4, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#70「頬が熱く火照ってくる」无落点（S#75 泛化新增 "But this wasn\'t the time for that"）；O#71「あの日のこと」被改为 S#76/77 "this morning"（指涉改变）⇒ 整区间取原版')
add('KAN_2001', 5, 'translation_artifact', 'no_action', '普通', 'O#85(1)↔S#91-92(2) EN 拆行')
add('KAN_2001', 6, 'translation_artifact', 'no_action', '普通', 'O#115(1)↔S#122(1) 换装 VAGE0004，忠实翻译')
add('KAN_2001', 7, 'translation_artifact', 'no_action', '普通', 'O#222(1)↔S#229(1) 换装 VKAN0015，忠实翻译')
add('KAN_2001', 8, 'translation_artifact', 'no_action', '普通', 'O#224-225(2)↔S#231-232(2) 换装 VKAN0016/VYOR0000')
add('KAN_2001', 9, 'para_delete_new_write', 'keep_steam_insert_orig', '性暗示',
    '★处女话题阉割：O#227-237(11)↔S#234-259(26)——原版「自分が処女なのかそうでないのかって、どうやって確かめればいいと思う？」被 Steam 换成 15 格新写回忆戏(VYOR0001-0006 新录音)；段级对不上+原版录音全表无锚点 ⇒ 新写保留+被删还原插入')
add('KAN_2001', 10, 'para_delete_new_write', 'keep_steam_insert_orig', '性暗示',
    'O#239-243(5)↔S#261-266(6)：「碧先輩ですね？」被改成 VYOR0009 反应行；新写保留+被删还原插入')
add('KAN_2001', 11, 'para_delete_new_write', 'keep_steam_insert_orig', '性暗示',
    'O#255-256(2)↔S#278-292(15)：原版「私も考える時間が欲しいんです」被换成 13 格醒来回忆+「再问一个问题」；新写保留+被删还原插入')
add('KAN_2001', 12, 'translation_artifact', 'no_action', '普通',
    'O#293-309(17)↔S#329-346(18) 逐行核对：晚饭后收拾/咖喡/佳奈子没吃完/她的异样/必须找她谈谈，EN 逐行为忠实翻译（仅 1 格拆行）⇒ 伪差异。注：subagent 曾报此处为纯删，经逐行取证不成立')

# ============ KAN_3001_5 / KAN_2002 ============
add('KAN_3001_5', 0, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#16 后半「それにもっとすごいもの、見せてあげたでしょ？」被换成 S#16/17 (VKAN0165/0166 新录音) "laying in the same bed"（性暗示换装替换，无逐词对应）⇒ 整区间取原版')
add('KAN_3001_5', 1, 'rewrite', 'replace_with_orig', '性暗示',
    '澡堂戏逗弄段 O#51-52(2)↔S#53-54(2)：原版露骨(勃起だらけ)被改成 "something else… standing at attention"；同位换装 ⇒ 该格取原版')
add('KAN_3001_5', 2, 'pure_delete', 'insert_orig_all', '性暗示', 'O#67-68(2) Steam 侧无格 ⇒ 还原插入')
add('KAN_3001_5', 3, 'pure_delete', 'insert_orig_all', '性暗示', 'O#83-86(4) Steam 侧无格 ⇒ 还原插入')

add('KAN_2002', 0, 'translation_artifact', 'no_action', '普通', 'O#49-53(5)↔S#49-54(6) EN 扩写覆盖')
add('KAN_2002', 1, 'rewrite', 'replace_with_orig', '普通',
    'O#77 朱莉「用があるのはソアリング部ではなく、水瀬碧くん個人に対してよ」→ Steam "It\'s not a problem in the soaring club, it\'s something personal between Aoi and Kanako"（商谈对象被改成碧×佳奈子）+ 换装 VAKA0018 ⇒ 该格取原版')
add('KAN_2002', 2, 'translation_artifact', 'no_action', '普通', '伪新增：S#97 是原版 O#95 长句的拆行尾部（O#95「口を出す筋合いなんて私にはない」= no right to tell anyone）⇒ EN 拆行 ⇒ 不动作')
add('KAN_2002', 3, 'translation_artifact', 'no_action', '普通', 'O#102(1)↔S#104-105(2) EN 拆行')

# ============ 其余非 H 脚本：全部为翻译拆/合行伪差异 ============
_ART = {
    'KAN_2004': 5, 'KAN_1001': 5, 'KAN_1003': 4, 'KAN_1004': 3,
    'KAN_3001_2': 3,
    'KAN_3004_1': 1, 'KAN_4001': 3, 'KAN_2003': 1, 'AFT_002': 5,
    'AFT_004': 1, 'AFT_005': 3, 'AFT_007_1': 1, 'AFT_008_2': 1, 'BEF_006': 1,
    'HOT_001': 5, 'HOT_003': 2, 'HOT_005': 3, 'AFT_001': 1,
}
for sc, n in _ART.items():
    for i in range(n):
        add(sc, i, 'translation_artifact', 'no_action', '普通',
            'EN 拆行/扩写覆盖对应日文（逐处语义核验：英文格即原版格翻译）')

# KAN_3002_1：idx1 接吻戏被整体审查改写；idx0 有一条带新录音的 Steam 插入行（纯增保留）
add('KAN_3002_1', 0, 'pure_add', 'keep', '普通',
    '复查改判：S#114 (VKAN0180 "Flattered? What\'s there to be flattered about?") 为带新录音的 Steam 插入行，原版 O#113 后直接接 O#114，无此行 ⇒ 纯增保留（产物不变）')
add('KAN_3002_1', 1, 'mixed_censor', 'replace_with_orig', '性暗示',
    '复查改判：KANA_0877-0884 共 8 条原版配音在 Steam 全表消失——O#123-136 接吻戏（耳元で喋らないで/桜色の唇へ吸い付いた/口の中へ舌を滑り込ませていく）被整体换成 VKAN0181-0190 的嗅闻/克制戏（"dial it back"/"nuzzled into the nape"/"we can go crazy later"）；O#117-120 为忠实翻译 ⇒ 整区间取原版')

# ============ 拆行漏挂复查改判（2026-10-18，逐条亲核） ============
# 形态 mixed_censor：区间内 Steam 格部分是原版翻译、部分是审查替换/删减（对应原版行无落点）
# ⇒ 整区间取原版。此前 10-13 语义核验把这些区间一律判成 translation_artifact/no_action，
# 漏挂了其中的审查替换/删减（原版内容至今未还原）。
add('BEF_006', 0, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：S#140 将 O#140「例えば、エロサイトで勉強するよう勧めてたりとか」+O#141 整段换成泛论 "It was hard to think that Amane\'s views on love were anything that applied to other people."（エロサイト 在英文中无落点）；S#138/139/141 为忠实翻译但随区间一并回源 ⇒ 整区间取原版')
add('KAN_1001', 1, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：S#12/13 把 O#10「さすがに下着一枚では少し肌寒かった」火宰成 "my usual pajamas"/"just one layer"；S#15 把 O#12「ずり落ちたシーツを掴もうとして」换成 "tuck my hands under my armpits"（床单动作无落点）⇒ 整区间取原版')
add('KAN_1001', 4, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#39「ショーツ以外何も身につけていなかった」+O#40「トランクス一丁」在 Steam 无落点——S#44 合并译 O#38+40 并删去内衣细节，S#45 为新增推测句 ⇒ 整区间取原版')
add('KAN_1004', 0, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#3「後ろを見れば窓があり、青々とした裏庭が見渡せる」整句无落点（EN 无 window/backyard/garden），S#3 实为 O#4 的翻译 ⇒ 整区间取原版')
add('KAN_1004', 1, 'mixed_censor', 'replace_with_orig', '性暗示',
    '复查改判（系统性审查改写）：O#9「あたしが裸なのは…寝る時の癖で服を脱いじゃったからだろうけど」被换成 S#8/9 "dragged me into bed"；O#10「どうして碧くんまで裸になってるんだろ？」无落点；O#16「唯一身につけていたパンツの中もチェックする」→ S#13 "a few wrinkles"；O#20「彼の手は…あたしの下着を握って離さなかった」→ S#18 "instinctively jerked back"；O#21「現実味を帯びていく」被反转为 S#20 "nothing \'untoward\' had happened" ⇒ 整区间取原版')
add('KAN_1004', 2, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#28「お互い一糸まとわぬ格好で一晩過ごして」的裸体细节在 S#29-31 中被删；O#31「もしかしてあたしたち、ヤっちゃった？」被软化为 S#32 "I don\'t want to think about it... But I have to know..." ⇒ 整区间取原版')
add('KAN_2004', 3, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：S#416 与 S#384 逐字同文（英化脚本串行误插，其内容属 O#383）；O#414 后半「これは前回の噂とまったく同じパターンだ」无落点；其余 15 格为忠实翻译 ⇒ 整区间取原版（剔除串行行）')
add('KAN_3001_2', 2, 'mixed_censor', 'replace_with_orig', '性暗示',
    '复查改判：O#87「わ、分かってるクセに」(KANA_0562)、O#90「さ、もう観音しなさい」(KANA_0563) 被换成 VKAN0032/0033 新录音挑逗段；O#92「俺は頷いてしまっていた」无落点；S#95-98 为原版没有的追加 ⇒ 整区间取原版')
add('KAN_3004_2', 0, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#106『碧』「そんなにですか？」整句删除（S#105 后直接进叙述行）；S#106-109 不是 O#106-108 的翻译，而是原版后半 O#120-124 蒙布朗品尝段的前移 ⇒ 与 idx1 联动，整区间取原版')
add('KAN_3004_2', 1, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#119「そっちのモンブランは？」(KANA_1192 有配音) 在 Steam 无落点，该语音锚点整个缺失；O#120-124 的英译落在 idx0 的 S#106-109 ⇒ 两区间同改 replace_with_orig 后文本时序即原版')
add('KAN_4001', 0, 'pure_add', 'keep', '普通',
    '复查改判：S#58 "I reached out my hand, as if I could pluck the glider right out of the sky" 为 Steam 独立新增叙述（ORIG 全文 69 行无对应），O#57→S#57、O#58→S#59 后半均已各自译出 ⇒ 纯增保留（产物不变）')
add('KAN_4001', 1, 'pure_add', 'keep', '普通',
    '复查改判：S#67-69（patted Hatty\'s head→whip up some food→picture their faces）为 Steam 纯增做饭段，原版侧无格，前后锚点 O#66「でも、今は」→S#70 正常 ⇒ 纯增保留（产物不变，idx2 维持 no_action 无联动问题）')
add('HOT_003', 0, 'mixed_censor', 'replace_with_orig', '性暗示',
    '复查改判：S#218 将 O#218「ほたるの、服の下の……体……素肌……」换成 "nestling in my arms"；O#219 后半「胸、大きかったよな」无落点；O#221 后半「触っても、入りこんでも」与 O#222「入っても……入る……」整句删除（S#219 只覆盖 やわらかかった+熱かった）⇒ 整区间取原版')
add('HOT_005', 0, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#109「あおにぃの時だけ、そうしてたみたい。他の人の時は普段通り」(HOTARU_0943 有配音) 与 O#110「あのやろ……」在 Steam 无落点（S#108/109 只对应 O#108/111）⇒ 整区间取原版')
add('AFT_005', 1, 'mixed_censor', 'replace_with_orig', '普通',
    '复查改判：O#493「俺はその話を知らない事になっているので、なんとも答えようがない」整句无落点（S#492/493 对应 O#491/492），非敏感内容纯漏译 ⇒ 整区间取原版')
