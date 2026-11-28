import pcbnew, sys
D="/usr/share/kicad/footprints/"
for lid in sys.argv[1:]:
    lib,name=lid.split(":")
    fp=pcbnew.FootprintLoad(D+lib+".pretty",name)
    if fp is None: print("MISSING",lid); continue
    print("==",lid)
    for p in fp.Pads():
        pos=p.GetPosition(); s=p.GetSize()
        print("  pad %-4s at (%.3f,%.3f) size %.3fx%.3f %s drill %.2f"%(p.GetNumber(),pos.x/1e6,pos.y/1e6,s.x/1e6,s.y/1e6,p.GetShape(),p.GetDrillSize().x/1e6))
    bb=fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else None
    if bb: print("  courtyard x %.2f..%.2f y %.2f..%.2f"%(bb.GetLeft()/1e6,bb.GetRight()/1e6,bb.GetTop()/1e6,bb.GetBottom()/1e6))
    for lay,nm in ((pcbnew.F_Fab,"fab"),(pcbnew.F_SilkS,"silk")):
        xs=[];ys=[]
        for g in fp.GraphicalItems():
            if g.GetLayer()==lay:
                bb=g.GetBoundingBox(); xs+= [bb.GetLeft()/1e6,bb.GetRight()/1e6]; ys+=[bb.GetTop()/1e6,bb.GetBottom()/1e6]
        if xs: print("  %s x %.2f..%.2f y %.2f..%.2f"%(nm,min(xs),max(xs),min(ys),max(ys)))
