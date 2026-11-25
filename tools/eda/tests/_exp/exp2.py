import pcbnew, os
pcbnew.KIID.SeedGenerator(1234)
p = os.path.abspath("exp.kicad_pcb")
b = pcbnew.LoadBoard(p)
for f in list(b.GetFootprints()): b.Remove(f)
def MM(x,y): return pcbnew.VECTOR2I_MM(x,y)
# outline
pts=[(90,90),(120,90),(120,110),(90,110)]
for i in range(4):
    s=pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(MM(*pts[i])); s.SetEnd(MM(*pts[(i+1)%4])); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(pcbnew.FromMM(0.1)); b.Add(s)
import itertools
k=0
for i,(x,y,rot) in enumerate([(95,95,0),(110,95,90),(100,105,0),(115,105,90)]):
    fp = pcbnew.FootprintLoad("/usr/share/kicad/footprints/Resistor_SMD.pretty", "R_0402_1005Metric")
    fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD","R_0402_1005Metric")); fp.SetReference("R%d"%(i+1)); fp.SetValue("10k"); b.Add(fp)
    fp.SetPosition(MM(x,y)); fp.SetOrientationDegrees(rot)
    for pad in fp.Pads():
        pad.SetNet(b.FindNet("GND" if pad.GetNumber()=="1" else "SIG"))
# preroute
t=pcbnew.PCB_TRACK(b); t.SetStart(MM(100,100)); t.SetEnd(MM(105,100)); t.SetLayer(pcbnew.F_Cu); t.SetWidth(pcbnew.FromMM(0.3)); t.SetNet(b.FindNet("SIG")); t.SetLocked(True); b.Add(t)
# zone on In1 GND
z=pcbnew.ZONE(b); z.SetLayer(pcbnew.In1_Cu); z.SetNet(b.FindNet("GND")); 
ol=z.Outline(); ol.NewOutline()
for q in pts: ol.Append(pcbnew.FromMM(q[0]),pcbnew.FromMM(q[1]))
z.SetZoneName("GND_PLANE"); b.Add(z)
b.BuildConnectivity()
print("dsn", pcbnew.ExportSpecctraDSN(b, os.path.abspath("exp.dsn")))
pcbnew.SaveBoard(p, b, True)
import inspect
print(pcbnew.SaveBoard.__doc__)
