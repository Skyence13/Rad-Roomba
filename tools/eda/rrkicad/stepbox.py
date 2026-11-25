"""Minimal STEP (AP214) writer for a rectangular block - used as a component
envelope when no real 3D model exists (the stock KiCad container ships none)."""

_HEADER = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('rrkicad component envelope (box)'),'2;1');
FILE_NAME('%(name)s.step','%(date)sT00:00:00',('rrkicad'),(''),'rrkicad','rrkicad','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
"""


def box_step(name, x0, y0, z0, x1, y1, z1, date="1970-01-01"):
    """Return STEP text for an axis-aligned solid box (mm)."""
    out = []
    n = [0]

    def e(s):
        n[0] += 1
        out.append("#%d = %s;" % (n[0], s))
        return n[0]

    def f(v):
        return ("%.6f" % v).rstrip("0").rstrip(".") + ("." if float(v) == int(v) else "")

    def pt(p):
        return e("CARTESIAN_POINT('',(%s,%s,%s))" % (f(p[0]), f(p[1]), f(p[2])))

    def dr(d):
        return e("DIRECTION('',(%s,%s,%s))" % (f(d[0]), f(d[1]), f(d[2])))
    ctx_app = e("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    e("APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#%d)" % ctx_app)
    pctx = e("PRODUCT_CONTEXT('',#%d,'mechanical')" % ctx_app)
    prod = e("PRODUCT('%s','%s','',(#%d))" % (name, name, pctx))
    form = e("PRODUCT_DEFINITION_FORMATION('','',#%d)" % prod)
    dctx = e("PRODUCT_DEFINITION_CONTEXT('part definition',#%d,'design')" % ctx_app)
    pdef = e("PRODUCT_DEFINITION('design','',#%d,#%d)" % (form, dctx))
    pds = e("PRODUCT_DEFINITION_SHAPE('','',#%d)" % pdef)
    e("PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#%d))" % prod)
    lu = e("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    au = e("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    su = e("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = e("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#%d,'distance_accuracy_value','confusion accuracy')" % lu)
    gctx = e("( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#%d)) "
             "GLOBAL_UNIT_ASSIGNED_CONTEXT((#%d,#%d,#%d)) REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') )"
             % (unc, lu, au, su))
    X, Y, Z = (x0, x1), (y0, y1), (z0, z1)
    P = {}
    V = {}
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                P[(i, j, k)] = (X[i], Y[j], Z[k])
                V[(i, j, k)] = e("VERTEX_POINT('',#%d)" % pt(P[(i, j, k)]))
    edges = {}

    def edge(a, b):
        """Edge curve between corners a and b; returns (id, same_direction)."""
        if (a, b) in edges:
            return edges[(a, b)], True
        if (b, a) in edges:
            return edges[(b, a)], False
        pa, pb = P[a], P[b]
        d = tuple(pb[i] - pa[i] for i in range(3))
        ln = sum(c * c for c in d) ** 0.5
        vec = e("VECTOR('',#%d,%s)" % (dr(tuple(c / ln for c in d)), f(ln)))
        line = e("LINE('',#%d,#%d)" % (pt(pa), vec))
        edges[(a, b)] = e("EDGE_CURVE('',#%d,#%d,#%d,.T.)" % (V[a], V[b], line))
        return edges[(a, b)], True
    # faces: corner loops counter-clockwise seen from outside, with outward normal / reference dir
    faces_def = [
        ([(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], (0, 0, -1), (1, 0, 0)),   # bottom
        ([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], (0, 0, 1), (1, 0, 0)),    # top
        ([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], (0, -1, 0), (1, 0, 0)),   # front (y0)
        ([(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], (0, 1, 0), (1, 0, 0)),    # back (y1)
        ([(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)], (-1, 0, 0), (0, 1, 0)),   # left (x0)
        ([(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], (1, 0, 0), (0, 1, 0)),    # right (x1)
    ]
    faces = []
    for corners, normal, ref in faces_def:
        oes = []
        for i in range(4):
            eid, same = edge(corners[i], corners[(i + 1) % 4])
            oes.append(e("ORIENTED_EDGE('',*,*,#%d,%s)" % (eid, ".T." if same else ".F.")))
        loop = e("EDGE_LOOP('',(%s))" % ",".join("#%d" % o for o in oes))
        bound = e("FACE_OUTER_BOUND('',#%d,.T.)" % loop)
        ax = e("AXIS2_PLACEMENT_3D('',#%d,#%d,#%d)" % (pt(P[corners[0]]), dr(normal), dr(ref)))
        plane = e("PLANE('',#%d)" % ax)
        faces.append(e("ADVANCED_FACE('',(#%d),#%d,.T.)" % (bound, plane)))
    shell = e("CLOSED_SHELL('',(%s))" % ",".join("#%d" % x for x in faces))
    solid = e("MANIFOLD_SOLID_BREP('%s',#%d)" % (name, shell))
    ax0 = e("AXIS2_PLACEMENT_3D('',#%d,#%d,#%d)" % (pt((0, 0, 0)), dr((0, 0, 1)), dr((1, 0, 0))))
    rep = e("ADVANCED_BREP_SHAPE_REPRESENTATION('',(#%d,#%d),#%d)" % (ax0, solid, gctx))
    e("SHAPE_DEFINITION_REPRESENTATION(#%d,#%d)" % (pds, rep))
    return _HEADER % {"name": name, "date": date} + "\n".join(out) + "\nENDSEC;\nEND-ISO-10303-21;\n"
