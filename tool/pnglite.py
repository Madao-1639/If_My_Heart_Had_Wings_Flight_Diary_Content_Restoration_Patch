"""纯标准库 PNG 解码与像素比对（8-bit，colortype 0/2/3/4/6）。

用途：PNA 子图逐像素比对（L3 同名判定、立绘记录映射与层内修复）。
不依赖第三方包（本机离线）。`decode_png` 与 `script/build/build_l3.py` 原实现同源，
抽出到 `tool/` 供构建脚本与闸共用。
"""
import struct
import zlib


def decode_png(png):
    """→ (w, h, channels, pixels bytes)。colortype 3（调色板）展开为 RGB。"""
    if png[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not png')
    pos, w, h, bd, ct, idat, plte = 8, None, None, None, None, b'', None
    while pos < len(png):
        ln = struct.unpack_from('>I', png, pos)[0]
        typ = png[pos + 4:pos + 8]
        chunk = png[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            w, h, bd, ct = struct.unpack_from('>IIBB', chunk, 0)
        elif typ == b'PLTE':
            plte = chunk
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
        pos += 12 + ln
    if bd != 8:
        raise ValueError('bitdepth %s unsupported' % bd)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    rp = 0
    for y in range(h):
        f = raw[rp]
        rp += 1
        line = bytearray(raw[rp:rp + stride])
        rp += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + (a + prev[i]) // 2) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif f != 0:
            raise ValueError('filter %s' % f)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    if ct == 3:
        rgb = bytearray(w * h * 3)
        for i, idx in enumerate(out):
            rgb[i * 3:i * 3 + 3] = plte[idx * 3:idx * 3 + 3]
        return w, h, 3, bytes(rgb)
    return w, h, ch, bytes(out)


def to_gray(w, h, ch, pix):
    """转 8-bit 灰度 bytes（长度 w*h）。"""
    if ch == 1:
        return pix
    g = bytearray(w * h)
    if ch == 2:
        for i in range(w * h):
            g[i] = pix[i * 2]
    elif ch == 3:
        for i in range(w * h):
            j = i * 3
            g[i] = (pix[j] * 299 + pix[j + 1] * 587 + pix[j + 2] * 114) // 1000
    else:
        for i in range(w * h):
            j = i * 4
            g[i] = (pix[j] * 299 + pix[j + 1] * 587 + pix[j + 2] * 114) // 1000
    return bytes(g)


def png_gray(data):
    return to_gray(*decode_png(data))


def to_rgba(w, h, ch, pix):
    """统一为 RGBA bytes（长度 4*w*h），缺 alpha 补 255。"""
    if ch == 4:
        return pix
    out = bytearray(w * h * 4)
    if ch == 3:
        for i in range(w * h):
            out[i * 4:i * 4 + 3] = pix[i * 3:i * 3 + 3]
            out[i * 4 + 3] = 255
    elif ch == 1:
        for i in range(w * h):
            v = pix[i]
            out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = v
            out[i * 4 + 3] = 255
    elif ch == 2:
        for i in range(w * h):
            v = pix[i * 2]
            a = pix[i * 2 + 1]
            out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = v
            out[i * 4 + 3] = a
    else:
        raise ValueError('channels %d' % ch)
    return bytes(out)


def rgba_of(png):
    """PNG bytes → (w, h, rgba bytes)。"""
    w, h, ch, pix = decode_png(png)
    return w, h, to_rgba(w, h, ch, pix)


def diff_rgba(a, b, big_t=16):
    """两张 **同尺寸** RGBA bytes → (mean, big_ratio)。

    mean＝逐字节绝对差均值（0–255）；big_ratio＝差值 > big_t 的字节占比。
    """
    if len(a) != len(b):
        raise ValueError('length mismatch %d != %d' % (len(a), len(b)))
    n = len(a)
    s = big = 0
    for i in range(n):
        d = a[i] - b[i]
        if d < 0:
            d = -d
        s += d
        if d > big_t:
            big += 1
    return s / n, big / n
