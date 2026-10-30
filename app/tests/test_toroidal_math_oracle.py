import math
from hosted_judge import toroidal_math_oracle as o

P={'major_radius':1.,'width_r':.75,'width_z':.75}

def test_geometry():
    groups=o.tetrahedra()
    assert len({tuple(v) for g in groups for v in g})==8
    for g in groups:
        assert all(abs(sum(v[i] for v in g))<1e-15 for i in range(3))
        distances=[math.dist(a,b) for i,a in enumerate(g) for b in g[i+1:]]
        assert max(distances)-min(distances)<1e-15
    projected=[(o.dot(v,o.U),o.dot(v,o.V)) for g in groups for v in g]
    assert sum(math.hypot(*v)<1e-12 for v in projected)==2
    assert len([v for v in projected if math.hypot(*v)>1e-12])==6

def test_rodrigues_orientation():
    assert math.dist(o.rotate(o.U,math.pi/2),o.V)<1e-15
    assert math.dist(o.rotate(o.rotate([.3,-.4,.5],.7),-.7),[.3,-.4,.5])<1e-15

def test_axis_and_zero():
    assert o.field([0,0,0],0,0,P)==[0,0,0]
    assert all(math.isfinite(v) for v in o.field([0,0,0],1,1,P))
    assert math.dist(o.field([0,0,0],0,1,P),[2*math.exp(-1/.75**4)*v for v in o.AXIS])<1e-15

def test_toroidal_circle():
    for angle in [0,.4,1.5,math.pi,2*math.pi]:
        x=[math.cos(angle)*u+math.sin(angle)*v+.2*a for u,v,a in zip(o.U,o.V,o.AXIS)]
        b=o.field(x,1,0,P)
        radial=[math.cos(angle)*u+math.sin(angle)*v for u,v in zip(o.U,o.V)]
        assert abs(o.dot(b,radial))<1e-14 and abs(o.dot(b,o.AXIS))<1e-14
        assert math.sqrt(o.dot(b,b))>0

def test_divergence_and_flux_tangent():
    for x in ([0,0,0],[.4,.2,-.7],[1.1,-.3,.6],[-.4,.8,.3]):
        assert abs(o.divergence(x,.7,-.2,P))<1e-7
        assert abs(o.flux_tangent(x,.7,-.2,P))<1e-8
