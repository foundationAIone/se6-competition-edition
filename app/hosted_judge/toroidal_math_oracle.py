"""Independent stdlib oracle of the explicit candidate contract, not Maxwell physics."""
import math

AXIS=tuple(1/math.sqrt(3) for _ in range(3))
U=(1/math.sqrt(2),-1/math.sqrt(2),0.)
V=(1/math.sqrt(6),1/math.sqrt(6),-2/math.sqrt(6))

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def rotate(x,angle):
    c,s=math.cos(angle),math.sin(angle); ax=cross(AXIS,x); z=dot(AXIS,x)
    return [c*x[i]+s*ax[i]+(1-c)*z*AXIS[i] for i in range(3)]
def tetrahedra(radius=1.):
    # Enumerate cube vertices by sign parity, independently of candidate ordering.
    groups=[[],[]]
    for x in (-1,1):
        for y in (-1,1):
            for z in (-1,1):groups[0 if x*y*z>0 else 1].append([radius*t/math.sqrt(3) for t in (x,y,z)])
    return groups
def field(position,ct,cp,p):
    x,y,z=dot(position,U),dot(position,V),dot(position,AXIS); r2=x*x+y*y
    d=r2-p['major_radius']**2
    g=math.exp(-d*d/p['width_r']**4-z*z/p['width_z']**2)
    # Cartesian expression avoids coordinate singularity or candidate formulas.
    a=2*cp*z*g/p['width_z']**2
    bz=2*cp*g*(1-2*r2*d/p['width_r']**4)
    bx=a*x-ct*g*y; by=a*y+ct*g*x
    return [bx*U[i]+by*V[i]+bz*AXIS[i] for i in range(3)]
def flux(position,cp,p):
    z=dot(position,AXIS); r2=dot(position,U)**2+dot(position,V)**2
    return cp*r2*math.exp(-(r2-p['major_radius']**2)**2/p['width_r']**4-z*z/p['width_z']**2)
def divergence(position,ct,cp,p,h=1e-5):
    out=0.
    for j in range(3):
        a=list(position);b=list(position);a[j]+=h;b[j]-=h
        out+=(field(a,ct,cp,p)[j]-field(b,ct,cp,p)[j])/(2*h)
    return out
def flux_tangent(position,ct,cp,p,h=1e-5):
    grad=[]
    for j in range(3):
        a=list(position);b=list(position);a[j]+=h;b[j]-=h
        grad.append((flux(a,cp,p)-flux(b,cp,p))/(2*h))
    return dot(grad,field(position,ct,cp,p))
