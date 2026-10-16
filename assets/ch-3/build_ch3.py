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
        f.write(b'CH-3 Rainbow-3 approximate exterior model (mm)'.ljust(80, b' '))
        f.write(np.uint32(len(T)).tobytes()); f.write(rec.tobytes())

parts = {}
# ---- fuselage (nose x=0 -> tail x=4400)
xs = np.linspace(0, 4400, 70)
f = np.where(xs < 1300, np.sqrt(np.clip(1-((1300-xs)/1300)**2, 0, 1)), 1.0)
f = np.where(xs > 3000, 1-0.75*((xs-3000)/1400)**1.3, f); f = np.maximum(f, 0.03)
c = np.c_[xs, 0*xs, 0*xs]
parts['01_fuselage'] = mesh(tube(c, Y, Z, 380*f, 340*f, 64))

# ---- wing (high-mounted, span 8000)
def naca(t=0.14, n=30):
    b = (1-np.cos(np.linspace(0, np.pi, n)))/2
    yt = 5*t*(0.2969*np.sqrt(b)-0.1260*b-0.3516*b**2+0.2843*b**3-0.1036*b**4)
    return np.r_[np.c_[b[::-1], yt[::-1]], np.c_[b[1:], -yt[1:]]]
af = naca(); rings = []
for y in np.linspace(-4000, 4000, 25):
    ch = 1100-(1100-550)*abs(y)/4000; le = 1500+60*abs(y)/4000*0
    rings.append(np.c_[le+ch*af[:, 0], np.full(len(af), y), 330+ch*af[:, 1]])
parts['02_wing'] = mesh(np.array(rings))

# ---- twin tail booms
for s, nm in ((-1, 'L'), (1, 'R')):
    xs = np.linspace(1900, 6200, 40); r = np.where(xs < 4800, 95, 95-40*(xs-4800)/1400)
    parts[f'03_boom_{nm}'] = mesh(tube(np.c_[xs, np.full_like(xs, s*1300), np.full_like(xs, 220)], Y, Z, r, r, 32))
    zs = np.linspace(220, 1050, 20); le = 5450+0.30*(zs-220); ch = 6200-le
    parts[f'04_vfin_{nm}'] = mesh(tube(np.c_[(le+6200)/2, np.full_like(zs, s*1300), zs], X, Y, ch/2, np.full_like(zs, 28), 40))
ys = np.linspace(-1700, 1700, 30)
parts['05_hstab'] = mesh(tube(np.c_[np.full_like(ys, 5920), ys, np.full_like(ys, 1000)], X, Z, 260, 30, 40))

# ---- pusher propeller (3 blades) + hub
xs = np.linspace(4400, 4700, 12)
parts['06_prop_hub'] = mesh(tube(np.c_[xs, 0*xs, 0*xs], Y, Z, 110, 110, 32))
rs = np.linspace(110, 1000, 20); p = np.radians(np.linspace(35, 12, 20))
u = np.c_[np.cos(p), np.sin(p), 0*p]; v = np.c_[-np.sin(p), np.cos(p), 0*p]
blade = mesh(tube(np.c_[np.full_like(rs, 4560), 0*rs, rs], u, v, np.linspace(75, 40, 20), np.linspace(12, 5, 20), 24))
for k in range(3): parts[f'07_prop_blade_{k+1}'] = rot_x(blade, 120*k)

# ---- sensor turret
dx = np.linspace(-170, 170, 25); r = np.sqrt(np.maximum(170**2-dx**2, 4))
parts['08_eo_turret'] = mesh(tube(np.c_[900+dx, 0*dx, np.full_like(dx, -300)], Y, Z, r, r, 32))

# ---- landing gear
# def strut(x, y, z0, z1, r=28):
#     zs = np.linspace(z0, z1, 6); return mesh(tube(np.c_[np.full_like(zs, x), np.full_like(zs, y), zs], X, Y, r, r, 20))
# def wheel(x, y, z, R, w):
#     ys = np.linspace(y-w/2, y+w/2, 6); return mesh(tube(np.c_[np.full_like(ys, x), ys, np.full_like(ys, z)], X, Z, R, R, 32))
# parts['09_gear_nose'] = np.r_[strut(800, 0, -250, -850), wheel(800, 0, -850, 140, 90)]
# for s, nm in ((-1, 'L'), (1, 'R')):
#     parts[f'10_gear_main_{nm}'] = np.r_[strut(3000, s*350, -200, -850), wheel(3000, s*350, -900, 170, 110)]

os.makedirs(OUT, exist_ok=True)
for k, T in parts.items(): save_stl('CH3_'+k, T)
save_stl('CH3_00_assembly_all', np.concatenate(list(parts.values())))
print(len(parts), 'parts;', sum(len(t) for t in parts.values()), 'triangles')
np.savez_compressed('/tmp/all.npz', *parts.values())
