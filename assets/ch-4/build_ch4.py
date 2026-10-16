import numpy as np, os
OUT = os.path.dirname(os.path.abspath(__file__))
X, Y, Z = np.eye(3)

def tube(c, u, v, rx, ry, N=48):
    c = np.asarray(c, float); S = len(c)
    u = np.broadcast_to(np.asarray(u, float), (S, 3)); v = np.broadcast_to(np.asarray(v, float), (S, 3))
    rx = np.broadcast_to(np.asarray(rx, float), (S,)); ry = np.broadcast_to(np.asarray(ry, float), (S,))
    t = np.linspace(0, 2*np.pi, N, endpoint=False)
    return (c[:, None, :] + rx[:, None, None]*np.cos(t)[None, :, None]*u[:, None, :]
            + ry[:, None, None]*np.sin(t)[None, :, None]*v[:, None, :])

def mesh(rings):
    S, N, _ = rings.shape; T = []
    for i in range(S-1):
        for j in range(N):
            a, b = rings[i, j], rings[i, (j+1) % N]
            c, d = rings[i+1, (j+1) % N], rings[i+1, j]
            T += [(a, b, c), (a, c, d)]
    for k, first in ((0, True), (S-1, False)):
        r = rings[k]; ctr = r.mean(0)
        for j in range(N):
            p, q = r[j], r[(j+1) % N]
            T.append((ctr, q, p) if first else (ctr, p, q))
    T = np.array(T)
    vol = np.einsum('ij,ij->i', T[:, 0], np.cross(T[:, 1], T[:, 2])).sum()/6
    if vol < 0: T = T[:, ::-1, :]
    return T

def rot_x(T, deg):
    a = np.radians(deg); R = np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
    return T @ R.T

def save_stl(name, T):
    n = np.cross(T[:,1]-T[:,0], T[:,2]-T[:,0]); l = np.linalg.norm(n, axis=1, keepdims=True); n = n/np.where(l == 0, 1, l)
    rec = np.zeros(len(T), dtype=[('n','<f4',3),('v','<f4',(3,3)),('a','<u2')])
    rec['n'] = n; rec['v'] = T
    with open(os.path.join(OUT, name+'.stl'), 'wb') as f:
        f.write(b'CH-4 Rainbow-4 approximate exterior model (mm)'.ljust(80, b' '))
        f.write(np.uint32(len(T)).tobytes()); f.write(rec.tobytes())

parts = {}
# ---- fuselage (nose x=0 -> tail x=7400)
xs = np.linspace(0, 7400, 100)
f = np.where(xs < 1600, np.sqrt(np.clip(1-((1600-xs)/1600)**2, 0, 1)), 1.0)
tail = np.clip((xs-4800)/2600, 0, 1)
f = np.where(xs > 4800, 1-0.72*tail**1.3, f); f = np.maximum(f, 0.03)
parts['01_fuselage'] = mesh(tube(np.c_[xs, 0*xs, 0*xs], Y, Z, 400*f, 430*f, 64))

# ---- dorsal satcom dome on the nose
dx = np.linspace(-900, 900, 30); r = np.sqrt(np.maximum(1-(dx/900)**2, 0.0004))
parts['02_satcom_dome'] = mesh(tube(np.c_[1500+dx, 0*dx, np.full_like(dx, 360)], Y, Z, 380*r, 330*r, 48))

# ---- wing (mid/high, span 18000)
def naca(t=0.14, n=30):
    b = (1-np.cos(np.linspace(0, np.pi, n)))/2
    yt = 5*t*(0.2969*np.sqrt(b)-0.1260*b-0.3516*b**2+0.2843*b**3-0.1036*b**4)
    return np.r_[np.c_[b[::-1], yt[::-1]], np.c_[b[1:], -yt[1:]]]
af = naca(); rings = []
for y in np.linspace(-9000, 9000, 37):
    ch = 1300-(1300-650)*abs(y)/9000
    rings.append(np.c_[2700+ch*af[:, 0], np.full(len(af), y), 200+ch*af[:, 1]])
parts['03_wing'] = mesh(np.array(rings))

# ---- inverted-V tail
a = np.radians(40); ts = np.linspace(0, 1700, 24)
for s, nm in ((-1, 'L'), (1, 'R')):
    d = np.array([0, s*np.cos(a), -np.sin(a)]); v = np.array([0, np.sin(a), s*np.cos(a)])
    le = 6300+0.25*ts; ch = 900-400*ts/1700
    cen = np.array([0, s*150, 60]) + ts[:, None]*d
    cen[:, 0] = le+ch/2
    parts[f'04_vtail_{nm}'] = mesh(tube(cen, X, v, ch/2, np.full_like(ts, 26), 40))

# ---- pusher propeller (3 blades) + hub
xs = np.linspace(7400, 7750, 12)
parts['05_prop_hub'] = mesh(tube(np.c_[xs, 0*xs, 0*xs], Y, Z, 120, 120, 32))
rs = np.linspace(120, 1100, 22); p = np.radians(np.linspace(35, 12, 22))
u = np.c_[np.cos(p), np.sin(p), 0*p]; v = np.c_[-np.sin(p), np.cos(p), 0*p]
blade = mesh(tube(np.c_[np.full_like(rs, 7570), 0*rs, rs], u, v, np.linspace(85, 45, 22), np.linspace(13, 5, 22), 24))
for k in range(3): parts[f'06_prop_blade_{k+1}'] = rot_x(blade, 120*k)

# ---- EO/IR turret
dx = np.linspace(-240, 240, 25); r = np.sqrt(np.maximum(240**2-dx**2, 4))
parts['07_eo_turret'] = mesh(tube(np.c_[1500+dx, 0*dx, np.full_like(dx, -400)], Y, Z, r, r, 32))

# ---- landing gear
# def strut(x, y, z0, z1, r=32):
#     zs = np.linspace(z0, z1, 6); return mesh(tube(np.c_[np.full_like(zs, x), np.full_like(zs, y), zs], X, Y, r, r, 20))
# def wheel(x, y, z, R, w):
#     ys = np.linspace(y-w/2, y+w/2, 6); return mesh(tube(np.c_[np.full_like(ys, x), ys, np.full_like(ys, z)], X, Z, R, R, 32))
# parts['08_gear_nose'] = np.r_[strut(1300, 0, -300, -1050), wheel(1300, 0, -1050, 160, 100)]
# for s, nm in ((-1, 'L'), (1, 'R')):
#     parts[f'09_gear_main_{nm}'] = np.r_[strut(4000, s*450, -250, -1050), wheel(4000, s*450, -1050, 200, 130)]

os.makedirs(OUT, exist_ok=True)
for k, T in parts.items(): save_stl('CH4_'+k, T)
save_stl('CH4_00_assembly_all', np.concatenate(list(parts.values())))
print(len(parts), 'parts;', sum(len(t) for t in parts.values()), 'triangles')
np.savez_compressed('/tmp/all4.npz', *parts.values())
