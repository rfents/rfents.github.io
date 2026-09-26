import math, random
random.seed(5)
W,H=1584,396
GLOW='filter="url(#glowS)"'
G="#D4AF37"; G2="#f3dc8a"; C="#7fd6ff"
out=[]
def a(s): out.append(s)

# ---------- globe (orthographic) ----------
CX,CY,R=1265,205,165
lon0=math.radians(42); lat0=math.radians(12)
def proj(lat,lon,r=R):
    la,lo=math.radians(lat),math.radians(lon)
    x=math.cos(la)*math.sin(lo-lon0)
    y=math.cos(lat0)*math.sin(la)-math.sin(lat0)*math.cos(la)*math.cos(lo-lon0)
    z=math.sin(lat0)*math.sin(la)+math.cos(lat0)*math.cos(la)*math.cos(lo-lon0)
    return CX+x*r, CY-y*r, z
def path(pts):
    return "M"+" L".join(f"{x:.1f},{y:.1f}" for x,y in pts)
def curve(samples, front_op, back_op, width):
    seg=[];cur=None
    for x,y,z in samples:
        f=z>0
        if cur is None or f!=cur:
            if seg: 
                a(f'<path d="{path(seg)}" fill="none" stroke="{G}" stroke-opacity="{front_op if cur else back_op}" stroke-width="{width}"/>')
                seg=seg[-1:]
            cur=f
        seg.append((x,y))
    if seg: a(f'<path d="{path(seg)}" fill="none" stroke="{G}" stroke-opacity="{front_op if cur else back_op}" stroke-width="{width}"/>')

a(f'<circle cx="{CX}" cy="{CY}" r="{R+40}" fill="url(#halo)"/>')
a(f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="url(#sphere)" stroke="{G}" stroke-opacity=".55" stroke-width="1.2"/>')
for lat in range(-75,90,15):
    curve([proj(lat,l) for l in range(0,361,3)],.14,0,.7)
for lon in range(0,360,15):
    curve([proj(l,lon) for l in range(-90,91,3)],.14,0,.7)

# dotted "land" hint: random dots on the front hemisphere, denser near continents is overkill; use fine dot field
import json
for lat,lon in json.load(open("land_dots.json")):
    x,y,z=proj(lat,lon)
    if z>0.02: a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{.7+.9*z:.2f}" fill="{G}" fill-opacity="{.15+.55*z:.2f}"/>')

cities={"TNR":(-18.9,47.5),"PAR":(48.9,2.3),"DXB":(25.2,55.3),"JNB":(-26.2,28.0),"SIN":(1.35,103.8),
        "BOM":(19.1,72.9),"LON":(51.5,-0.1),"NBO":(-1.3,36.8),"CAI":(30.0,31.2),"FRA":(50.1,8.7),"MRU":(-20.2,57.5),"HKG":(22.3,114.2)}
links=[("TNR","PAR"),("TNR","DXB"),("TNR","JNB"),("TNR","SIN"),("LON","DXB"),("NBO","BOM"),("CAI","JNB")]
def slerp(p,q,t):
    la1,lo1=map(math.radians,p); la2,lo2=map(math.radians,q)
    v1=(math.cos(la1)*math.cos(lo1),math.cos(la1)*math.sin(lo1),math.sin(la1))
    v2=(math.cos(la2)*math.cos(lo2),math.cos(la2)*math.sin(lo2),math.sin(la2))
    d=math.acos(max(-1,min(1,sum(i*j for i,j in zip(v1,v2)))))
    s1=math.sin((1-t)*d)/math.sin(d); s2=math.sin(t*d)/math.sin(d)
    v=[s1*i+s2*j for i,j in zip(v1,v2)]
    return math.degrees(math.asin(v[2])),math.degrees(math.atan2(v[1],v[0]))
for i,(s,e) in enumerate(links):
    pts=[]
    for k in range(41):
        t=k/40; la,lo=slerp(cities[s],cities[e],t)
        pts.append(proj(la,lo,R*(1+.12*math.sin(math.pi*t))))
    if all(z>-0.05 for _,_,z in pts):
        d=path([(x,y) for x,y,_ in pts])
        a(f'<path d="{d}" fill="none" stroke="{G2}" stroke-width="1.3" stroke-opacity=".9" filter="url(#glow)"/>')
        # travelling packet
        x,y,_=pts[[12,20,28,16,24][i%5]]
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#fff" filter="url(#glowS)"/>')
for n,(la,lo) in cities.items():
    x,y,z=proj(la,lo)
    if z>0:
        big = n=="TNR"
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{9 if big else 6}" fill="none" stroke="{G2}" stroke-opacity=".5"/>')
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3.4 if big else 2.4}" fill="{G2}" filter="url(#glowS)"/>')

# orbit ring (front half drawn over globe)
def ring_pts(rx,ry,t0,t1):
    th=math.radians(-14); pts=[]
    for k in range(61):
        t=t0+(t1-t0)*k/60; x=rx*math.cos(t); y=ry*math.sin(t)
        pts.append((CX+x*math.cos(th)-y*math.sin(th), CY+x*math.sin(th)+y*math.cos(th)))
    return path(pts)
for rx,ry,op,dash in ((R+62,44,.45,' stroke-dasharray="2 6"'),(R+98,68,.2,'')):
    a(f'<path d="{ring_pts(rx,ry,0,math.pi)}" fill="none" stroke="{G}" stroke-opacity="{op}"{dash}/>')
    out.insert(0,f'<path d="{ring_pts(rx,ry,math.pi,2*math.pi)}" fill="none" stroke="{G}" stroke-opacity="{op*.6:.2f}"{dash}/>')
x,y=[float(v) for v in ring_pts(R+62,44,2.3,2.3).split(" L")[0][1:].split(",")]
a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#fff" filter="url(#glowS)"/>')
globe="\n".join(out); out.clear()

# ---------- server racks (perspective-ish, center) ----------
def rack(x,y,w,h,units,seed):
    rnd=random.Random(seed)
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="url(#rackfill)" stroke="{G}" stroke-opacity=".55"/>')
    a(f'<rect x="{x+4}" y="{y+4}" width="{w-8}" height="6" fill="{G}" fill-opacity=".15"/>')
    uh=(h-24)/units
    for u in range(units):
        yy=y+14+u*uh
        a(f'<rect x="{x+7}" y="{yy:.1f}" width="{w-14}" height="{uh-4:.1f}" rx="1.5" fill="#101010" stroke="{G}" stroke-opacity=".22"/>')
        # vents
        for vx in range(int(x+30),int(x+w-12),4):
            a(f'<rect x="{vx}" y="{yy+uh/2-3.5:.1f}" width="1.6" height="5" fill="{G}" fill-opacity=".18"/>')
        for k in range(3):
            on=rnd.random()<.72
            col = C if (k==2 and rnd.random()<.35) else G2
            a(f'<circle cx="{x+13+k*6}" cy="{yy+uh/2-1:.1f}" r="1.7" fill="{col if on else "#3a3015"}" {GLOW if on else ""}/>')
racks=[(560,70,120,270,11,1),(700,40,140,320,13,2),(860,70,120,270,11,3)]
for r in racks: rack(*r)
# floor reflection glow under racks
a(f'<ellipse cx="770" cy="365" rx="260" ry="18" fill="url(#floorglow)"/>')
rackssvg="\n".join(out); out.clear()

# ---------- circuit traces from racks to globe & to left network ----------
traces=[
 [(980,120),(1030,120),(1060,90),(1105,90)],
 [(980,205),(1040,205),(1070,235),(1100,235)],
 [(980,300),(1020,300),(1050,330),(1150,330)],
 [(560,110),(505,110),(470,75),(380,75)],
 [(560,200),(480,200),(450,230),(330,230)],
 [(560,300),(500,300),(470,270),(390,270)],
]
for i,t in enumerate(traces):
    a(f'<path d="{path(t)}" fill="none" stroke="{G}" stroke-opacity=".55" stroke-width="1.3"/>')
    for (x,y) in (t[0],t[-1]): a(f'<circle cx="{x}" cy="{y}" r="3" fill="#0a0a0a" stroke="{G2}" stroke-width="1.3"/>')
    mx=(t[1][0]+t[2][0])/2; my=(t[1][1]+t[2][1])/2
    a(f'<circle cx="{mx}" cy="{my}" r="2.4" fill="#fff" filter="url(#glowS)"/>')
tracesvg="\n".join(out); out.clear()

# ---------- left topology mesh (fades toward left, where profile photo sits) ----------
nodes=[(random.uniform(300,520),random.uniform(20,376)) for _ in range(26)]
edges=set()
for i,(x,y) in enumerate(nodes):
    d=sorted(range(len(nodes)),key=lambda j:(nodes[j][0]-x)**2+(nodes[j][1]-y)**2)
    for j in d[1:4]: edges.add(tuple(sorted((i,j))))
for i,j in edges:
    (x1,y1),(x2,y2)=nodes[i],nodes[j]
    op=.12+.3*(min(x1,x2)-300)/220
    a(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{G}" stroke-opacity="{op:.2f}"/>')
for k,(x,y) in enumerate(nodes):
    op=.3+.6*(x-300)/220
    if k%6==0:
        a(f'<rect x="{x-5:.0f}" y="{y-5:.0f}" width="10" height="10" rx="2" fill="#0a0a0a" stroke="{G2}" stroke-opacity="{op:.2f}" transform="rotate(45 {x:.0f} {y:.0f})"/>')
    else:
        a(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.2" fill="{G}" fill-opacity="{op:.2f}"/>')
meshsvg="\n".join(out); out.clear()

# ---------- faint terminal texture ----------
log=["$ ssh admin@core-sw01","BGP 10.0.0.2 Established","$ systemctl status nginx","  active (running)","$ ping -c4 gw01",
     "  0% packet loss","$ ansible-playbook site.yml","  ok=42 failed=0","fw: ACCEPT tcp/443","$ uptime","  up 412 days","backup: 100% OK","monitoring: all green"]
term="".join(f'<tspan x="36" dy="{0 if i==0 else 27}">{l}</tspan>' for i,l in enumerate(log))
termsvg=f'<text x="36" y="34" font-family="JetBrains Mono" font-size="12.5" fill="{G}" fill-opacity=".2">{term}</text>'

svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
 <radialGradient id="bg" cx="72%" cy="50%" r="75%"><stop offset="0" stop-color="#1d1707"/><stop offset=".45" stop-color="#0e0d0a"/><stop offset="1" stop-color="#070707"/></radialGradient>
 <radialGradient id="halo"><stop offset=".78" stop-color="{G}" stop-opacity=".18"/><stop offset="1" stop-color="{G}" stop-opacity="0"/></radialGradient>
 <radialGradient id="sphere" cx="38%" cy="32%" r="75%"><stop offset="0" stop-color="#2a220c"/><stop offset=".6" stop-color="#110f08"/><stop offset="1" stop-color="#060606"/></radialGradient>
 <radialGradient id="floorglow"><stop offset="0" stop-color="{G}" stop-opacity=".28"/><stop offset="1" stop-color="{G}" stop-opacity="0"/></radialGradient>
 <linearGradient id="rackfill" x1="0" x2="1"><stop offset="0" stop-color="#1b1b1b"/><stop offset=".5" stop-color="#121212"/><stop offset="1" stop-color="#0b0b0b"/></linearGradient>
 <linearGradient id="edge" x1="0" x2="1"><stop offset="0" stop-color="{G}" stop-opacity="0"/><stop offset=".25" stop-color="#8B4513"/><stop offset=".6" stop-color="{G}"/><stop offset="1" stop-color="#B8860B"/></linearGradient>
 <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse"><path d="M44 0H0V44" fill="none" stroke="{G}" stroke-opacity=".05"/></pattern>
 <filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
 <filter id="glowS" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<rect width="{W}" height="{H}" fill="url(#grid)"/>
{termsvg}
{meshsvg}
{tracesvg}
{rackssvg}
{globe}
<rect y="{H-3}" width="{W}" height="3" fill="url(#edge)"/>
</svg>'''
html=f'''<!doctype html><html><head><meta charset="utf-8"><link href="fonts.css" rel="stylesheet">
<style>*{{margin:0}}html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#070707}}</style></head><body>{svg}</body></html>'''
open("cover.html","w").write(html)
