import re, json, sys
ATTR=re.compile(r'\s*([\w-]+)="([^"]*)"')
def parse_extinf(line):
    m=re.match(r'#EXTINF:\s*(-?\d+)', line); pos=m.end(); attrs={}
    while True:
        a=ATTR.match(line,pos)
        if not a: break
        attrs[a.group(1)]=a.group(2); pos=a.end()
    rest=line[pos:]
    title=rest.split(',',1)[1] if ',' in rest else rest
    return m.group(1), attrs, title.strip()
def parse(path):
    out=[]; cur=None
    for line in open(path, encoding='utf-8', errors='replace'):
        line=line.rstrip('\r\n')
        if line.startswith('#EXTINF'):
            d,a,t=parse_extinf(line); cur={'dur':d,'attrs':a,'title':t}
        elif line.startswith('#EXTGRP'):
            if cur: cur['extgrp']=line[8:]
        elif line.startswith('#') or not line.strip(): pass
        else:
            if cur: cur['url']=line.strip(); out.append(cur); cur=None
    return out
if __name__=='__main__':
    ch=parse(sys.argv[1]); json.dump(ch, open(sys.argv[2],'w'))
    print(len(ch), sum('group-title' not in c['attrs'] for c in ch))
