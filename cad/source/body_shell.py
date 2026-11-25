"""Rad Roomba B shell, in mm. Front is positive X and the floor is z = 0."""
import math
import cadquery as cq

SHELL="#D7DFE1"
CHARCOAL="#252E33"
SLATE="#444F56"
GASKET="#202A30"
SILVER="#A5B2B7"
AMBER="#D99A48"
GLASS="#344D59"

# z, tail, nose, nominal half-breadth. Periodic sections give a clean printable skin.
UPPER=[(56.6,-154.5,111.1,110.0),(59,-155.0,112.0,110.5),
       (66,-154.2,111.6,110.1),(77,-151.1,108.5,106.9),
       (90,-144.1,102.9,99.9),(100,-132.4,93.0,88.4),
       (108,-116,78.5,75.2),(114,-93,56.0,56.5),
       (117.0,-68,35.8,39.4),(117.6,-60,30,34.9)]
LOWER=[(33,-133,90,84),(34,-141,96,90),(38,-148.5,102.1,97.3),
       (46,-153.5,108.5,106.1),(52,-154.8,110.5,109.3),
       (55.2,-154.4,111.0,109.9)]

def ringwire(z,tail,nose,breadth):
    cen=(tail+nose)*.5
    length=(nose-tail)*.5
    pts=[]
    for i in range(24):
        th=2*math.pi*i/24
        c,s=math.cos(th),math.sin(th)
        # Gently broad aft shoulders and a narrower forward transition.
        x=cen+length*math.copysign(abs(c)**.925,c)
        y=breadth*math.copysign(abs(s)**.925,s)*(1-.185*c)
        pts.append(cq.Vector(x,y,z))
    return cq.Wire.assembleEdges([cq.Edge.makeSpline(pts,periodic=True)])

def loft(rows):
    return cq.Solid.makeLoft([ringwire(*s) for s in rows],False)

def cyl(r,h,base,axis=(0,0,1)):
    return cq.Solid.makeCylinder(r,h,cq.Vector(*base),cq.Vector(*axis))

def compound(items):
    return cq.Compound.makeCompound(items)

def capsule(plane,w,h,r,t):
    # XY profile in the selected mount plane, with four full-radius shoulders.
    wire=(cq.Workplane(plane).sketch().rect(w,h).vertices().fillet(r).finalize())
    return wire.extrude(t).val()

def level_capsule(x,y,z,length,width,rad,height):
    return capsule(cq.Plane(origin=(x,y,z)),length,width,rad,height)

def oblique_plane(sign,p_y=0,offset=0):
    x,z,theta=(100,92,17) if sign==1 else (-146,82,22)
    th=math.radians(theta)
    d=(sign*math.cos(th),0,-math.sin(th))
    pos=(x+offset*d[0],p_y,z+offset*d[2])
    return cq.Plane(origin=pos,xDir=(0,1,0),normal=d)

def rounded_wire(plane,w,h,r):
    a,b=w/2,h/2
    k=r*math.sqrt(.5)
    return (cq.Workplane(plane).moveTo(-a+r,-b).lineTo(a-r,-b)
            .threePointArc((a-r+k,-b+r-k),(a,-b+r)).lineTo(a,b-r)
            .threePointArc((a-r+k,b-r+k),(a-r,b)).lineTo(-a+r,b)
            .threePointArc((-a+r-k,b-r+k),(-a,b-r)).lineTo(-a,-b+r)
            .threePointArc((-a+r-k,-b+r-k),(-a+r,-b)).close().val())

def optical_saddle(sign):
    # This continuous colour-matched breech fills the full back of the bezel.
    # It tapers into the curved outer skin and is hollowed with the rest of the lid.
    rows=[(-32,61,5,2),(-24,68,11,4),(-14,74,20,6.2),
          (-6,74,22,7),(.35,70.6,18.8,6.4)]
    return cq.Solid.makeLoft([rounded_wire(oblique_plane(sign,offset=d),w,h,r)
                              for d,w,h,r in rows],False)

def wheel_cutters():
    return [cyl(55.8,38,(10,sgn*95.7,52),(0,sgn,0)) for sgn in (-1,1)]

def clear(s,cutters):
    for tool in cutters:
        s=s.cut(tool)
    return s

def add_shell(add):
    upper_outer=loft(UPPER)
    # The underside of the top cover is open. Wall thickness is conceptual.
    inner_rows=[(54,-150.0,107.4,106.9),(63,-150.0,107.5,106.2),
                (75,-146.0,104.5,102.3),(87,-138.8,99,95.5),
                (97,-126.0,87.0,82.7),(105,-107,71,68),
                (110,-86,50,50),(113,-61,30,34)]
    upper=upper_outer.fuse(optical_saddle(1),optical_saddle(-1)).cut(loft(inner_rows))
    wells=wheel_cutters()
    # The handwell has a removable washable liner and moulded flush transverse grip.
    pocket=level_capsule(-84,0,40.5,94,130,18,120)
    # A shallow visible faceplate pocket stops at its back wall. Only the individual
    # beam channels pass through the skin; this preserves the saddle's side webs.
    pod_holes=[]
    for d in (-1,1):
        pod_holes.append(capsule(oblique_plane(d,offset=-1.2),65.0,14.2,5,37))
        for yy in (-23,23):
            pod_holes.append(capsule(oblique_plane(d,yy,offset=-34),13,8.4,3.5,36))
    button_pocket=cyl(16.2,64,(-14,-64,97.0))
    upper=clear(upper,[*wells,pocket,button_pocket,*pod_holes])
    add("upper_fairing",upper,SHELL)
    lower=loft(LOWER)
    inner_lo=loft([(37,-133,87,82),(43,-140,94,89),
                   (51,-147,102,101),(58,-150,106,106)])
    lower=clear(lower.cut(inner_lo),[*wells,pocket])
    # A dark sealing gasket is a narrow separate strip at the true shell split.
    gasket=loft([(55.18,-154.3,110.96,109.8),(56.62,-154.43,111.07,109.97)])
    gasket=gasket.cut(loft([(54.5,-150,107,106),(57.2,-150,107,106)]))
    add("perimeter_split_seal",clear(gasket,[*wells,pocket]),GASKET)
    # Downward sensors sit flush below the skid pan with an unobstructed axial bore.
    positions=[(70,46),(70,-46),(-112,48),(-112,-48)]
    tube_cuts=[cyl(9.6,20,(x,y,25)) for x,y in positions]
    add("lower_bumper_hull",clear(lower,tube_cuts),CHARCOAL)
    sockets=[]; windows=[]; optics=[]
    for x,y in positions:
        sock=cyl(9.4,5,(x,y,30.85)).cut(cyl(6.1,5.5,(x,y,30.6)))
        sockets.append(sock)
        windows.append(cyl(5.85,1.1,(x,y,31.05)))
        optics.append(cyl(2.7,.35,(x,y,31.0)))
    add("downward_sensor_socket_rings",compound(sockets),SLATE)
    add("downward_sensor_windows",compound(windows),GASKET)
    add("downward_sensor_optics",compound(optics),GLASS)

    # Upper edge follows the lofted skin, without a cap or blind flange covering it.
    lining_outer=level_capsule(-84,0,42.7,94,130,18,110)
    lining_inner=level_capsule(-84,0,45,88.4,124.4,15.2,111)
    recess=lining_outer.cut(lining_inner).intersect(upper_outer.fuse(loft(LOWER)))
    # Explicit part beneath the hull seam joins any integral well strips across it.
    liner_bridge=lining_outer.cut(lining_inner).intersect(
        loft([(54.9,-154.4,111,110),(57.2,-154.5,111,110)]))
    recess=recess.fuse(liner_bridge)
    add("handwell_liner",recess,SLATE)
    # Bridge cross-section is flat topped and undercut for four gloved fingers.
    # It dives into side cheeks that return carrying loads to the chassis.
    grip=(cq.Workplane("XZ",origin=(-84,67,94.5)).sketch().rect(25,22)
          .vertices().fillet(7.5).finalize().extrude(134).val())
    add("recessed_transverse_grip",grip,CHARCOAL)
    brackets=[]
    for side in (-1,1):
        brackets.append(level_capsule(-84,side*65.3,68.5,28,7,3.1,28))
    add("grip_anchor_cheeks",compound(brackets),SLATE)

    # The bezel is one tidy transverse feature per end with two protected channels.
    for sign,longname in ((1,"forward"),(-1,"aft")):
        surround=capsule(oblique_plane(sign,offset=-1.2),64.92,14.12,4.94,1.75)
        aperture=capsule(oblique_plane(sign,offset=-2),61.8,11.7,4.0,3.2)
        bezel=surround.cut(aperture)
        add(longname+"_sensor_shroud",bezel,SLATE)
        back=capsule(oblique_plane(sign,offset=-1.2),61.74,11.64,3.97,1.10)
        for y in (-23,23):
            back=back.cut(capsule(oblique_plane(sign,y,-11),13,8.3,3.5,12))
        add(longname+"_sensor_carrier",back,GASKET)
        lenses=[]
        for y in (-23,23):
            lenses.append(capsule(oblique_plane(sign,y,-2.8),12.7,8.05,3.3,2.8))
        add(longname+"_oblique_optics",compound(lenses),GLASS)

    # Deliberately low-profile red local stop, captivated in a recessed escutcheon.
    add("stop_switch_cup",cyl(16.0,6,(-14,-64,97)),SLATE)
    add("stop_switch_collar",cyl(14.5,2.6,(-14,-64,103)),AMBER)
    add("stop_switch_black_stem",cyl(8.7,6.2,(-14,-64,105.6)),CHARCOAL)
    stop=(cq.Workplane("XZ").moveTo(0,111.5).lineTo(9.9,111.5)
          .lineTo(12.0,114.0).lineTo(12.0,117.0)
          .threePointArc((11.55,118.55),(10.1,119.0)).lineTo(0,119).close()
          .revolve(360,(0,0),(0,1)).val().translate((-14,-64,0)))
    add("stop_button",stop,"#C95146")

    # Low panoramic scan head. The shrouded central mount and optical belt are
    # rotationally symmetric, leaving all azimuths clear of the handle and switch.
    x=-10
    add("lidar_shouldered_base",level_capsule(x,0,114.0,68,63,15,7.8),SHELL)
    add("lidar_lower_bezel",cyl(27.5,4.2,(x,0,121.7)),SLATE)
    prof=[(0,125.8),(26.8,125.8),(26.8,128.3),(25.5,130.1),
          (25.5,144.7),(26.8,146.8),(26.8,149.0),(0,149.0)]
    window=(cq.Workplane("XZ").polyline(prof).close().revolve(360,(0,0),(0,1))
            .val().translate((x,0,0)))
    add("lidar_panoramic_window",window,GLASS)
    add("lidar_upper_gasket",cyl(27.4,1.4,(x,0,148.9)),GASKET)
    cap=level_capsule(x,0,150.2,59,55,12,8.3)
    cap=cq.Workplane(obj=cap).edges(">Z").fillet(2.0).val()
    add("lidar_cap",cap,SHELL)
    add("lidar_status_indicator",level_capsule(x+17,0,158.47,3.1,12,1.4,.52),AMBER)
