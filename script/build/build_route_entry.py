# -*- coding: utf-8 -*-
"""L6 路线入口还原写盘：补回姬城あげは线（`AGS_001`）的**入口按钮**。

产物（`asset/`，相对 `backup/` 有差异的文件）：
  - `asset/Script.arc`            —— `LegacyGame.lua` 的 `StoryMenuInit` 按钮表 7 -> 8（插回 102）
  - `asset/zh-CN/SysGraphic.arc`  —— `SYS_C_Story.pna` 的 `StoryBace` 第 8 个按钮图层（on/def）

规格来源：`resource/route_entry.json`。
按钮图形由 `tool/agsbutton.py` 从官中既有按钮**逐字拼字**生成（字体/描边/旋转/字距天然一致）。
Lua 字节码读写出 `tool/lua53.py`（本作定制 5.3，字符串长度 1 字节）。

`mainmenu.ws2` 的分派表**不改**：Steam 侧 `var[98]==102 -> AGS_001` 分支本就保留
（[doc/route-mechanics.md](../../doc/route-mechanics.md) §3）。

幂等：总是从 `backup/` 重新生成；`write_arc` 对逐字节相同的产物不重写。
自检（任一失败即中止）：Lua/PNA 未改动前的逐字节往返闸、按钮回读校验、
记录数与画布尺寸不变、朱莉线保护名单。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:                                    # 控制台按 UTF-8 输出（AGENTS §4）
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import agsbutton, lua53  # noqa: E402

sys.path.insert(0, os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev'))
from galrev.advhd import arc, pna  # noqa: E402

BACKUP = os.path.join(ROOT, 'backup')
ASSET = os.path.join(ROOT, 'asset')
RESOURCE = os.path.join(ROOT, 'resource')


def res_file(name):
    """规格里的素材路径相对 `resource/`；缺失即中止（不允许回退去读外部原版目录）。"""
    path = os.path.join(RESOURCE, name.replace('/', os.sep))
    if not os.path.exists(path):
        raise SystemExit('缺少 resource 素材：%s（先跑 script/build/import_route_assets.py）' % name)
    return open(path, 'rb').read()

OP_MOVE = 0
OP_LOADK = 1
OP_NEWTABLE = 11
OP_SELF = 12
OP_EQ = 31
OP_CALL = 36
OP_RETURN = 38
OP_JMP = 30
OP_FORLOOP = 39
OP_FORPREP = 40
OP_TFORLOOP = 42
OP_SETLIST = 43
# 本引擎在索引 9 处多一个操作码，故上游 5.3 里 >= 9 的 opcode 在本引擎一律 +1
# （RETURN=38 / FORLOOP=39 / FORPREP=40 / SETLIST=43；LOADK=1、NEWTABLE=11 不变）。
SBX_OPS = {OP_JMP, OP_FORLOOP, OP_FORPREP, OP_TFORLOOP}
RK_K = 256      # EQ/SELF 等 RK 操作数：>=256 表示常量（idx = 值-256）
SBX_BIAS = ((1 << 18) - 1) >> 1   # 本引擎 JMP/FORPREP 的 sBx 偏置 = 131071（不是 131072）


def _log(msg):
    sys.stdout.write(msg + '\n')


def load_spec():
    with open(os.path.join(ROOT, 'resource', 'route_entry.json'), encoding='utf-8') as fh:
        return json.load(fh)


def member(members, name):
    for n, d in members:
        if n.decode('utf-16le') == name:
            return d
    raise KeyError('%s 不在归档内' % name)


def set_member(members, name, data):
    for i, (n, _) in enumerate(members):
        if n.decode('utf-16le') == name:
            members[i] = (n, data)
            return
    raise KeyError('%s 不在归档内' % name)


# ── Lua 指令编解码 ─────────────────────────────────────────────────────────

def _fld(w):
    return {'op': w & 0x3F, 'A': (w >> 6) & 0xFF, 'B': (w >> 23) & 0x1FF,
            'C': (w >> 14) & 0x1FF, 'Bx': (w >> 14) & 0x3FFFF,
            'sBx': ((w >> 14) & 0x3FFFF) - SBX_BIAS}


def _mk(op, A=0, B=0, C=0, Bx=None):
    w = op | (A << 6)
    if Bx is not None:
        return w | (Bx << 14)
    return w | (B << 23) | (C << 14)


def _with(w, **kw):
    """只改指定字段。带 `Bx` 的参数走 Bx 形式（LOADK / sBx 跳转），
    带 `B`/`C` 的走 B/C 形式（NEWTABLE / SETLIST）——不能混用。"""
    f = _fld(w)
    f.update(kw)
    head = f['op'] | (f['A'] << 6)
    if 'Bx' in kw:
        return head | (f['Bx'] << 14)
    return head | (f['B'] << 23) | (f['C'] << 14)


def _insert_and_fix_jumps(code, ins_index, new_instr):
    """在 `ins_index` 处插入一条指令，并**重算全部 sBx 跳转**（不依赖「恰好不变」的假设）。"""
    jumps = []
    for i, w in enumerate(code):
        if _fld(w)['op'] in SBX_OPS:
            jumps.append((i, i + 1 + _fld(w)['sBx']))
    code.insert(ins_index, new_instr)

    def newpc(i):
        return i + 1 if i >= ins_index else i

    for i, target in jumps:
        ni, nt = newpc(i), newpc(target)
        nsbx = nt - (ni + 1)
        if not -(1 << 17) <= nsbx < (1 << 17):
            raise AssertionError('sBx 溢出于 pc=%d' % ni)
        code[ni] = _with(code[ni], Bx=nsbx + SBX_BIAS)
    return jumps


def _const_for(proto, value):
    """返回常量池中值为 `value` 的整数常量下标；没有则末尾追加（既有下标不变）。"""
    for i, (tag, v) in enumerate(proto.constants):
        if tag == lua53.T_NUMINT and v == value:
            return i
    proto.constants.append((lua53.T_NUMINT, value))
    return len(proto.constants) - 1


def _bump_for_bounds(proto, old, new, expect=1):
    """把 `proto` 里所有「上界 == old」的数值 FOR 循环改成 `new`。

    FORPREP A 之前依次是 `LOADK R(A)=init`、`LOADK R(A+1)=limit`、`LOADK R(A+2)=step`
    ⇒ 上界指令在 `forprep_pc - 2`（不是 -1）。
    """
    code = proto.code
    limits = []
    for i, w in enumerate(code):
        if _fld(w)['op'] != OP_FORPREP:
            continue
        lim = i - 2
        f = _fld(code[lim])
        if f['op'] == OP_LOADK and proto.constants[f['Bx']][1] == old \
                and _fld(code[i])['A'] + 1 == f['A']:
            limits.append(lim)
    if len(limits) != expect:
        raise AssertionError('上界 == %d 的数值 FOR 循环在 %s 找到 %d 个（期望 %d）'
                             % (old, proto.source, len(limits), expect))
    k = _const_for(proto, new)
    for lim in limits:
        code[lim] = _with(code[lim], Bx=k)
    return len(limits)


def _insert_block(code, ins_index, block, block_jumps):
    """在 `ins_index` 插入一段指令，并重算全部 sBx。

    `block_jumps` = [(block 内偏移, 旧代码里的目标 pc)]，用于修正新块自身的 JMP。
    旧代码里的跳转按「插入点之后整体后移 len(block)」重算；新块指令不在旧跳转名单里。
    """
    L = len(block)
    old_jumps = []
    for i, w in enumerate(code):
        if _fld(w)['op'] in SBX_OPS:
            old_jumps.append((i, i + 1 + _fld(w)['sBx']))
    code[ins_index:ins_index] = block

    def newpc(i):
        return i + L if i >= ins_index else i

    for i, target in old_jumps:
        ni, nt = newpc(i), newpc(target)
        code[ni] = _with(code[ni], Bx=(nt - (ni + 1)) + SBX_BIAS)
    for off, old_target in block_jumps:
        ni, nt = ins_index + off, newpc(old_target)
        code[ni] = _with(code[ni], Bx=(nt - (ni + 1)) + SBX_BIAS)
    return L


def _repel_loop_limit(proto, old_upper, new_upper, expect=1):
    """把「数值 FOR 上界 == old_upper」的循环上界改成 new_upper（常量为值本身）。"""
    k = _const_for(proto, new_upper)
    hit = 0
    for i, w in enumerate(proto.code):
        if _fld(w)['op'] != OP_FORPREP:
            continue
        lim = i - 2
        f = _fld(proto.code[lim])
        if f['op'] == OP_LOADK and proto.constants[f['Bx']][1] == old_upper                 and _fld(proto.code[i])['A'] + 1 == f['A']:
            proto.code[lim] = _with(proto.code[lim], Bx=k)
            hit += 1
    if hit != expect:
        raise AssertionError('%s：上界 == %d 的循环找到 %d 个（期望 %d）'
                             % (proto.source, old_upper, hit, expect))
    return hit


def patch_lua_cast(top, spec):
    """角色高亮：让 `StorySelCursor(id)` 在 id == AGS(102) 时显示新增的 Cast 图层。

    - 两个 hide 循环（`MenuEffectStart` 开界面时、`StorySelCursor` 每次选择时）的上界
      由 28 扩到 29，保证新层不会残留；
    - `StorySelCursor` 在「hide 22..29」之后插一段：
          if id == 102 then setSubLayerVisible(29, 1); goto hide-31..39 end
      （hide-31..39 之后自然落到 `return`，与 101..107 分支同构。）
    """
    ch = spec['cast_highlight']
    old_up = ch['lua']['hide_loop_old_upper']
    new_up = ch['lua']['hide_loop_new_upper']
    # 两处 hide 循环 + initSubLayer 循环，上界一律 28 -> 29。
    # init 那处不能漏：普通子层必须先 initSubLayer，否则 setSubLayerVisible 静默无效。
    for path in ch['lua']['hide_loop_protos'] + ch['lua'].get('init_loop_protos', []):
        _repel_loop_limit(lua53.find(top, path), old_up, new_up, expect=1)

    proto = lua53.find(top, ch['lua']['proto_path'])
    code = proto.code
    # 找到「hide 22..<new_up>」那个 FORLOOP，就插在它后面
    forprep = None
    for i, w in enumerate(code):
        if _fld(w)['op'] != OP_FORPREP:
            continue
        lim = i - 2
        f = _fld(code[lim])
        if f['op'] == OP_LOADK and proto.constants[f['Bx']][1] == new_up:
            forprep = i
            break
    if forprep is None:
        raise AssertionError('未找到 hide 22..%d 的循环' % new_up)
    loop_pc = forprep
    while _fld(code[loop_pc])['op'] != OP_FORLOOP:
        loop_pc += 1
    ins = loop_pc + 1
    after = ins                          # 旧代码里紧随循环之后的那条指令
    # 旧代码里「hide 31..39」循环：序列是 LOADK init / LOADK limit / LOADK step / FORPREP。
    # 必须跳到**序列第一条 LOADK**，不能直接跳 FORPREP —— FORPREP 依赖 R(A)/R(A+1)/R(A+2)
    # 已被那三条填好，直接跳过去会拿到别的寄存器内容（实测：'for' limit must be a number）。
    hide_fp = None
    for i in range(ins, len(code)):
        if _fld(code[i])['op'] == OP_FORPREP:
            hide_fp = i
            break
    if hide_fp is None:
        raise AssertionError('未找到 hide 31..39 的循环')
    hide_sprites = hide_fp - 3
    if not (_fld(code[hide_sprites])['op'] == OP_LOADK
            and _fld(code[hide_sprites])['A'] == _fld(code[hide_fp])['A']
            and _fld(code[hide_sprites + 1])['op'] == OP_LOADK
            and _fld(code[hide_sprites + 2])['op'] == OP_LOADK):
        raise AssertionError('hide 31..39 循环前面不是预期的三条 LOADK（init/limit/step）')

    k_id = _const_for(proto, ch['lua']['special_id'])
    k_cast = _const_for(proto, new_up)
    k_sl = _const_for(proto, ch['lua']['sublayer_const_name']) if 'sublayer_const_name' in ch['lua'] else None
    k_storymenu = next(i for i, (t, v) in enumerate(proto.constants) if v == b'StoryMenu')
    k_storybace = next(i for i, (t, v) in enumerate(proto.constants) if v == b'StoryBace')
    k_setvis = next(i for i, (t, v) in enumerate(proto.constants) if v == b'setSubLayerVisible')
    k_one = next(i for i, (t, v) in enumerate(proto.constants) if t == lua53.T_NUMINT and v == 1)

    block = [
        _mk(OP_EQ, 0, B=2, C=RK_K + k_id),                  # EQ R2, K(id)
        _mk(OP_JMP),                                        # JMP -> after（不相等）
        _mk(OP_SELF, 6, B=5, C=RK_K + k_setvis),            # R6 := R5.setSubLayerVisible; R7 := R5
        _mk(OP_LOADK, 8, Bx=k_storymenu),
        _mk(OP_LOADK, 9, Bx=k_storybace),
        _mk(OP_LOADK, 10, Bx=k_cast),
        _mk(OP_LOADK, 11, Bx=k_one),
        _mk(OP_CALL, 6, B=6, C=1),                          # setSubLayerVisible(StoryMenu, StoryBace, cast, 1)
        _mk(OP_JMP),                                        # JMP -> hide_sprites
    ]
    _insert_block(code, ins, block, [(1, after), (8, hide_sprites)])


def patch_lua(blob, spec):
    sm = spec['story_menu']
    top = lua53.load(blob)
    if lua53.dump(top) != blob:
        raise AssertionError('Lua 往返闸失败（序列化与原始字节不一致）')
    proto = lua53.find(top, sm['proto_path'])
    code = proto.code

    # 定位按钮表构造：SETLIST(C=1) 且其前恰为 NEWTABLE(array=n) + n 条 LOADK
    setlist_pc = None
    n_old = None
    for i, w in enumerate(code):
        f = _fld(w)
        if f['op'] != OP_SETLIST or f['C'] != 1:
            continue
        n = f['B']
        nt = i - n - 1
        if nt < 0:
            continue
        if _fld(code[nt])['op'] != OP_NEWTABLE or _fld(code[nt])['B'] != n:
            continue
        if all(_fld(code[k])['op'] == OP_LOADK for k in range(nt + 1, i)):
            setlist_pc, n_old, newtable_pc = i, n, nt
            break
    if setlist_pc is None:
        raise AssertionError('未找到按钮表构造（NEWTABLE + n*LOADK + SETLIST）')
    if n_old != sm['for_bound'] - 1:
        raise AssertionError('现有表长 %d 与规格（%d-1）不符' % (n_old, sm['for_bound']))

    first_val_reg = _fld(code[newtable_pc + 1])['A']
    append_reg = first_val_reg + n_old
    if append_reg >= proto.max_stack_size:
        raise AssertionError('追加寄存器 R%d 超出 maxstack %d' % (append_reg, proto.max_stack_size))

    # 追加常量（末尾追加，既有下标不变；已存在则复用）
    k_id = _const_for(proto, sm['table_append'])

    # 1) NEWTABLE array n -> n+1
    code[newtable_pc] = _with(code[newtable_pc], B=n_old + 1)
    # 2) SETLIST 前插入一条 LOADK append_reg := K(k_id)，并重算跳转
    _insert_and_fix_jumps(code, setlist_pc, _mk(OP_LOADK, append_reg, Bx=k_id))
    # 3) SETLIST B n -> n+1（覆盖 R(first)..R(first+n)，含新追加寄存器）
    code[setlist_pc + 1] = _with(code[setlist_pc + 1], B=n_old + 1)
    # 4) 所有「上界 == n_old」的数值 FOR 循环（表构造循环 + 其它逐按钮循环）
    for path in [sm['proto_path']] + [list(p) for p in sm.get('additional_for_loop_protos', [])]:
        _bump_for_bounds(lua53.find(top, path), n_old, sm['for_bound'])

    if spec.get('cast_highlight'):
        patch_lua_cast(top, spec)

    out = lua53.dump(top)
    if lua53.dump(lua53.load(out)) != out:
        raise AssertionError('改写后 Lua 往返闸失败')
    return out


# ── PNA ────────────────────────────────────────────────────────────────────

def patch_pna(blob, spec, on_png, def_png):
    sm = spec['story_menu']
    p = pna.parse(blob)
    if pna.serialize(p) != blob:
        raise AssertionError('PNA 往返闸失败（序列化与原始字节不一致）')
    w_on, h_on = pna.png_dimensions(on_png)
    w_def, h_def = pna.png_dimensions(def_png)
    if (w_on, h_on) != (w_def, h_def):
        raise AssertionError('on/def 按钮尺寸不一致：%s / %s' % ((w_on, h_on), (w_def, h_def)))

    for idx, png, box in ((sm['button_record_indices']['on'], on_png, sm['button_boxes']['on']),
                          (sm['button_record_indices']['def'], def_png, sm['button_boxes']['def'])):
        layer = p.layers[idx]
        if layer.data is not None and layer.data != png:
            raise AssertionError('记录 %d 已是别的图层内容，拒绝覆盖' % idx)
        layer.u0 = 0                                  # 哨兵 -> 真实叠加层（记录数不变 => 子层编号不变）
        layer.layer_id = p.count - 1 - idx            # 位置量不变量
        layer.x, layer.y = box
        layer.width, layer.height = w_on, h_on
        layer.marker_lo = 0
        layer.marker_hi = 0x3FF00000                  # 不透明度 double 1.0
        layer.reserved = 0
        layer.data = png
        layer.size = len(png)
    out = pna.serialize(p)

    q = pna.parse(out)
    if q.count != p.count or (q.width, q.height) != (p.width, p.height):
        raise AssertionError('PNA 记录数/画布尺寸被改变')
    for idx in (sm['button_record_indices']['on'], sm['button_record_indices']['def']):
        if q.layers[idx].data is None or q.layers[idx].u0 != 0:
            raise AssertionError('记录 %d 未落成真实图层' % idx)
    return out


def patch_cast_record(blob, spec, png):
    """把「角色高亮」Cast 图层落到 PNA 的指定记录（默认 29）。"""
    ch = spec['cast_highlight']
    p = pna.parse(blob)
    if pna.serialize(p) != blob:
        raise AssertionError('PNA 往返闸失败（%s）' % p.path)
    idx = ch['record']
    w, h = pna.png_dimensions(png)
    layer = p.layers[idx]
    if layer.data is not None and layer.data != png:
        raise AssertionError('PNA 记录 %d 已是别的图层内容，拒绝覆盖' % idx)
    layer.u0 = 0
    layer.layer_id = p.count - 1 - idx
    layer.x, layer.y = ch['box']
    layer.width, layer.height = w, h
    layer.marker_lo = 0
    layer.marker_hi = 0x3FF00000
    layer.reserved = 0
    layer.data = png
    layer.size = len(png)
    out = pna.serialize(p)
    q = pna.parse(out)
    if q.count != p.count or (q.width, q.height) != (p.width, p.height):
        raise AssertionError('PNA 记录数/画布尺寸被改变（%s）' % p.path)
    if q.layers[idx].data is None or q.layers[idx].u0 != 0:
        raise AssertionError('PNA 记录 %d 未落成真实图层' % idx)
    return out


def patch_base_pna(blob, base, src_on, src_def):
    """把「原版日文」按钮图形（字节保真）落到 base `SYS_Story.pna` 的记录 19/20。

    base/英式 PNA 的按钮与中文 PNA 在屏位置一致（见 `resource/route_entry.json` 的
    `base_ui_entry.button_boxes_derivation`），所以直接沿用原版图形自带的 box 约定。
    """
    p = pna.parse(blob)
    if pna.serialize(p) != blob:
        raise AssertionError('base PNA 往返闸失败')
    for tag, png in (('on', src_on), ('def', src_def)):
        idx = base['button_record_indices'][tag]
        box = base['button_boxes'][tag]
        w, h = pna.png_dimensions(png)
        if (w, h) != (pna.png_dimensions(src_on)[0], pna.png_dimensions(src_on)[1]):
            raise AssertionError('on/def 原版按钮尺寸不一致')
        layer = p.layers[idx]
        if layer.data is not None and layer.data != png:
            raise AssertionError('base 记录 %d 已是别的图层内容，拒绝覆盖' % idx)
        layer.u0 = 0
        layer.layer_id = p.count - 1 - idx
        layer.x, layer.y = box
        layer.width, layer.height = w, h
        layer.marker_lo = 0
        layer.marker_hi = 0x3FF00000
        layer.reserved = 0
        layer.data = png
        layer.size = len(png)
    out = pna.serialize(p)
    q = pna.parse(out)
    if q.count != p.count or (q.width, q.height) != (p.width, p.height):
        raise AssertionError('base PNA 记录数/画布尺寸被改变')
    for tag in ('on', 'def'):
        idx = base['button_record_indices'][tag]
        if q.layers[idx].data is None or q.layers[idx].u0 != 0:
            raise AssertionError('base 记录 %d 未落成真实图层' % idx)
    return out


# ── 主流程 ─────────────────────────────────────────────────────────────────

def main():
    spec = load_spec()
    sm = spec['story_menu']
    bg = spec['button_graphic']

    guard = json.load(open(os.path.join(ROOT, 'resource', 'julie_guard.json'), encoding='utf-8'))
    for a in (sm['button_pna_archive'].lower(), sm['archive'].lower()):
        if a in [x.lower() for x in guard['archives']] + [x.lower() for x in guard['archive_prefixes']]:
            raise SystemExit('命中朱莉线保护名单：%s' % a)

    # 1) 按钮图形
    ref_members = arc.read_raw(os.path.join(BACKUP, sm['button_pna_archive'].replace('/', os.sep)))
    ref_pna = pna.parse(member(ref_members, sm['button_pna_member']))
    layers = {l.index: l.data for l in ref_pna.png_layers}
    tgt = bg['target_button_records']
    srcr = bg['source_button_records']
    # 内容只读 resource/ 入库件；几何仍从 backup 的官方按钮实测，并用 verify 复核入库件
    geom = agsbutton.measure({tgt['on']: layers[tgt['on']], tgt['def']: layers[tgt['def']],
                              srcr['on']: layers[srcr['on']], srcr['def']: layers[srcr['def']]})
    button_png = {tag: res_file(bg['resource_files'][tag]) for tag in ('on', 'def')}
    for tag in ('on', 'def'):
        agsbutton.verify(button_png[tag], layers[tgt[tag]], layers[srcr[tag]], geom)
    _log('按钮图形：%s（字距 %.3f、字格原点差 %.3f、整数平移 %d）—— 对官方按钮复核通过'
         % (bg['resource_files']['on'] + ' / ' + bg['resource_files']['def'],
            geom['advance'], geom['grid_off'], geom['shift_int']))

    # 1b) 角色高亮 Cast 图层（原版第 2 条线 = AGS）
    ch = spec.get('cast_highlight')
    cast_png = None
    if ch:
        cast_png = res_file(ch['resource_file'])
        w, h = pna.png_dimensions(cast_png)
        _log('Cast 高亮：%s = %dx%d（%s；原版 %s 记录 %d）'
             % (ch['resource_file'], w, h, ch['source']['label'],
                ch['source']['pna_member'], ch['source']['record']))

    # 2) PNA
    cn_pna = patch_pna(member(ref_members, sm['button_pna_member']), spec,
                       button_png['on'], button_png['def'])
    if cast_png is not None:
        cn_pna = patch_cast_record(cn_pna, spec, cast_png)
    set_member(ref_members, sm['button_pna_member'], cn_pna)
    out_sys = os.path.join(ASSET, sm['button_pna_archive'].replace('/', os.sep))
    os.makedirs(os.path.dirname(out_sys), exist_ok=True)
    arc.write_arc(ref_members, out_sys)
    arc.verify(out_sys, expect_count=len(ref_members))
    _log('PNA：%s 记录 %d/%d 落成按钮图层 -> %s'
         % (sm['button_pna_member'], sm['button_record_indices']['on'],
            sm['button_record_indices']['def'], os.path.relpath(out_sys, ROOT)))

    # 2b) base（英/默认）UI：把原版日文入口图形落到 base SYS_Story.pna 的记录 19/20
    bu = spec.get('base_ui_entry')
    if bu:
        rec = bu['source']['records']
        src_on = res_file(bu['resource_files']['on'])
        src_def = res_file(bu['resource_files']['def'])
        base_members = arc.read_raw(os.path.join(BACKUP, bu['archive']))
        base_pna = patch_base_pna(member(base_members, bu['pna_member']), bu, src_on, src_def)
        if cast_png is not None:
            # base 的 Cast 图层与中文同一在屏位置（box 直接沿用原版）
            base_pna = patch_cast_record(base_pna, spec, cast_png)
        set_member(base_members, bu['pna_member'], base_pna)
        out_base = os.path.join(ASSET, bu['archive'])
        os.makedirs(os.path.dirname(out_base), exist_ok=True)
        arc.write_arc(base_members, out_base)
        arc.verify(out_base, expect_count=len(base_members))
        _log('base PNA：%s 记录 %d/%d = 原版日文入口（%s） -> %s'
             % (bu['pna_member'], bu['button_record_indices']['on'],
                bu['button_record_indices']['def'], bu['source']['label'],
                os.path.relpath(out_base, ROOT)))

    # 3) Lua
    lua_members = arc.read_raw(os.path.join(BACKUP, sm['archive'].replace('/', os.sep)))
    set_member(lua_members, sm['lua_member'], patch_lua(member(lua_members, sm['lua_member']), spec))
    out_lua = os.path.join(ASSET, sm['archive'].replace('/', os.sep))
    os.makedirs(os.path.dirname(out_lua), exist_ok=True)
    arc.write_arc(lua_members, out_lua)
    arc.verify(out_lua, expect_count=len(lua_members))
    _log('Lua：%s/%s 按钮表 %d -> %d、追加 id %d -> %s'
         % (sm['archive'], sm['lua_member'], sm['for_bound'] - 1, sm['for_bound'],
            sm['table_append'], os.path.relpath(out_lua, ROOT)))
    _log('完成。')


if __name__ == '__main__':
    main()
