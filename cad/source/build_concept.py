"""Rev D modular scan-head envelope, in millimetres. Requires CadQuery 2.7.

The preceding body STEP is the neutral geometry reference included in the project.
Head and changed platform components are defined parametrically below. Its origin
remains under the axle; the Rev B STEP used an origin 10 mm behind the axle.
"""
import argparse
import json
from pathlib import Path

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

HERE = Path(__file__).resolve().parent
CAD = HERE.parent
B_REFERENCE = CAD.parent / 'reference' / 'revision_B' / 'Rad_Roomba_Body_Concept_B.step'
PITCH = 87.5
ACTIVE_Y = 80.0
ACTIVE_X = 100.0
OPTICS_X = 204.0
FACE_Z = 10.0  # entrance-foil elevation above nominal floor
BUMPER_PROJECTION = 3.0  # 5 mm is a separate guarded trial setting
STACK_LIFT = 4.0  # optics/tray raised from C; chassis mating key remains fixed
WIDTH = 350.0
HEAD_REAR = 138.8
HEAD_FRONT = 265.0
TEAL = '#278981'
REF = '#e2a84e'
DARK = '#24393e'
SILVER = '#b5c6ca'
LID = '#e0e7e7'
GLASS = '#71acbb'
FILTER = '#655b7b'
HEAT = '#b67346'


def block(x, y, z, length, width, height, r=0):
    """Centred in x and y; z is bottom elevation."""
    work = cq.Workplane('XY', origin=(x,y,z)).box(length,width,height,centered=(True,True,False))
    if r:
        work = work.edges('|Z').fillet(r)
    return work.val()


def cyl(r, length, pos, axis=(0,0,1)):
    return cq.Solid.makeCylinder(r,length,cq.Vector(*pos),cq.Vector(*axis))


def bounds(shape):
    bb=Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped,bb,False,False)
    return [round(float(i),3) for i in bb.Get()]


def make_model(body_file):
    project = cq.Assembly(name='Rad_Roomba_D')
    platform = cq.Assembly(name='Platform')
    head = cq.Assembly(name='Detector_head')
    parts=[]
    def add(group, name, shape, color, family):
        if not shape.isValid() or not shape.Solids():
            raise ValueError(f'Empty or invalid envelope: {name}')
        group.add(shape,name=name,color=cq.Color(color) if isinstance(color,str) else color)
        parts.append((family,name,shape,color))

    # Keep the user-approved shell, support tray and optical geometry from Rev B.
    if body_file is None:
        from body_chassis import add_body_chassis
        from body_shell import add_shell
        old=cq.Assembly(name='Parametric_body')
        def register(name, shape, color):
            old.add(shape,name=name,color=cq.Color(color))
        add_body_chassis(register)
        add_shell(register)
    else:
        old = cq.Assembly.importStep(str(body_file))
    for node in old.objects.values():
        name=node.name
        if node.obj is None or name.startswith(('Head_','Neck_Transverse','Neck_Flush','Neck_Pin')):
            continue
        solid=node.obj.moved(node.loc).translate((-10,0,0))
        if name=='Neck_Asymmetric_Keyed_Tongue':
            solid=solid.cut(block(202,0,0,100,180,90))
        color=node.color if node.color else cq.Color('#697b82')
        add(platform,name,solid,color,'platform')
    # Mount ring and electrical landing are assembly allowances, not vendor footprints.
    collar=block(146.3,0,23.2,15.0,79.5,18.8,3.0)
    key_clear=block(146.6,0,25.5,16.0,45.0,13.0)
    collar=collar.cut(key_clear)
    lock=cyl(2.6,100,(144.3,-50,31.8),(0,1,0))
    collar=collar.cut(lock)
    for y in (-PITCH/2,PITCH/2):
        collar=collar.cut(block(152.0,y,19.0,5.5,14.0,11.0))
    add(head,'Key_socket',collar,DARK,'housing')
    add(head,'Captive_pin_envelope',cyl(2.3,83.0,(144.3,-41.5,31.8),(0,1,0)),SILVER,'housing')
    # Perimeter ring and ribs leave all four rectangular windows open.
    rear=143.0
    front=261.0
    core=(rear+front)/2
    length=front-rear
    lanes=[(1.5-i)*PITCH for i in range(4)]
    apertures=[block(OPTICS_X,y,4.0,ACTIVE_X,ACTIVE_Y,40) for y in lanes]
    tray=block(core,0,FACE_Z-0.4,length,WIDTH-5.0,23.0,3)
    for aperture in apertures:
        tray=tray.cut(aperture)
    # Cavities for the guides' readout behind each active plane.
    for y in lanes:
        tray=tray.cut(block(151.25,y,6.0,5.6,15.0,30.0))
    tray=tray.cut(collar).cut(key_clear).cut(lock)
    add(head,'Peripheral_frame_and_interlane_ribs',tray,'#344c51','housing')
    seam=block(core,0,32.6,length-.8,WIDTH-5.8,1.0,3).cut(block(core,0,32.4,length-5.0,WIDTH-9.0,2.0,1.0)).cut(collar)
    add(head,'Service_cover_seal',seam,'#298b82','housing')
    cover=block(core,0,33.6,length-.8,WIDTH-5.8,5.4,3)
    cover=cq.Workplane(obj=cover).edges('>Z').fillet(1.2).val().cut(collar)
    add(head,'Removable_top_and_heat_spreader',cover,LID,'housing')
    # Three independently compliant zones. Fixed tray sidewalls stop at y=±172.5.
    # Nominal unloaded envelopes only; guide stems, switches and overtravel need detailing.
    bottom=FACE_Z-BUMPER_PROJECTION
    add(head,'Leading_contact_rail',block(263.2,0,bottom,3.6,350.0,13.0,1.4),DARK,'housing')
    for sign,side in [(-1,'right'),(1,'left')]:
        side_rail=block(202.0,174.25*sign,bottom,117.8,1.5,13.0,.65)
        wing=block(142.3,136.0*sign,bottom,1.4,76.5,13.0,.6)
        # Rear returns guard wing tips on local lateral/reverse contact.
        add(head,'Side_contact_rail_'+side,side_rail,DARK,'housing')
        add(head,'Wing_tip_contact_return_'+side,wing,DARK,'housing')
        add(head,'Front_rail_link_'+side,block(261.15,sign*108,17.0,1.1,10.0,2.6),SILVER,'housing')
    # Two candidate platform bearing lands on either side of the retained key. Their upper faces
    # sit against the underside of the socket. Dimensioned registration hardware requires FEA/test.
    for sign,side in [(-1,'R'),(1,'L')]:
        foot=block(139.5,sign*31,21.7,8.8,7.5,1.5,.5)
        add(platform,'Receiver_bearing_land_'+side,foot,SILVER,'platform')
    # Actual face-film thickness/material, particle filter and Z stack require testing.
    for i,y in enumerate(lanes):
        label=f'S{i}'
        def tile(suffix,z,thickness,color):
            shape=block(OPTICS_X,y,z,ACTIVE_X,ACTIVE_Y,thickness)
            add(head,f'{label}_{suffix}',shape,color,suffix)
        # A sparse example bridge establishes a guard envelope. Its shadow and
        # membrane support require qualification with the selected source.
        guard=[block(OPTICS_X+d,y,FACE_Z-.36,.7,ACTIVE_Y,.22) for d in (-30,0,30)]
        add(head,label+'_Guard_webs',cq.Compound.makeCompound(guard),'#475c61','Guard')
        tile('Entrance_foil',FACE_Z,.05,'#d4e2e3')
        tile('Floor_screen',7.00+STACK_LIFT,.25,TEAL)
        tile('Floor_guide',7.25+STACK_LIFT,5.0,GLASS)
        tile('Particle_stop_optical_barrier_allowance',14.0+STACK_LIFT,2.0,FILTER)
        tile('Reference_tile_envelope',19.0+STACK_LIFT,.5,REF)
        tile('Reference_guide',19.5+STACK_LIFT,5.0,'#c6ab72')
        for z,plane in ((7.55+STACK_LIFT,'Floor'),(19.8+STACK_LIFT,'Reference')):
            sensor=block(153.45,y,z,1.1,7.0,4.3)
            pcb=block(152.15,y,z-.3,1.5,13,5.0)
            add(head,label+'_'+plane+'_SiPM',sensor,'#314f48','SiPM')
            add(head,label+'_'+plane+'_carrier',pcb,'#75a08a','carrier')
        tile('Heater_zone_reserved',27.95+STACK_LIFT,.22,HEAT)
    for side in (-1,1):
        # Rearward body-contact tabs are a design allowance; switches and travel TBD.
        add(platform,'Rear_contact_pad_'+str(side),block(-150.0,side*44,55.6,5.0,27,8,1.5),DARK,'platform')
    project.add(platform)
    project.add(head)
    return project,head,parts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,default=B_REFERENCE)
    p.add_argument('--out',type=Path,default=CAD)
    p.add_argument('--rebuild-body',action='store_true',help='regenerate rounded body from editable native source instead of the baseline STEP')
    p.add_argument('--check',action='store_true',help='re-import the exported solids and compare extents')
    p.add_argument('--scene',type=Path,help='optional intermediate polygon data for rendering')
    p.add_argument('--cached-body-mesh',type=Path,help='optional Rev B mesh cache for faster preview')
    args=p.parse_args()
    order,head,parts=make_model(None if args.rebuild_body else args.base)
    args.out.mkdir(exist_ok=True,parents=True)
    for stem,group in [('Rad_Roomba_D',order),('Detector_Head_D',head)]:
        path=args.out/(stem+'.step')
        group.export(str(path))
        box=bounds(group.toCompound())
        print(stem,len(group.toCompound().Solids()),box,flush=True)
        if args.check:
            check=cq.Assembly.importStep(str(path)).toCompound()
            assert len(check.Solids())==len(group.toCompound().Solids())
            assert max(abs(a-b) for a,b in zip(bounds(check),box))<.02
    if args.scene:
        quick={} if args.cached_body_mesh is None else {v['name']:v for v in json.loads(args.cached_body_mesh.read_text())}
        meshes=[]
        for family,name,shape,color in parts:
            if name in quick and name!='Neck_Asymmetric_Keyed_Tongue':
                piece=quick[name]
                verts=[(x-10,y,z) for x,y,z in piece['verts']]
                faces=piece['faces']
            else:
                pts,faces=shape.tessellate(.2,.16)
                verts=[(round(a.x,3),round(a.y,3),round(a.z,3)) for a in pts]
            if not isinstance(color,str):
                vals=color.toTuple()[:3]
                color='#'+''.join(f'{round(255*c):02x}' for c in vals)
            meshes.append(dict(family=family,name=name,color=color,verts=verts,faces=faces))
        args.scene.write_text(json.dumps(meshes,separators=(',',':')))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
