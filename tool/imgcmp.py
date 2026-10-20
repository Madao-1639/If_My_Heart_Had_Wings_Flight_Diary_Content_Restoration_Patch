# -*- coding: utf-8 -*-
"""图像内容等价判定（用于「内容对齐」：名字不同但内容实质相同 ⇒ 不纠正）。

判据（用户 2026-10-19 定案）：
* **字节相同** ⇒ 等价；
* **PNG**：解码到 640×360 RGB 后逐字节比；`mean_abs < 3.0` 且 `>16 的字节占比 < 3%`
  ⇒ 视为**水印级**差异，等价（如 `FDSDEV14_02B` ↔ `FDSDEV14_02B_SC`）；
* **PNA**：画布尺寸相同且**图层图像哈希多重集相同** ⇒ 等价（引用名不同、图层相同）。

PNG 解码用 ffmpeg（本机无 PIL）；结果按 sha256 缓存在 `tmp/_imgcmp/`。
"""
import hashlib
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'tmp', '_imgcmp')
MEAN_MAX = 3.0
BIG_RATIO_MAX = 0.03


def _raw(data):
    """PNG bytes -> 640x360 rgb24 raw（缓存）。"""
    h = hashlib.sha256(data).hexdigest()
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, h + '.raw')
    if os.path.exists(out):
        return open(out, 'rb').read()
    src = os.path.join(CACHE, h + '.png')
    with open(src, 'wb') as fh:
        fh.write(data)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src,
                    '-vf', 'scale=640:360:force_original_aspect_ratio=decrease,'
                           'pad=640:360:(ow-iw)/2:(oh-ih)/2',
                    '-f', 'rawvideo', '-pix_fmt', 'rgb24', out], check=True)
    return open(out, 'rb').read()


def png_equal(a, b):
    """-> (bool, mean_abs, big_ratio)"""
    x, y = _raw(a), _raw(b)
    n = min(len(x), len(y))
    if n == 0:
        return False, 999.0, 1.0
    s = big = 0
    for i in range(n):
        d = abs(x[i] - y[i])
        s += d
        if d > 16:
            big += 1
    mean = s / n
    ratio = big / n
    return (mean < MEAN_MAX and ratio < BIG_RATIO_MAX), mean, ratio


def pna_sig(data):
    from tool import pna
    d = pna.load(data)
    imgs = d.get('images') or []
    hs = sorted(hashlib.sha256(x if isinstance(x, (bytes, bytearray)) else b'').hexdigest()
                for x in imgs)
    return (d.get('canvas_w'), d.get('canvas_h'), hs)


def same_content(name_a, data_a, name_b, data_b):
    """-> (bool, reason)。名字只用于选判定方式。"""
    if data_a == data_b:
        return True, 'identical'
    ua, ub = name_a.upper(), name_b.upper()
    if ua.endswith('.PNA') and ub.endswith('.PNA'):
        try:
            return (pna_sig(data_a) == pna_sig(data_b)), 'pna-layers'
        except Exception:
            return False, 'pna-error'
    if ua.endswith('.PNG') and ub.endswith('.PNG'):
        ok, mean, ratio = png_equal(data_a, data_b)
        return ok, 'watermark(mean=%.2f,big=%.1f%%)' % (mean, ratio * 100)
    return False, 'type-mismatch'
