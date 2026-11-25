"""Rad Roomba B running gear, keyed neck and removable survey bar (mm)."""
from math import cos, radians, sin, sqrt

import cadquery as cq


SHELL = "#d7dfe1"
NECK = "#bfcbd0"
RUBBER = "#242a2d"
TIRE_DETAIL = "#30373a"
DEEP = "#283237"
GRAPHITE = "#39454b"
GUNMETAL = "#58666e"
STEEL = "#a8b4b7"
AMBER = "#da9745"
INSERT = "#45545b"


def cylinder(r, h, p, d=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, h, cq.Vector(*p), cq.Vector(*d))


def round_rect_wire(plane, width, height, r):
    a, b, k = width / 2, height / 2, sqrt(0.5)
    return (cq.Workplane(plane)
            .moveTo(-a+r, -b).lineTo(a-r, -b)
            .threePointArc((a-r+r*k, -b+r-r*k), (a, -b+r))
            .lineTo(a, b-r).threePointArc((a-r+r*k, b-r+r*k), (a-r, b))
            .lineTo(-a+r, b).threePointArc((-a+r-r*k, b-r+r*k), (-a, b-r))
            .lineTo(-a, -b+r).threePointArc((-a+r-r*k, -b+r-r*k), (-a+r, -b))
            .close().val())


def rounded(x, y, z, length, width, height, corner):
    plane = cq.Plane(origin=(x,y,z), xDir=(1,0,0), normal=(0,0,1))
    wire = round_rect_wire(plane, length, width, corner)
    return cq.Solid.extrudeLinear(wire, [], cq.Vector(0,0,height))


def neck_loft(stations):
    wires = []
    for x, width, bottom, top, r in stations:
        plane = cq.Plane(origin=(x,0,(top+bottom)/2), xDir=(0,1,0), normal=(1,0,0))
        wires.append(round_rect_wire(plane, width, top-bottom, r))
    return cq.Solid.makeLoft(wires, False)


def screw(radius, height, point, direction=(0,0,1)):
    cap = cylinder(radius, height, point, direction)
    origin = tuple(a + b*height*0.38 for a,b in zip(point,direction))
    socket = (cq.Workplane(cq.Plane(origin=origin, normal=direction))
              .polygon(6, radius*0.93).extrude(height).val())
    return cap.cut(socket)


def tire_shape():
    # Three-point arcs form the tread crown and the soft, rounded shoulder.
    tire = (cq.Workplane("XY").moveTo(31.5,-10.2).lineTo(32.8,-11.5)
            .threePointArc((37,-12.27),(41,-12.5))
            .threePointArc((44.3,-12.15),(47.6,-11.05))
            .threePointArc((50.3,-9.35),(51.6,-7.1))
            .threePointArc((52,0),(51.6,7.1))
            .threePointArc((50.3,9.35),(47.6,11.05))
            .threePointArc((44.3,12.15),(41,12.5))
            .threePointArc((37,12.27),(32.8,11.5))
            .lineTo(31.5,10.2).close().revolve(360,(0,0),(0,1)).val())
    cuts = []
    for i in range(28):
        for side in (-1,1):
            groove = (cq.Workplane("XY").box(1.4,11,5.5).val()
                      .rotate((0,0,0),(0,0,1),side*22)
                      .translate((0,side*6.15,50.8))
                      .rotate((0,0,0),(0,1,0),(i+side*0.14)*360/28))
            cuts.append(groove)
    return tire.cut(cq.Compound.makeCompound(cuts))


def wheels(add):
    tire = tire_shape()
    for tag, s in (("L",1),("R",-1)):
        group = "Wheel_" + tag + "_"
        x, y, z = 10, s*110, 52
        def ax(r, h, offset):
            return cylinder(r,h,(x, y+s*offset, z),(0,s,0))
        add(group+"Tire",tire.translate((x,y,z)),RUBBER)
        # A light witness ring blends into the sidewall at the tire bead.
        ring = ax(35.0,0.3,11.79).cut(ax(34.55,0.65,11.62))
        add(group+"Molded_Bead_Line",ring,TIRE_DETAIL)
        add(group+"Hub_Drum",ax(32.5,19.8,-11.0),DEEP)
        # Dished cast face with five elongated radial pockets and recessed lug circle.
        profile = [(0,7.8),(32.25,7.8),(32.25,10.6),(30.3,11.25),(26.8,10.7),
                   (23,8.95),(16,8.75),(12,10.05),(0,10.05)]
        face = cq.Workplane("XY").polyline(profile).close().revolve(360,(0,0),(0,1)).val()
        if s < 0:
            face = face.rotate((0,0,0),(1,0,0),180)
        face = face.translate((x,y,z))
        holes, bolts = [], []
        for i in range(5):
            angle = radians(90 + i*72)
            cx, cz = x + 22.1*cos(angle), z + 22.1*sin(angle)
            lp = cq.Plane(origin=(cx, y+s*7.9, cz),xDir=(cos(angle),0,sin(angle)),normal=(0,s,0))
            slot = cq.Solid.extrudeLinear(round_rect_wire(lp,8.2,4.5,2),[],cq.Vector(0,s*5,0))
            holes.append(slot)
            bx,bz = x+11.0*cos(angle), z+11.0*sin(angle)
            bolts.append(screw(1.77,1.25,(bx,y+s*9.55,bz),(0,s,0)))
        add(group+"Machined_Hub_Face",face.cut(cq.Compound.makeCompound(holes)),GRAPHITE)
        add(group+"Hub_Fasteners",cq.Compound.makeCompound(bolts),STEEL)
        add(group+"Satin_Axle_Cap",ax(6.4,1.4,10.05),GUNMETAL)
        add(group+"Motor_Axle",ax(6.5,18,-28.2),GUNMETAL)
        plate = rounded(10,s*85.7,37.4,33,10,25,3)
        add(group+"Bearing_Mount",plate.cut(ax(6.8,21,-31.5)),GRAPHITE)


def rear_caster(add):
    add("Caster_Seat", rounded(-100,0,34,32,36,3.7,5),GUNMETAL)
    add("Caster_Swivel",cylinder(12.5,2.3,(-100,0,31.9)),STEEL)
    add("Caster_Crown",rounded(-96,0,27.8,17,28,4.3,4),GRAPHITE)
    blade_profile = [(-92,30),(-109,30),(-120.7,22),(-123,16),
                     (-121,11.6),(-115,10.8),(-111,13.4),(-108,18.4),(-92,25.6)]
    for tag,sy in (("L",1),("R",-1)):
        blade=(cq.Workplane("XZ", origin=(0,sy*12.5+1.5,0))
               .polyline(blade_profile).close().extrude(3).val())
        blade=blade.cut(cylinder(3.05,5,(-116,sy*12.5-2.5,15.5),(0,1,0)))
        add("Caster_"+tag+"_Fork",blade,GUNMETAL)
    tire = (cq.Workplane("XY").moveTo(6,-8).lineTo(12.5,-8)
            .threePointArc((14.5,-6.4),(15.1,-4.6))
            .threePointArc((15.5,0),(15.1,4.6))
            .threePointArc((14.5,6.4),(12.5,8))
            .lineTo(6,8).close().revolve(360,(0,0),(0,1)).val().translate((-116,0,15.5)))
    add("Caster_Rolling_Tire",tire,RUBBER)
    hub=cylinder(6,16.2,(-116,-8.1,15.5),(0,1,0)).cut(
        cylinder(3.07,17,(-116,-8.5,15.5),(0,1,0)))
    add("Caster_Wheel_Hub",hub,GRAPHITE)
    add("Caster_Pin",cylinder(3,28.5,(-116,-14.25,15.5),(0,1,0)),STEEL)


def underframe(add):
    plate = rounded(-18,0,33,228,157,4,20)
    # Pull in the forward shoulders to keep the hidden tray inside the body silhouette.
    side=[(-140,86),(27,86),(45,77),(65,65),(74,59),(82,53),(92,42),(100,36)]
    outline=side+[(x,-y) for x,y in reversed(side)]
    trim=cq.Workplane("XY",origin=(0,0,32)).polyline(outline).close().extrude(7).val()
    plate=plate.intersect(trim)
    for x,ys in ((70,46),(-112,48)):
        for sy in (-1,1):
            plate = plate.cut(cylinder(10.5,9,(x,sy*ys,30)))
    for tag,s in (("L",1),("R",-1)):
        inner_clearance=cq.Solid.makeBox(99,124.4,30,cq.Vector(-133.5,-62.2,44.8))
        rail=rounded(-24,s*62,36,167,9,14,2).cut(inner_clearance)
        # A bolted pedestal lands directly beneath each moulded grip cheek.
        foot=rounded(-84,s*65.1,50,26.5,6.0,3.5,1.6)
        tower=rounded(-84,s*65.5,53.5,23.5,5.8,15,1.6)
        bolts=[]
        for px in (-92,-76):
            p=(px,s*65.3,35.7)
            hole=cylinder(1.65,35,p)
            rail=rail.cut(hole)
            foot=foot.cut(hole)
            tower=tower.cut(hole)
            # Service bores under the load rails give hex-key access from below.
            plate=plate.cut(cylinder(3.0,5,(px,s*65.3,32.7)))
            shank=cylinder(1.48,34.1,(px,s*65.3,36.02))
            cap=screw(2.6,1.35,(px,s*65.3,36.03),(0,0,-1))
            bolts.extend([shank,cap])
        add("Subframe_"+tag+"_Load_Rail",rail,GUNMETAL)
        add("Subframe_"+tag+"_Carry_Seat",foot,GRAPHITE)
        add("Subframe_"+tag+"_Carry_Post",tower,GUNMETAL)
        add("Subframe_"+tag+"_Carry_Bolts",cq.Compound.makeCompound(bolts),STEEL)
    add("Subframe_Optical_Clearance_Tray",plate,GRAPHITE)
    add("Subframe_Nose_Spar",rounded(82,0,34.8,70,39,13,4),GUNMETAL)


def key_shape(start, stop, fit=0):
    # Unequal upper corner bevels both orient the shoe and resist twisting.
    yz = [(-22-fit,26-fit),(22+fit,26-fit),(22+fit,33+fit),
          (16+fit,38+fit),(-19-fit,38+fit),(-22-fit,35+fit)]
    return (cq.Workplane("YZ",origin=(start,0,0))
            .polyline(yz).close().extrude(stop-start).val())


def add_fixed_neck(add):
    fixed = neck_loft([(77,105,35,63,9),(90,104,32.5,59.5,9),(112,96,28,50.5,8),
                       (134,85,24.5,44.0,6),(148.2,80,23.2,42.5,5.6)])
    lower_clip = cq.Solid.makeBox(160,200,28,cq.Vector(50,-100,0))
    recess = key_shape(128,150,0.18)
    add('Neck_Fixed_Shroud',fixed.cut(lower_clip).cut(recess),NECK)
    add('Neck_Fixed_Lower_Skid',fixed.intersect(lower_clip).cut(recess),GRAPHITE)
    add('Neck_Asymmetric_Keyed_Tongue',key_shape(127.5,181.8).cut(
        cylinder(2.55,166,(154.3,-83,31.8),(0,1,0))),STEEL)


def add_body_chassis(add):
    underframe(add)
    wheels(add)
    rear_caster(add)
    add_fixed_neck(add)
