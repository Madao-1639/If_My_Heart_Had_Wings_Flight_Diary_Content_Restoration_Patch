# -*- coding: utf-8 -*-
"""L5 中文覆盖层：按 `resource/slot_sources.json` 重建 `asset/zh-CN/Rio.arc` 的 `.lng`。

原理
----
本作中文只走**宽字符通路**：`zh-CN/Rio.arc` 内的逐脚本 `.lng`（`u32 count` + `u16[count]`
长度表 + UTF-16LE 逐字节 XOR 体，密钥 `0x3E`）+ `NameTable.txt`。`.lng` 与脚本**按槽位
位置对应**（`lng[i]` ↔ 第 i 条 `0x14`）⇒ 正文一增删就必须**整体重建**宿主 `.lng`。

槽位来源（`resource/slot_sources.json`）
----------------------------------------
* `['steam', 旧槽号]` —— 保留的 Steam 格 ⇒ 直取官方 `zh-CN/Rio.arc` 同名 `.lng` 的该条；
* `['orig', 原版行号]` —— 还原插入的原版格 ⇒ 取本项目语料 `resource/corpus/cn/<脚本>.jsonl`。

闸（任一不过即退出 1）
----------------------
官方 `.lng` 条数 == Steam 脚本 `0x14` 条数；产物 `.lng` 条数 == 槽表长度；逐条非空；
无假名残留（内容面闸，见 AGENTS「闸门要能验内容」）。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GALREV = os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')
for p in (ROOT, GALREV):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, lng, paths, ws2, ws2dis  # noqa: E402

# 假名 = 平假名（U+3041–U+309F）+ 片假名字母（U+30A1–U+30FA）。
# **不含**片假名标点块 U+30FB–U+30FF（`・` 中点 / `ー` 长音符 / `♪` 邻域）——
# 本作原版正文用 `・` 做逐字强调（`お・ち・○・ち・ん`），中文照抄该写法是**刻意**的。
KANA = re.compile(r'[\u3041-\u309f\u30a1-\u30fa]')


def load_corpus(script):
    p = os.path.join(ROOT, 'resource', 'corpus', 'cn', script + '.jsonl')
    if not os.path.exists(p):
        raise SystemExit('缺语料 %s' % p)
    out = {}
    for line in open(p, encoding='utf-8'):
        if line.strip():
            r = json.loads(line)
            out[r['orig_row']] = r['cn']
    return out


def main():
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    _choice_path = os.path.join(ROOT, 'resource', 'corpus', 'choice_cn.json')
    choice_cn = (json.load(open(_choice_path, encoding='utf-8')).get('scripts') or {}
                 if os.path.exists(_choice_path) else {})
    zh_members = arcbuild.read_raw(os.path.join(paths.STEAM, 'zh-CN', 'Rio.arc'))
    by_name = {nb.decode('utf-16le'): i for i, (nb, _) in enumerate(zh_members)}
    # NameTable.txt 存放位置随发行包而异：官方范式在 `zh-CN/Rio.arc`，本作 Flight
    # Diary 的官方简中把它放在**基础** `Rio.arc`（zh-CN 只有 .lng）。按「语言包
    # 优先、基础档兜底」取，不能写死一侧。
    nametable, nt_path = lng.load_nametable(paths.STEAM)
    nt_keys = set(re.findall(r'%LC([^\t\r\n]+)\t', nametable))

    steam_rio = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(os.path.join(paths.STEAM, 'Rio.arc'))}
    report, missing_keys = [], set()
    for sc, info in sorted(slots_all.items()):
        # 官方 lng 名 = 宿主成员名换扩展名（whole 脚本无宿主 ⇒ 新建）
        if info['kind'] == 'host':
            lng_name = info['steam_file'][:-4] + '.lng'
            ws_name = info['steam_file']
        else:
            lng_name = sc + '.lng'
            ws_name = None
        official = None
        if lng_name in by_name:
            official = lng.parse_lng(zh_members[by_name[lng_name]][1], lng.KEY_FD)
            if ws_name:
                n14 = sum(1 for _, op, _, _ in ws2dis.disassemble(ws2.decode(steam_rio[ws_name]))[0]
                          if op == 0x14)
                assert len(official) == n14, \
                    '%s 官方 lng %d 条 != Steam 0x14 %d 条' % (lng_name, len(official), n14)
        elif info['kind'] == 'host':
            raise SystemExit('官方 zh-CN 缺 %s' % lng_name)

        corpus = load_corpus(sc)
        texts, n_official, n_corpus, n_choice = [], 0, 0, 0
        for src, idx in info['slots']:
            if src == 'choice':
                row = (choice_cn.get(sc) or {}).get(str(idx))
                if not row or not (row.get('cn') or '').strip():
                    raise SystemExit('%s 选项槽 strid %s 缺中文（resource/corpus/choice_cn.json）'
                                     % (sc, idx))
                texts.append(row['cn'])
                n_choice += 1
            elif src == 'steam':
                if official is None:
                    raise SystemExit('%s 槽 %r 需官方 lng，但缺失' % (sc, (src, idx)))
                texts.append(official[idx])
                n_official += 1
            else:
                if idx not in corpus:
                    raise SystemExit('%s 原版行 %d 不在语料' % (sc, idx))
                texts.append(corpus[idx])
                n_corpus += 1
        blob = lng.encode_lng(texts, lng.KEY_FD)
        back = lng.parse_lng(blob, lng.KEY_FD)
        assert back == texts, '%s lng 往返不一致' % sc
        assert len(texts) == len(info['slots']), '%s lng 条数 %d != 槽数 %d' % (sc, len(texts), len(info['slots']))
        # 严格等式（GalRev/CC 口径）：lng 条数 == 0x14 条数 + Σ(0f count)
        if info['kind'] == 'host':
            _pins, _ = ws2dis.disassemble(ws2.decode(
                {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(
                    os.path.join(ROOT, 'asset', 'Rio.arc'))}[info['steam_file']]))
            _p14 = sum(1 for _a, _op, _s, _x in _pins if _op == 0x14)
            _pch = sum(len(ws2.choice_entries(ws2.decode(
                {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(
                    os.path.join(ROOT, 'asset', 'Rio.arc'))}[info['steam_file']]), _off))
                for _off, _op, _s, _x in _pins if _op == 0x0F)
            assert len(texts) == _p14 + _pch,                 '%s lng %d 条 != 产物文本槽位 %d（0x14 %d + 选项 %d）' % (
                    sc, len(texts), _p14 + _pch, _p14, _pch)
        empty = [i for i, t in enumerate(texts) if not t.strip()]
        kana = [i for i, t in enumerate(texts) if KANA.search(t)]
        assert not empty, '%s lng 有 %d 条空条目（首 %s）' % (sc, len(empty), empty[:5])
        assert not kana, '%s lng 有 %d 条假名残留（首 %s）' % (sc, len(kana), kana[:5])
        for t in texts:
            missing_keys |= {m for m in re.findall(r'%LC([^\t\r\n]+)', t) if m not in nt_keys}
        if lng_name in by_name:
            zh_members[by_name[lng_name]] = (zh_members[by_name[lng_name]][0], blob)
        else:
            zh_members.append((lng_name.encode('utf-16le'), blob))
            by_name[lng_name] = len(zh_members) - 1
        report.append('| %s | %s | %d 条（官方 %d + 语料 %d + 选项 %d） | %d B |'
                      % (sc, lng_name, len(texts), n_official, n_corpus, n_choice, len(blob)))

    out = os.path.join(ROOT, 'asset', 'zh-CN', 'Rio.arc')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    arcbuild.write_arc(zh_members, out)
    cnt, size, _end = arcbuild.verify(out, expect_count=len(zh_members))
    print('写出 %s：成员 %d、%d B' % (out, cnt, size))
    print('\n'.join(report))
    if missing_keys:
        raise SystemExit('产物引用了 %s 里没有的键 %s —— 需补 NameTable' % (nt_path, sorted(missing_keys)))
    print('NameTable 键覆盖（%s）：产物引用的 %%LC 键全部命中 ✅' % nt_path)


if __name__ == '__main__':
    main()
