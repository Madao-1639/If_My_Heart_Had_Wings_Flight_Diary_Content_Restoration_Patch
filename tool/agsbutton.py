# -*- coding: utf-8 -*-
"""姬城线（`AGS_001`）路线按钮图形的**验收工具**（`verify` / `measure`）。

> **产物已定版入库**：中文按钮成品为 `resource/route_entry/ags_button_cn_{on,def}.png`，
> 构建只读这两个文件，**不再就地生成**（生成脚本已随定版移除）。本模块保留的是
> 「拿 `backup/` 里的官方中文按钮，反过来校验入库件」的那套判据与几何实测。

## 这两个按钮当初是怎么来的（保留下来作为溯源与判据）

Steam 官中的 7 个路线按钮（`zh-CN/SysGraphic.arc` 的 `SYS_C_Story.pna` → `StoryBace` 子层）是
**位图**：字体、字号、蓝色填充、白色描边、45° 旋转、字距都固化在像素里。要新增第 8 个按钮
（姬城姐妹线，日文原版「アフターストーリー：姫城姉妹編」，官中平行条目「风户姐妹的日常」），
**重新用字体排版无法复刻描边与亚像素位置**；而所需 7 个字在既有按钮里全都有：

| 目标字 | 来源按钮 | 该字在来源串中从右数第几位 |
|---|---|---|
| 姬、城 | 「姬城萤的场合」 | 5、4 |
| 姐、妹、的、日、常 | 「风户姐妹的日常」 | 4、3、2、1、0 |

「姬城姐妹的日常」与「风户姐妹的日常」**等长（7 字）且同字体同字距**，把前 2 字「风户」
换成「姬城」即可 ⇒ 只动 2 个字位（来源字形做**整数像素平移**，不重采样）。

## 几何量（每次校验都从像素实测，不写死）

- 按钮文字**右对齐**（末字与箭头位置固定）。
- 字距 `advance`：由「风户姐妹的日常」7 个字位的蓝色连通域质心做**公共斜率**最小二乘拟合
  （实测约 14.71 px，沿文字方向）。
- 字格原点差 `grid_off`：用两串共有的「的」（都自右数第 2 位）质心之差（实测约 −0.91 px）。
- 于是「姬/城」要落到目标「风/户」位，需要沿文字方向平移 `grid_off − advance`
  （约 −15.62 px，即斜向**上左** (−11.05, −11.05)）；实际取整到 (−11, −11)，残余 0.05 px。

## `verify()` 五道闸（对入库 PNG 逐项断言）

1. 仍是 7 个字位 + 1 个箭头（8 个蓝色连通域，同字碎片已合并）；
2. 未替换的 5 个字位与官中目标按钮**同位**；
3. 被替换的 2 个字位 = 来源按钮对应字位整平移后的位置；
4. 掩膜内**逐字节** = 来源整平移、掩膜外**逐字节** = 官中目标（防重采样/羽化回归）；
5. PNG 辅助块（`gAMA/cHRM/bKGD/pHYs/tEXt`）与官中目标一致（`bKGD=白` 影响查看器合成背景）。

依赖：Pillow + numpy（EDA 环境已装）；连通域与腐蚀/膨胀都用 numpy 自实现，不引入 scipy。
"""
import io
import math
import struct

import numpy as np
from PIL import Image

D = 1.0 / math.sqrt(2.0)          # 45° 旋转的坐标换算系数

# 目标（官中「风户姐妹的日常」）与来源（官中「姬城萤的场合」）在 PNA 里的记录下标。
# on = 亮（hover）、def = 暗（默认）；两态同一版式，仅颜色/位移不同。
TARGET = {'on': 9, 'def': 10}
SOURCE = {'on': 13, 'def': 14}

# 目标「风户姐妹的日常」中要被替换掉的 2 个字位（0 基，自左向右）与来源对应字位
# （来源「姬城萤的场合」的 0、1 位就是「姬」「城」）。
REPLACE_SLOTS = (0, 1)

BLUE_R = 170          # 文字填充蓝：r < BLUE_R 且 b > BLUE_B
BLUE_B = 200
ALPHA_MIN = 150
S_MAX = 14.0          # 文字带半宽（垂直文字方向，px）——文字描边实测 |s| <= 12
T_PAD = 5.0           # 左端额外留白（含白描边）


class ButtonError(ValueError):
    pass


# ── 基础工具 ───────────────────────────────────────────────────────────────

def _rgba(layer_png):
    return np.asarray(Image.open(io.BytesIO(layer_png)).convert('RGBA')).astype(float)


def _blue_mask(arr):
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    return (b > BLUE_B) & (r < BLUE_R) & (a > ALPHA_MIN)


def _label(boolean):
    """4/8 邻接连通域（BFS，纯 numpy 扫描），返回与输入同形的 int 标签图。"""
    h, w = boolean.shape
    lab = np.zeros((h, w), np.int32)
    cur = 0
    ys, xs = np.nonzero(boolean)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if lab[sy, sx]:
            continue
        cur += 1
        stack = [(sy, sx)]
        lab[sy, sx] = cur
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and boolean[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = cur
                        stack.append((ny, nx))
    return lab


def _glyph_centroids(arr, min_px=10, merge_gap=8.0):
    """蓝色填充连通域的质心（按沿文字方向的位置排序）。

    同一字被拆成多个连通域（如「合」）用 `merge_gap`（沿文字方向的距离）合并。
    返回 [(t, s, n), ...]，`t = (x+y)/√2` 为文字方向坐标，`s = (x−y)/√2` 为垂直方向。
    """
    lab = _label(_blue_mask(arr))
    out = []
    for i in range(1, int(lab.max()) + 1):
        ys, xs = np.nonzero(lab == i)
        if len(xs) < min_px:
            continue
        out.append(((xs + ys).mean() * D, (xs - ys).mean() * D, len(xs)))
    out.sort(key=lambda v: v[0])
    merged = []
    for t, s, n in out:
        if merged and t - merged[-1][0] < merge_gap:
            pt, _, pn = merged[-1]
            merged[-1] = ((pt * pn + t * n) / (pn + n), 0.0, pn + n)
        else:
            merged.append((t, s, n))
    return merged


def _measure(target_arr, source_arr):
    """实测字距 `advance`、字格原点差 `grid_off`、需要的平移量 `delta_t`（沿文字方向）。"""
    ct = _glyph_centroids(target_arr)[:-1]      # 末位是箭头，去掉
    cs = _glyph_centroids(source_arr)[:-1]
    if len(ct) != 7 or len(cs) != 6:
        raise ButtonError('字位数不符：目标 %d（期望 7）、来源 %d（期望 6）' % (len(ct), len(cs)))
    # 拟合用「从右数」下标：r=0 是末字，r 增大向左 ⇒ t = a − advance·r
    ct_r = ct[::-1]
    cs_r = cs[::-1]

    def intercept(pts, b):
        n = len(pts)
        sy = sum(c for c, _, _ in pts)
        sr = sum(range(n))
        return (sy + b * sr) / n

    def sse(b):
        tot = 0.0
        for pts in (ct_r, cs_r):
            a = intercept(pts, b)
            tot += sum((c - (a - b * r)) ** 2 for r, (c, _, _) in enumerate(pts))
        return tot

    grid_pts = np.linspace(13.0, 16.5, 3501)
    advance = float(grid_pts[int(np.argmin([sse(b) for b in grid_pts]))])
    if not 13.0 <= advance <= 16.0:
        raise ButtonError('字距实测 %.3f 超出合理区间 [13,16]' % advance)

    # 两串共有的「的」都从右数第 2 位（倒序后下标 2）
    grid_off = ct_r[2][0] - cs_r[2][0]
    if not -3.0 <= grid_off <= 3.0:
        raise ButtonError('字格原点差实测 %.3f 超出合理区间 [−3,3]' % grid_off)

    # 目标第 6 位（从右数；0 基）需要来源第 5 位的内容 -> 平移 (grid_off − advance)
    delta_t = grid_off - advance
    return {'advance': advance, 'grid_off': grid_off, 'delta_t': delta_t,
            'a_t': intercept(ct_r, advance), 'centroids': [c for c, _, _ in ct_r]}


def _translate_int(img, dx, dy):
    """整数像素平移：把内容整体移动 `(dx, dy)`，即 `out[y, x] = in[y − dy, x − dx]`，
    越界补全透明。

    本按钮的位移是「1 个字位」= 沿 45° 方向 `advance/√2` ≈ 11.05 px（**向上左**，即
    dx=dy≈−11），取整后残余 0.05 px，远小于一个像素、肉眼不可见。用纯像素拷贝
    （**不重采样**）可以完全避开双三次插值在「不透明文字 / 半透明底板」硬边上的
    振铃与量化噪声。
    """
    arr = np.asarray(img).astype(np.uint8)
    h, w = arr.shape[:2]
    out = np.zeros_like(arr)
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    if xs1 > xs0 and ys1 > ys0:
        out[ys0:ys1, xs0:xs1] = arr[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return Image.fromarray(out, 'RGBA')


def mask_region(geom, h, w):
    """目标上「要被替换」的两格区域（布尔图）：沿文字方向的区间 × 文字带。

    目标共 7 字；要替换的是自左数第 0、1 字 ⇒ 从右数第 (7−1−0)=6、5 字。
    """
    yy, xx = np.mgrid[0:h, 0:w]
    t = (xx + yy) * D
    s = (xx - yy) * D
    b_adv = geom['advance']
    total_chars = len(geom['centroids'])
    first_right = total_chars - 1 - REPLACE_SLOTS[0]
    last_right = total_chars - 1 - REPLACE_SLOTS[-1]
    t_lo = geom['a_t'] - b_adv * first_right - b_adv / 2.0 - T_PAD
    t_hi = geom['a_t'] - b_adv * last_right + b_adv / 2.0
    return (t >= t_lo) & (t <= t_hi) & (np.abs(s) <= S_MAX)


def _png_chunks(blob):
    """拆 PNG 为 [(tag, 完整块字节（含长度/类型/数据/CRC）)]，保留原始字节不做重编码。"""
    p, out = 8, []
    while p + 8 <= len(blob):
        ln = struct.unpack('>I', blob[p:p + 4])[0]
        tag = blob[p + 4:p + 8]
        out.append((tag, blob[p:p + 12 + ln]))
        p += 12 + ln
        if tag == b'IEND':
            break
    return out


def measure(layers):
    """`layers`：{记录下标: PNG 字节}，需含 TARGET/SOURCE 的 on/def 四张。

    返回几何量（`advance` / `grid_off` / `delta_t` / `shift_int` / `shift_residual` / `a_t` / `centroids`）。
    供「按钮 PNG 已入库、build 只读入库文件但仍要对官方按钮做回读校验」的场景。
    """
    for k in list(TARGET.values()) + list(SOURCE.values()):
        if k not in layers:
            raise ButtonError('PNA 缺少记录 %d' % k)
    geom = _measure(_rgba(layers[TARGET['on']]), _rgba(layers[SOURCE['on']]))
    geom['shift_int'] = int(round(geom['delta_t'] * D))
    geom['shift_residual'] = geom['delta_t'] * D - geom['shift_int']
    return geom


def _nb(m):
    """3×3 邻域并集（用 np.roll；图像边缘处掩膜为 False，环绕无影响）。"""
    out = m.copy()
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            out |= np.roll(np.roll(m, a, 0), b, 1)
    return out


def _dilate(m, k=1):
    for _ in range(k):
        m = _nb(m)
    return m


def verify(png_bytes, target_png, source_png, geom, tol=1.0):
    """回读校验：

    1. 仍是 7 个字位 + 1 个箭头（共 8 个蓝色连通域，同字碎片已合并）；
    2. 后 5 个字位（姐妹的日常）与官中目标按钮**同位**（未动）；
    3. 前 2 个字位（姬城）等于来源按钮对应字位平移 `delta_t` 后的位置。

    直接比「间距 == advance」没有意义：不同字的填充质心相对字格有 ±1px 的
    字形偏置，`advance` 是字格步长，不是质心步长。
    """
    got = _glyph_centroids(_rgba(png_bytes))
    tgt = _glyph_centroids(_rgba(target_png))
    src = _glyph_centroids(_rgba(source_png))
    if len(got) != 8:
        raise ButtonError('回读连通域 %d（期望 7 字 + 1 箭头 = 8）' % len(got))
    # 右对齐：两边皆自右数；下标 0 = 箭头，下标 i(>=1) = 从右数第 i−1 个字
    got_r = [c for c, _, _ in got[::-1]]
    tgt_r = [c for c, _, _ in tgt[::-1]]
    src_r = [c for c, _, _ in src[::-1]]
    if len(tgt_r) != 8 or len(src_r) != 7:
        raise ButtonError('参考按钮连通域数异常（目标 %d、来源 %d）' % (len(tgt_r), len(src_r)))
    tail_err = max(abs(got_r[i] - tgt_r[i]) for i in range(6))   # 箭头 + 姐妹的日常
    if tail_err > tol:
        raise ButtonError('未替换字位与官中目标偏离 %.2f（容差 %.2f）' % (tail_err, tol))
    shift = geom.get('shift_int', round(geom['delta_t'] * D)) * math.sqrt(2.0)   # 实际用的整数平移（换算到 t）
    # 目标「风」位（从右数 6 -> 倒序下标 7）← 来源「姬」（倒序下标 6）；
    # 目标「户」位（倒序下标 6）← 来源「城」（倒序下标 5）。
    head_err = max(abs(got_r[7] - (src_r[6] + shift)),
                   abs(got_r[6] - (src_r[5] + shift)))
    if head_err > tol:
        raise ButtonError('替换字位与来源平移后偏离 %.2f（容差 %.2f）' % (head_err, tol))

    # 4. 整数平移一致性（防重采样噪声回归）：
    #    - 掩膜核心（向里收 3 px）内，产物必须**逐字节**等于「来源整数平移」；
    #    - 掩膜之外（向外扩 3 px 以外的区域），产物必须**逐字节**等于目标。
    #    这两条任一不过，就说明又引入了插值/混合，会重新出现「杂乱像素点」。
    gi = np.asarray(Image.open(io.BytesIO(png_bytes)).convert('RGBA'))
    ti = np.asarray(Image.open(io.BytesIO(target_png)).convert('RGBA'))
    si = np.asarray(Image.open(io.BytesIO(source_png)).convert('RGBA'))
    h, w = ti.shape[:2]
    _i = geom.get('shift_int', round(geom['delta_t'] * D))
    sh = np.asarray(_translate_int(Image.fromarray(si, 'RGBA'), _i, _i))[:h, :w]
    m = mask_region(geom, h, w)
    # 入库件是硬掩膜版本：整张掩膜都必须逐字节 = 来源整平移（描边像素绝不能被混合「调暗」）
    core = m
    far = _dilate(m, 3)
    if core.any() and not (gi[core] == sh[core]).all():
        bad = int((gi[core] != sh[core]).any(axis=-1).sum())
        raise ButtonError('掩膜内 %d 像素与「来源整数平移」不一致（重采样/混合又进来了）' % bad)
    out = ~far
    if out.any() and not (gi[out] == ti[out]).all():
        bad = int((gi[out] != ti[out]).any(axis=-1).sum())
        raise ButtonError('掩膜之外 %d 像素与目标不一致' % bad)

    # 5. PNG 结构保真：非 IDAT 块（gAMA/cHRM/bKGD/pHYs/tEXt）必须与目标一致。
    #    bKGD=白是不透明观众合成时用的背景色；漏掉后不同谱的查看器会把半透明底板
    #    往黑里合成，近透明像素看上去就是「黑点」。
    ttags = [t for t, _ in _png_chunks(target_png) if t != b'IDAT']
    gtags = [t for t, _ in _png_chunks(png_bytes) if t != b'IDAT']
    if ttags != gtags:
        raise ButtonError('PNG 辅助块与目标按钮不一致：%r != %r' % (gtags, ttags))
    return got_r
