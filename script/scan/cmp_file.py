"""整档级比对：对每个归档计算 (size, sha256)，判定 ORIG / STEAM / PATCH 三者是否逐字节相同。"""
import hashlib
import os

ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'
CN = PATCH + '/Chinese_Localization_Patch'


def sha(p, chunk=1 << 22):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for blk in iter(lambda: fh.read(chunk), b''):
            h.update(blk)
    return h.hexdigest()


def idx(d):
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            out[fn.lower()] = p
    return out


def main():
    dirs = {'ORIG': idx(ORIG), 'STEAM': idx(STEAM), 'PATCH': idx(PATCH), 'CN': idx(CN), 'CN/zh-CN': idx(CN + '/zh-CN'), 'STEAM/zh-CN': idx(STEAM + '/zh-CN')}
    keys = sorted(set().union(*[set(v) for v in dirs.values()]))
    cache = {}

    def info(p):
        if p not in cache:
            st = os.stat(p)
            cache[p] = (st.st_size, sha(p))
        return cache[p]

    print('%-22s %-14s %-14s %-14s %-14s' % ('file', 'ORIG', 'STEAM', 'PATCH', 'CN'))
    for k in keys:
        if not k.endswith(('.arc', '.dll', '.ttf', '.ini')):
            continue
        row = []
        for tag in ('ORIG', 'STEAM', 'PATCH', 'CN'):
            p = dirs[tag].get(k)
            row.append(('%d/%s' % (info(p)[0], info(p)[1][:6])) if p else '-')
        # 标注相同
        print('%-22s %-14s %-14s %-14s %-14s' % (k, row[0], row[1], row[2], row[3]))
    print()
    print('=== 判定 ===')
    for k in keys:
        if not k.endswith('.arc'):
            continue
        tags = [t for t in ('ORIG', 'STEAM', 'PATCH') if k in dirs[t]]
        hs = {t: info(dirs[t][k])[1] for t in tags}
        uniq = set(hs.values())
        if len(uniq) == 1 and len(tags) == 3:
            print('%-22s 三者逐字节相同' % k)
        else:
            eq = []
            ts = list(hs)
            for i in range(len(ts)):
                for j in range(i + 1, len(ts)):
                    if hs[ts[i]] == hs[ts[j]]:
                        eq.append('%s==%s' % (ts[i], ts[j]))
            print('%-22s %s' % (k, ('; '.join(eq)) if eq else '三者互不相同'))


if __name__ == '__main__':
    main()
