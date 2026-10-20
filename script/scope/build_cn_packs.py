# -*- coding: utf-8 -*-
"""生成中文审校 pack（分块 JSONL）供 subagent 逐行归一/补译/清洗/统一/审校。"""
import json
import os
import glob

FD = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
      'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch')
SRC = os.path.join(FD, 'resource', 'corpus', 'cn_draft')
OUT = os.path.join(FD, 'tmp', 'scope', 'cnpacks')
CAP = 400

# 窄字节编码过程产生的替换字（原为日文假名/助词或少数汉字）→ 按 JP 上下文重译
GARBLE_DOC = """\
堯(=あ/な/则撒娇音，如「可愛堯」←「可愛いな」，「哈堯」←「はぅ」) → 啊
鶺(=ん) → 嗯
瑤(=她/は/の，如「瑤的脸」←「顔が」、「小鳥瑤遙」←「小鳥はというと」) → 她/呀
鞁(=舐め/ぺろ) → 舔
槇(=も/嘛/もぐ，句末语气或咀嚼声) → 嘛/咀嚼声
鼕(=だ/よ/咚) → 啊/咚
鵐(=ケン，「鵐架」←「ケンカ」) → 吵
鶫(=こら) → 喂/等
狢(=ほら) → 瞧
黐(=老黐龜 之类的詈词助词) → 按上下文
其他不在规范简体里的字（如 覚/辺/髪/変/軽/満/両/処/蛍/説/対/這/麼/樣/頭/臉/讓/開/們/話…）→ 一律转规范简体；一繁对多简（发/乾/幹/只/歷/復/彙/麵…）按上下文判断
"""

NAME_DOC = """\
官方 NameTable（简体，必须统一用这套）：
Ageha=扬羽 Asa=亚纱 Kotori=小鸟 Aoi=碧 Yoru=依瑠 Harumi=晴海 Haruka=遥 Isuka=伊斯卡
Masatsugu=柾次 Tatsuya=达也 Ryoko=亮子 Hibari=云雀 Amane=天音 Kanako=佳奈子 Hotaru=萤
Akari=朱莉 Hatty=哈特 Teacher=老师 Chairman=理事长 Mayor=市长 Interviewer=采访人员
Kotori's Scream=小鸟的悲鳴（简体：小鸟的悲鸣） Someone's Voice=其他人的声音
（Gemini 译文里出现的 蛍/凜 都指 Hotaru=萤；「碧前輩」=「碧前辈」可用）
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    n = 0
    for f in sorted(glob.glob(os.path.join(SRC, '*.jsonl'))):
        sc = os.path.basename(f)[:-6]
        rows = [json.loads(l) for l in open(f, encoding='utf-8')]
        rows.sort(key=lambda r: r['orig_row'])
        for i in range(0, len(rows), CAP):
            chunk = rows[i:i + CAP]
            n += 1
            path = os.path.join(OUT, 'c%02d_%s_%d-%d.jsonl' % (n, sc, chunk[0]['orig_row'], chunk[-1]['orig_row']))
            with open(path, 'w', encoding='utf-8') as fh:
                for r in chunk:
                    fh.write(json.dumps({
                        'i': r['orig_row'], 'sp': r['speaker'], 'v': r['voice'],
                        'h': r['h_level'], 'jp': r['jp'], 'cn': r['cn_gemini'],
                    }, ensure_ascii=False) + '\n')
            manifest.append({'chunk': os.path.basename(path), 'script': sc,
                             'rows': len(chunk), 'has_cn': sum(1 for r in chunk if r['cn_lang'] == 'CN')})
    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print('共 %d 块；总行 %d' % (len(manifest), sum(m['rows'] for m in manifest)))
    for m in manifest:
        print('  %-34s %3d 行（已有中文 %3d）' % (m['chunk'], m['rows'], m['has_cn']))


if __name__ == '__main__':
    main()
