"""分析 Rio.arc 成员名分组：按路线前缀归类，输出三版本对照。"""
import json
import re

def names(f):
    return [m['name'] for m in json.load(open(f, encoding='utf-8'))]

s = names('steam_rio.json')
o = names('orig_rio.json')
p = names('patch_rio.json')

def base(n):
    return re.sub(r'_E(?=\.ws2$)', '', n)

# 按前缀分组
def group(lst):
    g = {}
    for n in lst:
        m = re.match(r'^([A-Za-z]+)_', n)
        k = m.group(1).upper() if m else '(other)'
        g.setdefault(k, []).append(n)
    return g

gs, go, gp = group(s), group(o), group(p)
allk = sorted(set(gs) | set(go) | set(gp))
print('%-8s %-6s %-6s %-6s' % ('prefix', 'ORIG', 'STEAM', 'PATCH'))
for k in allk:
    print('%-8s %-6d %-6d %-6d' % (k, len(go.get(k, [])), len(gs.get(k, [])), len(gp.get(k, []))))

print()
print('--- STEAM story scripts (by prefix) ---')
for k in allk:
    if k == '(other)':
        continue
    print('%s: %s' % (k, ' '.join(sorted(base(x) for x in gs.get(k, [])))))
print()
print('--- ORIG story scripts ---')
for k in allk:
    if k == '(other)':
        continue
    print('%s: %s' % (k, ' '.join(sorted(go.get(k, [])))))
print()
print('--- PATCH: names not in STEAM (added) ---')
print(sorted(set(x.lower() for x in p) - set(x.lower() for x in s)))
print('--- STEAM: names not in PATCH (removed by patch) ---')
print(sorted(set(x.lower() for x in s) - set(x.lower() for x in p)))
print()
print('--- ORIG names (base) not present as base in STEAM ---')
sb = set(base(x).lower() for x in s)
print(sorted(x for x in o if x.lower() not in sb))
print('--- STEAM names (base) not present in ORIG ---')
ob = set(x.lower() for x in o)
print(sorted(base(x) for x in s if base(x).lower() not in ob))
