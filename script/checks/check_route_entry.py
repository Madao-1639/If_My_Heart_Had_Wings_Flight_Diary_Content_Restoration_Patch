# -*- coding: utf-8 -*-
"""L6 路线入口验收闸：核对 `asset/` 里的按钮表改动与 PNA 图层改动。

用法：`python script/checks/check_route_entry.py`（在 `build_route_entry.py` 之后跑）。

断言：
  1. `asset/Script.arc` 的 `LegacyGame.lua` `StoryMenuInit`：表长 8、内容
     [108,101,103,104,105,106,107,102]、FOR 上界 8；
  2. i=8 按 `x=(i-1)*2+6, y=(i-1)*2+5` 算出的 sublayer 恰为 19(on)/20(def)；
  3. `asset/zh-CN/SysGraphic.arc` 的 `SYS_C_Story.pna`：记录 19/20 为真实图层、
     u0=0、带完整 PNG、box 与规格一致；**其余 43 层与 backup 逐字节相同**、记录数/画布不变；
  4. `mainmenu.ws2` 的 `var[98]==102 -> AGS_001` 分派未被动过（base 与 asset 一致）；
  5. 朱莉线（`Rio1.arc`/`Chip10.arc`/`AKA_*`）不在 `asset/` 内。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import lua53, ws2  # noqa: E402

sys.path.insert(0, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev'))
from galrev.advhd import arc, pna  # noqa: E402

OP_MOVE = 0
OP_LOADK = 1
OP_NEWTABLE = 11
OP_SELF = 12
OP_JMP = 30
OP_EQ = 31
OP_CALL = 36
OP_FORPREP = 40
OP_FORLOOP = 39
OP_SETLIST = 43
RK_K = 256
SBX_BIAS = ((1 << 18) - 1) >> 1


def _fld(w):
    return {'op': w & 0x3F, 'A': (w >> 6) & 0xFF, 'B': (w >> 23) & 0x1FF,
            'C': (w >> 14) & 0x1FF, 'Bx': (w >> 14) & 0x3FFFF,
            'sBx': ((w >> 14) & 0x3FFFF) - SBX_BIAS}


def member(members, name):
    for n, d in members:
        if n.decode('utf-16le') == name:
            return d
    raise KeyError(name)


def check_lua(spec):
    sm = spec['story_menu']
    mem = arc.read_raw(os.path.join(ROOT, 'asset', sm['archive']))
    top = lua53.load(member(mem, sm['lua_member']))
    proto = lua53.find(top, sm['proto_path'])
    code = proto.code
    nt = next(i for i, w in enumerate(code)
              if _fld(w)['op'] == OP_NEWTABLE and _fld(w)['B'] == sm['for_bound'])
    vals = [proto.constants[_fld(code[nt + k])['Bx']][1] for k in range(1, sm['for_bound'] + 1)]
    want = [108, 101, 103, 104, 105, 106, 107, sm['table_append']]
    assert vals == want, '按钮表内容不符：%r != %r' % (vals, want)
    assert _fld(code[nt + sm['for_bound'] + 1])['op'] == OP_SETLIST, 'SETLIST 位置不符'
    assert _fld(code[nt + sm['for_bound'] + 1])['B'] == sm['for_bound'], 'SETLIST 覆盖数不符'
    # sublayer 公式：i=8 -> on=2i+3=19, def=2i+4=20（须与规格一致）
    i = sm['for_bound']
    assert (i - 1) * 2 + 6 == sm['button_record_indices']['def'], 'def sublayer 公式不符'
    assert (i - 1) * 2 + 5 == sm['button_record_indices']['on'], 'on sublayer 公式不符'
    # 逐按钮的数值 FOR 循环上界（表构造循环 + 其它逐按钮循环）全须为 for_bound
    old = sm['for_bound'] - 1
    bounds = {}
    for path in [sm['proto_path']] + [list(p) for p in sm.get('additional_for_loop_protos', [])]:
        p = lua53.find(top, path)
        hits = []
        for k, w in enumerate(p.code):
            if _fld(w)['op'] != OP_FORPREP:
                continue
            lim = k - 2
            f = _fld(p.code[lim])
            if f['op'] == 1 and p.constants[f['Bx']][1] == old:
                hits.append(lim)
        assert not hits, 'proto %s 仍有上界 %d 的逐按钮循环' % (path, old)
        got = []
        for k, w in enumerate(p.code):
            if _fld(w)['op'] != OP_FORPREP:
                continue
            lim = k - 2
            f = _fld(p.code[lim])
            if f['op'] == 1 and _fld(p.code[k])['A'] + 1 == f['A']:
                got.append(p.constants[f['Bx']][1])
        bounds[tuple(path)] = got
    # 表构造 proto 与动画 proto 各自恰有一条上界 = for_bound 的循环
    for path in [tuple(sm['proto_path'])] + [tuple(p) for p in sm.get('additional_for_loop_protos', [])]:
        assert bounds[path].count(sm['for_bound']) == 1, \
            'proto %s 的上界 = %d 循环数不为 1：%r' % (path, sm['for_bound'], bounds[path])
    print('[OK] Lua：表长 %d（末位 id %d）、SETLIST 覆盖 %d、逐按钮 FOR 上界 %d（%s）'
          % (sm['for_bound'], vals[-1], sm['for_bound'], sm['for_bound'],
             ' + '.join('/'.join(map(str, p)) for p in
                        [sm['proto_path']] + [list(x) for x in sm.get('additional_for_loop_protos', [])])))


def _check_pna_diff(now, base, expect):
    """`expect` = {记录下标: (box, 期望 PNG 或 None)}；其余记录必须与 backup 逐字节相同。"""
    assert now.count == base.count and (now.width, now.height) == (base.width, base.height)
    for idx in range(base.count):
        a, b = base.layers[idx], now.layers[idx]
        if idx in expect:
            box, want = expect[idx]
            assert b.u0 == 0 and b.data is not None, '记录 %d 未落成真实图层' % idx
            assert (b.x, b.y) == box, '记录 %d 的 box %r != %r' % (idx, (b.x, b.y), box)
            assert (b.width, b.height) == pna.png_dimensions(b.data), '记录 %d 的 box 尺寸与 PNG 不符' % idx
            assert b.layer_id == now.count - 1 - idx, '记录 %d 的 layer_id 位置量不符' % idx
            assert b.marker_hi == 0x3FF00000, '记录 %d 的不透明度不是 1.0' % idx
            if want is not None:
                assert b.data == want, '记录 %d 的 PNG 与期望来源不逐字节一致' % idx
        else:
            assert (a.u0, a.layer_id, a.x, a.y, a.width, a.height, a.marker_lo, a.marker_hi,
                    a.data) == (b.u0, b.layer_id, b.x, b.y, b.width, b.height, b.marker_lo,
                                b.marker_hi, b.data), '记录 %d 被动过' % idx


def _res(name):
    with open(os.path.join(ROOT, 'resource', name.replace('/', os.sep)), 'rb') as fh:
        return fh.read()


def _cast_expect(spec):
    ch = spec.get('cast_highlight')
    if not ch:
        return None, None
    return ch, _res(ch['resource_file'])


def check_pna(spec):
    sm = spec['story_menu']
    base = pna.parse(member(arc.read_raw(os.path.join(ROOT, 'backup', sm['button_pna_archive'])),
                            sm['button_pna_member']))
    now = pna.parse(member(arc.read_raw(os.path.join(ROOT, 'asset', sm['button_pna_archive'])),
                           sm['button_pna_member']))
    bg = spec['button_graphic']
    expect = {sm['button_record_indices']['on']: (tuple(sm['button_boxes']['on']), _res(bg['resource_files']['on'])),
              sm['button_record_indices']['def']: (tuple(sm['button_boxes']['def']), _res(bg['resource_files']['def']))}
    ch, cast_png = _cast_expect(spec)
    if ch:
        expect[ch['record']] = (tuple(ch['box']), cast_png)
    _check_pna_diff(now, base, expect)
    msg = '[OK] PNA（中文）：记录 %d/%d = resource 里的中文按钮，记录 %d = 原版 Cast 高亮图（均逐字节保真），其余 %d 层与 backup 相同'         % (sm['button_record_indices']['on'], sm['button_record_indices']['def'],
           ch['record'] if ch else -1, base.count - len(expect))
    print(msg)


def check_base_pna(spec):
    """base（英/默认）UI：记录 19/20 = 原版日文入口，记录 N = 原版 Cast 高亮图。"""
    bu = spec.get('base_ui_entry')
    if not bu:
        print('[--] base PNA：规格未启用，跳过')
        return
    base = pna.parse(member(arc.read_raw(os.path.join(ROOT, 'backup', bu['archive'])), bu['pna_member']))
    now = pna.parse(member(arc.read_raw(os.path.join(ROOT, 'asset', bu['archive'])), bu['pna_member']))
    rec = bu['button_record_indices']
    expect = {rec['on']: (tuple(bu['button_boxes']['on']), _res(bu['resource_files']['on'])),
              rec['def']: (tuple(bu['button_boxes']['def']), _res(bu['resource_files']['def']))}
    ch, cast_png = _cast_expect(spec)
    if ch:
        expect[ch['record']] = (tuple(ch['box']), cast_png)
    _check_pna_diff(now, base, expect)
    print('[OK] base PNA：记录 %d/%d = 原版日文入口「%s」，记录 %d = 原版 Cast 高亮图；其余 %d 层与 backup 相同'
          % (rec['on'], rec['def'], bu['source']['label'],
             ch['record'] if ch else -1, base.count - len(expect)))


def check_cast_lua(spec):
    """角色高亮：StorySelCursor 的 id==102 分支 + 两个 hide 循环上界 29。"""
    ch = spec.get('cast_highlight')
    if not ch:
        print('[--] Cast 高亮：规格未启用，跳过')
        return
    lua = ch['lua']
    mem = arc.read_raw(os.path.join(ROOT, 'asset', spec['story_menu']['archive']))
    top = lua53.load(member(mem, spec['story_menu']['lua_member']))

    def k_of(proto, value):
        for i, (t, v) in enumerate(proto.constants):
            if v == value:
                return i
        raise AssertionError('常量 %r 不在池内' % (value,))

    old_up, new_up = lua['hide_loop_old_upper'], lua['hide_loop_new_upper']
    for path in lua['hide_loop_protos'] + lua.get('init_loop_protos', []):
        pr = lua53.find(top, path)
        ups = []
        for i, w in enumerate(pr.code):
            if _fld(w)['op'] != OP_FORPREP:
                continue
            f = _fld(pr.code[i - 2])
            if f['op'] == OP_LOADK:
                ups.append(pr.constants[f['Bx']][1])
        assert new_up in ups, '%s 里没有上界 %d 的循环：%r' % (path, new_up, ups)
        assert old_up not in ups, '%s 里仍有上界 %d 的循环：%r' % (path, old_up, ups)

    # 被「显示」的子层必须都在某个 initSubLayer 的覆盖范围内（漏 init 时
    # setSubLayerVisible 静默无效 ⇒ 实机表现为「所有角色消失、只剩背景」）
    init_proto = lua53.find(top, (lua.get('init_loop_protos') or [lua['proto_path']])[0])
    covered = _initsublayer_covered(init_proto)
    need = set(range(old_up + 1, new_up + 1)) | set(range(lua['hide_sprites_range'][0],
                                                        lua['hide_sprites_range'][1] + 1))
    lack = sorted(x for x in need if x not in covered)
    assert not lack, '这些子层会被 setSubLayerVisible 引用但没有 initSubLayer：%r（已覆盖 %r）' % (
        lack, sorted(covered))

    pr = lua53.find(top, lua['proto_path'])
    code = pr.code
    k_id = k_of(pr, lua['special_id'])
    k_cast = k_of(pr, new_up)
    k_vis = k_of(pr, b'setSubLayerVisible')
    hits = [i for i, w in enumerate(code)
            if _fld(w)['op'] == OP_EQ and _fld(w)['C'] == RK_K + k_id]
    assert len(hits) == 1, 'StorySelCursor 里 id==%d 的比较应恰有 1 处，实得 %r' % (lua['special_id'], hits)
    i = hits[0]
    assert _fld(code[i + 1])['op'] == OP_JMP, 'id==102 后应紧跟 JMP'
    assert _fld(code[i + 2])['op'] == OP_SELF and _fld(code[i + 2])['C'] == RK_K + k_vis
    assert _fld(code[i + 7])['op'] == OP_CALL
    assert pr.constants[_fld(code[i + 5])['Bx']][1] == new_up, '分支里显示的 sublayer 不是 %d' % new_up
    assert _fld(code[i + 8])['op'] == OP_JMP
    # 不相等时要落到「hide 之后、原 101..107 分支之前」那条指令（即块尾）
    t_else = i + 1 + 1 + _fld(code[i + 1])['sBx']
    assert t_else == i + 9, 'id!=102 的跳转目标 %d 应为块尾 %d' % (t_else, i + 9)
    # 相等时块尾必须跳到 hide-31..39 **循环序列的第一条 LOADK**（init），
    # 不能跳 FORPREP —— FORPREP 依赖 R(A..A+2) 已由前三条 LOADK 填好。
    t_sprites = i + 8 + 1 + _fld(code[i + 8])['sBx']
    assert _fld(code[t_sprites])['op'] == OP_LOADK, '块尾应跳到 hide-31..39 的三条 LOADK 之首'
    assert _fld(code[t_sprites + 1])['op'] == OP_LOADK and _fld(code[t_sprites + 2])['op'] == OP_LOADK
    fp = t_sprites + 3
    assert _fld(code[fp])['op'] == OP_FORPREP, '三条 LOADK 之后应是 FORPREP'
    assert _fld(code[t_sprites])['A'] == _fld(code[fp])['A'], 'init 寄存器与 FORPREP 的 A 不一致'
    sp_up = pr.constants[_fld(code[fp - 2])['Bx']][1]
    assert sp_up == lua['hide_sprites_range'][1], '块尾跳到的循环上界 %r 不是 %d' % (sp_up, lua['hide_sprites_range'][1])
    print('[OK] Cast 高亮 Lua：id==%d -> sublayer %d；hide/init 循环上界 %d（%s）；块尾跳 hide %d..%d 的 init LOADK（不是 FORPREP）'
          % (lua['special_id'], new_up, new_up,
             ' + '.join('/'.join(map(str, p)) for p in
                        lua['hide_loop_protos'] + lua.get('init_loop_protos', [])),
             lua['hide_sprites_range'][0], lua['hide_sprites_range'][1]))
    print('[OK] Cast 高亮 init：initSubLayer 覆盖 %r（含新层 %d）' % (sorted(covered), new_up))


def _initsublayer_covered(proto):
    """静态分析 `initSubLayer` 实际覆盖到的子层号集合。

    本作两种形态都认：
      - 参数是常量：`LOADK R(A+4) := K(n)`；
      - 参数是循环变量：`MOVE R(A+4) := R(var)`，前面对应 `FOR var` 循环的 init/limit 常量。
    `SELF A := R(B)[initSubLayer]` 里方法在 R(A)，`CALL A` 的第 4 个实参是 R(A+4)。
    """
    k_init = next(i for i, (t, v) in enumerate(proto.constants) if v == b'initSubLayer')

    def loop_range(var_reg, before_pc):
        """在 `before_pc` 之前**由近及远**找 loop var == var_reg 的数值 FOR（寄存器会被复用，
        不能取全函数第一个匹配 —— 22..28 与 31..39 两处循环都用了 R7 作循环变量）。"""
        for i in range(before_pc - 1, -1, -1):
            if _fld(proto.code[i])['op'] != OP_FORPREP:
                continue
            f = _fld(proto.code[i])
            if f['A'] + 3 != var_reg:
                continue
            lo = _fld(proto.code[i - 3])
            hi = _fld(proto.code[i - 2])
            if lo['op'] == OP_LOADK and hi['op'] == OP_LOADK:
                return (proto.constants[lo['Bx']][1], proto.constants[hi['Bx']][1])
        return None

    covered = set()
    for i, w in enumerate(proto.code):
        f = _fld(w)
        if f['op'] != OP_SELF or f['C'] != RK_K + k_init:
            continue
        dest = f['A'] + 4
        call = next(j for j in range(i + 1, min(i + 10, len(proto.code)))
                    if _fld(proto.code[j])['op'] == OP_CALL and _fld(proto.code[j])['A'] == f['A'])
        src = None
        for j in range(call - 1, i, -1):
            g = _fld(proto.code[j])
            if g['op'] == OP_LOADK and g['A'] == dest:
                covered.add(proto.constants[g['Bx']][1])
                src = 'const'
                break
            if g['op'] == OP_MOVE and g['A'] == dest:
                r = loop_range(g['B'], i)
                assert r is not None, 'MOVE 来源 R%d 不是数值 FOR 的循环变量' % g['B']
                covered.update(range(r[0], r[1] + 1))
                src = 'loop'
                break
        assert src, 'initSubLayer 的第 3 实参 R%d 不是「常量」也不是「循环变量」形态' % dest
    return covered


def check_mainmenu(spec):
    """分派表不该被本步骤触碰：asset 若含 Script.arc 之外的同名脚本归档则另核。"""
    sm = spec['story_menu']
    base = arc.read_raw(os.path.join(ROOT, 'backup', 'Rio.arc'))
    mainmenu = member(base, 'mainmenu.ws2')
    # var[98]==102 分支：反混淆后脚本内出现 NextFile "AGS_001"
    assert b'AGS_001' in ws2.decode(mainmenu), 'mainmenu.ws2 里找不到 AGS_001 跳转'
    asset_rio = os.path.join(ROOT, 'asset', 'Rio.arc')
    if os.path.exists(asset_rio):
        m2 = member(arc.read_raw(asset_rio), 'mainmenu.ws2')
        assert m2 == mainmenu, 'mainmenu.ws2 被改动了（本步骤不应触碰）'
    print('[OK] mainmenu.ws2：var[98]==102 -> AGS_001 分支仍在（本步骤未改分派表）')


def check_julie(spec):
    guard = json.load(open(os.path.join(ROOT, 'resource', 'julie_guard.json'), encoding='utf-8'))
    bad = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, 'asset')):
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, 'asset')).replace('\\', '/').lower()
            if rel in [x.lower() for x in guard['archives']] or \
               any(rel.startswith(x.lower()) for x in guard['archive_prefixes']):
                bad.append(rel)
    assert not bad, 'asset/ 含朱莉线文件：%r' % bad
    print('[OK] 朱莉线保护：asset/ 未含 Rio1.arc / Chip10.arc / zh-CN/Rio1.arc')


def main():
    spec = json.load(open(os.path.join(ROOT, 'resource', 'route_entry.json'), encoding='utf-8'))
    check_lua(spec)
    check_pna(spec)
    check_base_pna(spec)
    check_cast_lua(spec)
    check_mainmenu(spec)
    check_julie(spec)
    print('路线入口验收通过。')


if __name__ == '__main__':
    main()
