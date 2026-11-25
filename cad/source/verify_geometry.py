"""Check STEP geometry and eight cliff-sensor centre rays. Uses CadQuery 2.7."""
from math import sin,cos,radians
from pathlib import Path
import cadquery as cq
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Dir,gp_Lin,gp_Pnt
from build_concept import bounds, CAD, FACE_Z, BUMPER_PROJECTION, PITCH

assembly=cq.Assembly.importStep(str(CAD/'Rad_Roomba_D.step'))
head=cq.Assembly.importStep(str(CAD/'Detector_Head_D.step'))
print('Vehicle and independent head bounds in mm')
print(bounds(assembly.toCompound()),bounds(head.toCompound()))
probes={}
for node in assembly.objects.values():
    if node.obj is not None:
        shape=node.obj.moved(node.loc)
        if not shape.isValid(): raise ValueError(node.name+' has invalid geometry')
        item=IntCurvesFace_ShapeIntersector()
        item.Load(shape.wrapped,.00001)
        probes[node.name]=item
print('Nominal cliff-sensor centre rays to a flat floor')
for sign,x,z,angle,xd,yd in [(1,90,92,17,60,46),(-1,-156,82,22,-122,48)]:
    theta=radians(angle)
    for side in (-1,1):
        rays=[((x,23*side,z),(sign*cos(theta),0,-sin(theta)),z/sin(theta)),
              ((xd,yd*side,31),(0,0,-1),31.)]
        for start,axis,reach in rays:
            line=gp_Lin(gp_Pnt(*start),gp_Dir(*axis))
            hits=[]
            for name,obj in probes.items():
                obj.Perform(line,.25,reach-.1)
                if obj.NbPnt(): hits.append(name)
            end=tuple(round(s+reach*d,1) for s,d in zip(start,axis))
            print(f'{start} to {end} | hits {hits}')
            if hits: raise ValueError('Cliff centre ray obstructed')
pieces={node.name:node.obj.moved(node.loc) for node in head.objects.values() if node.obj is not None}
for boxname in ['Key_socket','Peripheral_frame_and_interlane_ribs','Removable_top_and_heat_spreader']:
    shell=pieces[boxname]
    for name,s in pieces.items():
        if not name.startswith(('S0_','S1_','S2_','S3_')):continue
        volume=shell.intersect(s).Volume()
        if volume>0.002:raise ValueError(f'{name} overlaps {boxname} by {volume} mm³')
print('All optical lanes clear the three principal housing solids.')

rails=[n for n in pieces if n.startswith(('Leading_contact_rail','Side_contact_rail','Wing_tip_contact_return'))]
assert len(rails)==5
for name in rails:
    assert abs(bounds(pieces[name])[2]-(FACE_Z-BUMPER_PROJECTION))<.02,name
for i in range(4):
    foil=bounds(pieces[f'S{i}_Entrance_foil'])
    assert abs(foil[2]-FACE_Z)<.02 and abs((foil[1]+foil[4])/2-(1.5-i)*PITCH)<.02
    for name in rails:
        assert pieces[name].intersect(pieces[f'S{i}_Entrance_foil']).Volume()<.0001
assert abs(bounds(head.toCompound())[2]-(FACE_Z-BUMPER_PROJECTION))<.02
print(f'Four entrance films at {FACE_Z:.1f} mm. Five perimeter contact solids at {FACE_Z-BUMPER_PROJECTION:.1f} mm. Nominal solid checks only.')
