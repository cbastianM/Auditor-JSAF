import streamlit as st
import json
import math
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import Counter

st.set_page_config(page_title="JSAF Auditor", page_icon="🏗️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
code, pre, .stCode { font-family: 'JetBrains Mono', monospace !important; }
.metric-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #0f3460; border-radius: 12px; padding: 1rem; text-align: center;
}
.metric-card h3 { color: #e94560; margin: 0; font-size: 1.8rem; font-weight: 700; }
.metric-card p { color: #a8a8b3; margin: 0.2rem 0 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }
.section-header {
    background: linear-gradient(90deg, #e94560 0%, #0f3460 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-weight: 700; font-size: 1.5rem; margin-bottom: 0.5rem;
}
.group-label { color: #a8a8b3; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 2px; margin: 0.8rem 0 0.3rem; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

MATERIAL_TYPE  = {0:"Other",1:"Concrete",2:"Steel",3:"Timber",4:"Aluminium",5:"Masonry"}
CS_SHAPE       = {0:"Circle",1:"Rectangle",6:"I Section",9:"T Section",14:"U Section",16:"Pipe"}
CS_TYPE        = {0:"Parametric",1:"Manufactured",2:"Compound",3:"General"}
CURVE_TYPE     = {0:"General",1:"Beam",2:"Column",10:"SlabRib"}
SURFACE_TYPE   = {0:"Plate",1:"Wall",2:"Shell",3:"Ribbed Slab"}
SUPPORT_TRANS  = {0:"Free",1:"Rigid",2:"Flexible",3:"Comp. Only",4:"Tension Only"}
SUPPORT_ROT    = {0:"Free",1:"Rigid",2:"Flexible"}
ACTION_TYPE_LC = {0:"Permanent",1:"Variable",2:"Accidental"}
LOAD_TYPE      = {0:"Self Weight",1:"Others",2:"Prestress",3:"Dynamic",4:"Static",5:"Temperature",6:"Wind",7:"Snow",8:"Maintenance",9:"Fire",10:"Moving",11:"Seismic",12:"Standard"}
COMB_CATEGORY  = {0:"Undefined",1:"ULS",2:"SLS",3:"ALS",4:"National Std"}
DISTRIBUTION   = {0:"Uniform",1:"Trapezoidal"}
PLOT_COLORS    = ["#e94560","#4a9eff","#51cf66","#ffd43b","#cc5de8","#ff922b"]

SURFACE_LCS_TYPE = {0:"Default",1:"Eje X local = vector",2:"Eje Y local = vector"}
CURVE_LCS_TYPE   = {0:"Eje Y = dir. vector",1:"Eje Z = dir. vector",2:"Eje Y apunta al punto",3:"Eje Z apunta al punto"}

COMPS_1D   = ['aN','aVy','aVz','aMx','aMy','aMz']
COMPS_MESH = ['amx','amy','amxy','avx','avy','anx','any','anxy']

LCS_OK_COLOR   = "#51cf66"
LCS_BAD_COLOR  = "#e94560"
LCS_NONE_COLOR = "#748ffc"
ANGLE_TOL_DEG  = 5.0


# ─────────────────────────────────────────────────
# ALGEBRA VECTORIAL
# ─────────────────────────────────────────────────
def _mag(v):   return math.sqrt(v[0]**2+v[1]**2+v[2]**2)
def _sub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def _dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _norm(v):
    n=_mag(v)
    return (v[0]/n,v[1]/n,v[2]/n) if n>1e-12 else (0.0,0.0,0.0)
def _angle_deg(a,b):
    d=max(-1.0,min(1.0,_dot(_norm(a),_norm(b))))
    return math.degrees(math.acos(d))


# ─────────────────────────────────────────────────
# CALCULO LCS DESDE GEOMETRIA
# ─────────────────────────────────────────────────
def _default_bar_y(x_local):
    ref=(1.0,0.0,0.0) if abs(x_local[2])>0.9 else (0.0,0.0,1.0)
    d=_dot(ref,x_local)
    y_raw=(ref[0]-d*x_local[0],ref[1]-d*x_local[1],ref[2]-d*x_local[2])
    return _norm(y_raw) if _mag(y_raw)>1e-9 else (0.0,1.0,0.0)


def compute_surface_lcs(surf, nm):
    pts=[nm.get(nid) for nid in surf.get("Nodes",[])]
    pts=[p for p in pts if p]
    if len(pts)<3: return None
    p0=(pts[0]["X"],pts[0]["Y"],pts[0]["Z"])
    p1=(pts[1]["X"],pts[1]["Y"],pts[1]["Z"])
    p2=(pts[2]["X"],pts[2]["Y"],pts[2]["Z"])
    v01=_sub(p1,p0); v02=_sub(p2,p0)
    z_local=_norm(_cross(v01,v02))
    lcs_type=surf.get("LCS",0) or 0
    vx=surf.get("LCSX",0) or 0; vy=surf.get("LCSY",0) or 0; vz=surf.get("LCSZ",0) or 0
    has_vec=_mag((vx,vy,vz))>1e-9
    if lcs_type==1 and has_vec:
        raw=_norm((vx,vy,vz)); d=_dot(raw,z_local)
        xp=(raw[0]-d*z_local[0],raw[1]-d*z_local[1],raw[2]-d*z_local[2])
        x_local=_norm(xp) if _mag(xp)>1e-9 else _norm(v01)
        y_local=_norm(_cross(z_local,x_local))
    elif lcs_type==2 and has_vec:
        raw=_norm((vx,vy,vz)); d=_dot(raw,z_local)
        yp=(raw[0]-d*z_local[0],raw[1]-d*z_local[1],raw[2]-d*z_local[2])
        y_local=_norm(yp) if _mag(yp)>1e-9 else _norm(v01)
        x_local=_norm(_cross(y_local,z_local))
    else:
        x_local=_norm(v01); y_local=_norm(_cross(z_local,x_local))
    cx=sum(p["X"] for p in pts)/len(pts)
    cy=sum(p["Y"] for p in pts)/len(pts)
    cz=sum(p["Z"] for p in pts)/len(pts)
    return {"origin":(cx,cy,cz),"x":x_local,"y":y_local,"z":z_local,"has_vec":has_vec,"lcs_type":lcs_type}


def compute_bar_lcs(bar, nm):
    nids=bar.get("Nodes",[])
    if len(nids)<2: return None
    n1=nm.get(nids[0]); n2=nm.get(nids[-1])
    if not n1 or not n2: return None
    p1=(n1["X"],n1["Y"],n1["Z"]); p2=(n2["X"],n2["Y"],n2["Z"])
    x_local=_norm(_sub(p2,p1))
    lcs_type=bar.get("LCS")
    vx=bar.get("LCSX",0) or 0; vy=bar.get("LCSY",0) or 0; vz=bar.get("LCSZ",0) or 0
    has_vec=_mag((vx,vy,vz))>1e-9
    if lcs_type in (0,1) and has_vec:
        ref=_norm((vx,vy,vz)); d=_dot(ref,x_local)
        perp=(ref[0]-d*x_local[0],ref[1]-d*x_local[1],ref[2]-d*x_local[2])
        perp_n=_norm(perp) if _mag(perp)>1e-9 else _default_bar_y(x_local)
        if lcs_type==0: y_local=perp_n; z_local=_norm(_cross(x_local,y_local))
        else:           z_local=perp_n; y_local=_norm(_cross(z_local,x_local))
    elif lcs_type in (2,3) and has_vec:
        ref_dir=_norm(_sub((vx,vy,vz),p1)); d=_dot(ref_dir,x_local)
        perp=(ref_dir[0]-d*x_local[0],ref_dir[1]-d*x_local[1],ref_dir[2]-d*x_local[2])
        perp_n=_norm(perp) if _mag(perp)>1e-9 else _default_bar_y(x_local)
        if lcs_type==2: y_local=perp_n; z_local=_norm(_cross(x_local,y_local))
        else:           z_local=perp_n; y_local=_norm(_cross(z_local,x_local))
    else:
        y_local=_default_bar_y(x_local); z_local=_norm(_cross(x_local,y_local))
    cx=(p1[0]+p2[0])/2; cy=(p1[1]+p2[1])/2; cz=(p1[2]+p2[2])/2
    return {"origin":(cx,cy,cz),"x":x_local,"y":y_local,"z":z_local,
            "has_vec":has_vec,"lcs_type":lcs_type,"p1":p1,"p2":p2}


def check_surface_lcs(surf, lcs):
    lcs_type=surf.get("LCS",0) or 0
    vx=surf.get("LCSX",0) or 0; vy=surf.get("LCSY",0) or 0; vz=surf.get("LCSZ",0) or 0
    if _mag((vx,vy,vz))<1e-9 or lcs_type==0: return "default",None
    ref=_norm((vx,vy,vz))
    target=lcs["x"] if lcs_type==1 else lcs["y"]
    angle=_angle_deg(ref,target); angle=min(angle,180.0-angle)
    return ("ok" if angle<=ANGLE_TOL_DEG else "error"),angle


def check_bar_lcs(bar, lcs):
    lcs_type=bar.get("LCS")
    if lcs_type is None: return "default",None
    vx=bar.get("LCSX",0) or 0; vy=bar.get("LCSY",0) or 0; vz=bar.get("LCSZ",0) or 0
    if _mag((vx,vy,vz))<1e-9: return "default",None
    if lcs_type in (0,1):
        ref=_norm((vx,vy,vz)); target=lcs["y"] if lcs_type==0 else lcs["z"]
        angle=_angle_deg(ref,target); angle=min(angle,180.0-angle)
    else:
        ref_dir=_norm(_sub((vx,vy,vz),lcs["p1"])); target=lcs["y"] if lcs_type==2 else lcs["z"]
        angle=_angle_deg(ref_dir,target); angle=min(angle,180.0-angle)
    return ("ok" if angle<=ANGLE_TOL_DEG else "error"),angle


def _status_icon(status): return {"ok":"✅","error":"❌","default":"🔵"}.get(status,"—")
def _status_label(status): return {"ok":"✅ OK","error":"❌ Error","default":"🔵 Default"}.get(status,"—")


# ─────────────────────────────────────────────────
# HELPERS GENERALES
# ─────────────────────────────────────────────────
def load_json(file): return json.load(file)
def mc(value,label): return f'<div class="metric-card"><h3>{value}</h3><p>{label}</p></div>'
def id_name_map(items): return {it.get("Id",""): it.get("Name",it.get("Id","?")) for it in (items or [])}
def nz_ratio_1d(r): return sum(1 for c in COMPS_1D if any(abs(v)>1e-6 for v in r.get(c,[])))/len(COMPS_1D)
def nz_ratio_mesh(r): return sum(1 for c in COMPS_MESH if any(abs(v)>1e-6 for v in r.get(c,[])))/len(COMPS_MESH)
def has_lcs_vector(obj): return any(obj.get(k) is not None and obj.get(k)!=0 for k in ["LCSX","LCSY","LCSZ"])
def fmt_vec(obj): return f"({obj.get('LCSX',0) or 0:.3f}, {obj.get('LCSY',0) or 0:.3f}, {obj.get('LCSZ',0) or 0:.3f})"
def fmt_axis(v): return f"({v[0]:.3f},{v[1]:.3f},{v[2]:.3f})"

def project_to_2d(points_3d):
    if len(points_3d)<3: return [(p[0],p[1]) for p in points_3d]
    p0,p1,p2=points_3d[0],points_3d[1],points_3d[2]
    v1=(p1[0]-p0[0],p1[1]-p0[1],p1[2]-p0[2]); v2=(p2[0]-p0[0],p2[1]-p0[1],p2[2]-p0[2])
    nx=abs(v1[1]*v2[2]-v1[2]*v2[1]); ny=abs(v1[2]*v2[0]-v1[0]*v2[2]); nz=abs(v1[0]*v2[1]-v1[1]*v2[0])
    if nz>=nx and nz>=ny: return [(p[0],p[1]) for p in points_3d]
    elif ny>=nx:           return [(p[0],p[2]) for p in points_3d]
    else:                  return [(p[1],p[2]) for p in points_3d]

def point_in_polygon_2d(px,py,polygon):
    n=len(polygon); inside=False; j=n-1
    for i in range(n):
        xi,yi=polygon[i]; xj,yj=polygon[j]
        if ((yi>py)!=(yj>py)) and (px<(xj-xi)*(py-yi)/(yj-yi)+xi): inside=not inside
        j=i
    return inside


# ─────────────────────────────────────────────────
# TRAZAS LCS EN 3D — ejes X/Y/Z calculados
# ─────────────────────────────────────────────────
def _add_axis_line(fig, origin, direction, scale, color, hover, group):
    tip=(origin[0]+direction[0]*scale, origin[1]+direction[1]*scale, origin[2]+direction[2]*scale)
    fig.add_trace(go.Scatter3d(
        x=[origin[0],tip[0]], y=[origin[1],tip[1]], z=[origin[2],tip[2]],
        mode='lines', line=dict(color=color,width=4),
        hovertemplate=hover+"<extra></extra>",
        legendgroup=group, showlegend=False))


def add_lcs_traces_surfaces(fig, data, nm, scale):
    for surf in data.get("SurfaceMembers",[]):
        lcs=compute_surface_lcs(surf, nm)
        if not lcs: continue
        status,angle=check_surface_lcs(surf, lcs)
        o=lcs["origin"]; name=surf.get("Name","")
        lcs_type=surf.get("LCS",0) or 0

        for axis,base_color,label in [("x","#e94560","X"),("y","#51cf66","Y"),("z","#4a9eff","Z")]:
            v=lcs[axis]
            is_checked=(label=="X" and lcs_type==1) or (label=="Y" and lcs_type==2)
            color=LCS_BAD_COLOR if (is_checked and status=="error") else base_color
            angle_str=f" {_status_icon(status)} {angle:.1f}°" if is_checked and angle is not None else ""
            _add_axis_line(fig, o, v, scale, color, f"{name} eje {label}{angle_str}", "lcs_surf")

        pt_color=LCS_OK_COLOR if status=="ok" else (LCS_BAD_COLOR if status=="error" else LCS_NONE_COLOR)
        fig.add_trace(go.Scatter3d(
            x=[o[0]],y=[o[1]],z=[o[2]], mode='markers',
            marker=dict(size=5,color=pt_color),
            text=[f"{_status_icon(status)} {name}"],
            hovertemplate="%{text}<extra></extra>",
            legendgroup="lcs_surf_pt", showlegend=False))


def add_lcs_traces_bars(fig, data, nm, scale):
    for bar in data.get("CurveMembers",[]):
        lcs=compute_bar_lcs(bar, nm)
        if not lcs: continue
        status,angle=check_bar_lcs(bar, lcs)
        o=lcs["origin"]; name=bar.get("Name",""); lcs_type=bar.get("LCS")

        for axis,base_color,label in [("x","#e94560","X"),("y","#51cf66","Y"),("z","#4a9eff","Z")]:
            v=lcs[axis]
            is_checked=(label=="Y" and lcs_type in (0,2)) or (label=="Z" and lcs_type in (1,3))
            color=LCS_BAD_COLOR if (is_checked and status=="error") else base_color
            angle_str=f" {_status_icon(status)} {angle:.1f}°" if is_checked and angle is not None else ""
            _add_axis_line(fig, o, v, scale, color, f"{name} eje {label}{angle_str}", "lcs_bar")

        pt_color=LCS_OK_COLOR if status=="ok" else (LCS_BAD_COLOR if status=="error" else LCS_NONE_COLOR)
        fig.add_trace(go.Scatter3d(
            x=[o[0]],y=[o[1]],z=[o[2]], mode='markers',
            marker=dict(size=4,color=pt_color),
            text=[f"{_status_icon(status)} {name}"],
            hovertemplate="%{text}<extra></extra>",
            legendgroup="lcs_bar_pt", showlegend=False))

    # Leyenda visible
    for color,label in [(LCS_OK_COLOR,"LCS ✅ OK"),(LCS_BAD_COLOR,"LCS ❌ Error"),(LCS_NONE_COLOR,"LCS 🔵 Default")]:
        fig.add_trace(go.Scatter3d(x=[None],y=[None],z=[None],mode='markers',
            marker=dict(size=8,color=color),name=label))


# ─────────────────────────────────────────────────
# RESUMEN
# ─────────────────────────────────────────────────
def render_overview(data):
    st.markdown('<p class="section-header">📊 Resumen del Modelo</p>', unsafe_allow_html=True)
    c1,c2=st.columns([2,1])
    c1.markdown(f"### {data.get('Name','N/A')}")
    c2.markdown(f"`{data.get('Description','')}`")
    groups=[
        ("GEOMETRÍA",[("Materials","Materiales"),("CrossSections","Secciones"),("PointConnections","Nodos"),
            ("CurveMembers","Barras"),("SurfaceMembers","Superficies"),("SurfaceMemberOpenings","Aberturas"),
            ("SurfaceMemberRegions","Regiones"),("PointSupports","Apoyos")]),
        ("CARGAS",[("LoadCases","Casos"),("LoadCombinations","Combinaciones"),
            ("PointActions","Puntuales"),("CurveActions","Lineales"),("SurfaceActions","Superficiales")]),
        ("RESULTADOS",[("Results1D","1D Barras"),("MeshResults","2D Malla"),("Macros","Macros")]),
    ]
    for gn,ents in groups:
        st.markdown(f'<p class="group-label">{gn}</p>', unsafe_allow_html=True)
        cols=st.columns(len(ents))
        for col,(k,l) in zip(cols,ents):
            col.markdown(mc(len(data.get(k,[])),l), unsafe_allow_html=True)


def render_materials(data):
    st.markdown('<p class="section-header">🧱 Materiales</p>', unsafe_allow_html=True)
    mats=data.get("Materials",[])
    if not mats: return st.info("No hay materiales.")
    rows=[]
    for m in mats:
        mt=m.get("Type",0)
        row={"Nombre":m.get("Name",""),"Tipo":MATERIAL_TYPE.get(mt,str(mt)),
             "E (MPa)":f"{m.get('EModulus',0)/1e6:.1f}" if m.get("EModulus",0)>1000 else f"{m.get('EModulus',0):.1f}",
             "G (MPa)":f"{m.get('GModulus',0)/1e6:.1f}" if m.get("GModulus",0)>1000 else f"{m.get('GModulus',0):.1f}",
             "nu":m.get("PoissonCoefficient",""),
             "rho (kg/m3)":f"{m.get('UnitMass',0)/9.81:.0f}" if m.get("UnitMass",0)>100 else f"{m.get('UnitMass',0):.1f}"}
        if mt==1: row["Fck (MPa)"]=f"{m.get('Fck',0)/1e6:.1f}" if m.get("Fck",0)>1000 else f"{m.get('Fck',0):.1f}"
        elif mt==2:
            row["Fy (MPa)"]=f"{m.get('Fy',0)/1e6:.1f}" if m.get("Fy",0)>1000 else f"{m.get('Fy',0):.1f}"
            row["Fu (MPa)"]=f"{m.get('Fu',0)/1e6:.1f}" if m.get("Fu",0)>1000 else f"{m.get('Fu',0):.1f}"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_cross_sections(data):
    st.markdown('<p class="section-header">📐 Secciones</p>', unsafe_allow_html=True)
    secs=data.get("CrossSections",[])
    if not secs: return st.info("No hay secciones.")
    mm=id_name_map(data.get("Materials",[]))
    rows=[{"Nombre":s.get("Name",""),"Tipo":CS_TYPE.get(s.get("Type",-1),"?"),
           "Forma":CS_SHAPE.get(s.get("Shape",-1),str(s.get("Shape",-1))),
           "Parametros (m)":", ".join(f"{p:.3f}" for p in s.get("Parameters",[])),
           "Material":", ".join(mm.get(mid,mid[:8]) for mid in s.get("Materials",[]))} for s in secs]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────
# MODELO 3D
# ─────────────────────────────────────────────────
def render_3d_model(data):
    st.markdown('<p class="section-header">📍 Modelo 3D</p>', unsafe_allow_html=True)
    nodes=data.get("PointConnections",[])
    if not nodes: return st.info("No hay nodos.")
    nm={n.get("Id"):n for n in nodes}
    sup_ids=set(s.get("Node","") for s in data.get("PointSupports",[]))

    cc=st.columns(7)
    show_nodes    =cc[0].checkbox("Nodos",False)
    show_sups     =cc[1].checkbox("Apoyos",True)
    show_cols     =cc[2].checkbox("Columnas",True)
    show_beams    =cc[3].checkbox("Vigas",True)
    show_panels   =cc[4].checkbox("Paneles",True)
    show_openings =cc[5].checkbox("Aberturas",True)
    show_lcs      =cc[6].checkbox("LCS",False)

    if show_lcs:
        sc1,sc2=st.columns(2)
        lcs_scale_surf=sc1.slider("Escala LCS superficies",0.1,3.0,0.5,0.1)
        lcs_scale_bar =sc2.slider("Escala LCS barras",0.1,3.0,0.4,0.1)
        st.caption("🔴 X local  🟢 Y local  🔵 Z local  |  El eje verificado se vuelve rojo si hay error de alineacion")
    else:
        lcs_scale_surf,lcs_scale_bar=0.5,0.4

    fig=go.Figure()

    if show_nodes:
        ns=[n for n in nodes if n.get("Id") not in sup_ids]
        if ns:
            fig.add_trace(go.Scatter3d(x=[n["X"] for n in ns],y=[n["Y"] for n in ns],z=[n["Z"] for n in ns],
                mode='markers',marker=dict(size=2,color="#4a9eff",opacity=0.5),
                text=[n.get("Name","") for n in ns],hovertemplate="<b>%{text}</b><br>(%{x:.1f},%{y:.1f},%{z:.1f})<extra></extra>",name="Nodos"))

    if show_sups:
        sn=[nm[sid] for sid in sup_ids if sid in nm]
        if sn:
            fig.add_trace(go.Scatter3d(x=[n["X"] for n in sn],y=[n["Y"] for n in sn],z=[n["Z"] for n in sn],
                mode='markers',marker=dict(size=5,color="#e94560",symbol='diamond'),
                text=[n.get("Name","") for n in sn],hovertemplate="<b>%{text}</b> (Apoyo)<extra></extra>",name="Apoyos"))

    bars=data.get("CurveMembers",[])
    bar_groups={}
    for bar in bars:
        bt=CURVE_TYPE.get(bar.get("Type",0),"Other")
        if bt=="Column" and not show_cols: continue
        if bt!="Column" and not show_beams: continue
        if bt not in bar_groups: bar_groups[bt]={"x":[],"y":[],"z":[]}
        bn=bar.get("Nodes",[])
        if len(bn)>=2:
            n1,n2=nm.get(bn[0]),nm.get(bn[-1])
            if n1 and n2:
                bar_groups[bt]["x"].extend([n1["X"],n2["X"],None])
                bar_groups[bt]["y"].extend([n1["Y"],n2["Y"],None])
                bar_groups[bt]["z"].extend([n1["Z"],n2["Z"],None])
    cmap={"Column":"#ff6b6b","Beam":"#51cf66","General":"#748ffc","SlabRib":"#ffd43b"}
    for bt,co in bar_groups.items():
        fig.add_trace(go.Scatter3d(x=co["x"],y=co["y"],z=co["z"],mode='lines',
            line=dict(color=cmap.get(bt,"#748ffc"),width=3),name=bt,connectgaps=False))

    if show_panels:
        opening_map={}
        for op in data.get("SurfaceMemberOpenings",[]):
            sid=op.get("Surface","")
            pts_op=[nm.get(nid) for nid in op.get("Nodes",[])]
            pts_op=[p for p in pts_op if p]
            if len(pts_op)>=3:
                if sid not in opening_map: opening_map[sid]=[]
                opening_map[sid].append([(p["X"],p["Y"],p["Z"]) for p in pts_op])

        def pit(p,a,b,c):
            def sign(p1,p2,p3): return (p1[0]-p3[0])*(p2[1]-p3[1])-(p2[0]-p3[0])*(p1[1]-p3[1])
            d1,d2,d3=sign(p,a,b),sign(p,b,c),sign(p,c,a)
            return not((d1<0 or d2<0 or d3<0) and (d1>0 or d2>0 or d3>0))

        def triangulate(pts_3d, openings_3d=None):
            if len(pts_3d)<3: return []
            pts_2d=project_to_2d([(p["X"],p["Y"],p["Z"]) for p in pts_3d])
            tris=[]; idxs=list(range(len(pts_2d))); poly_sign=None; max_it=len(idxs)*3
            while len(idxs)>2 and max_it>0:
                max_it-=1; found=False; n=len(idxs)
                if poly_sign is None:
                    area=sum((pts_2d[idxs[j]][0]*pts_2d[idxs[(j+1)%n]][1]-pts_2d[idxs[(j+1)%n]][0]*pts_2d[idxs[j]][1]) for j in range(n))
                    poly_sign=1 if area>0 else -1
                for i in range(n):
                    pi,ci,ni=idxs[(i-1)%n],idxs[i],idxs[(i+1)%n]
                    ax,ay=pts_2d[pi]; bx,by=pts_2d[ci]; cx,cy=pts_2d[ni]
                    if ((bx-ax)*(cy-ay)-(by-ay)*(cx-ax))*poly_sign<=0: continue
                    if not any(pit(pts_2d[idxs[j]],pts_2d[pi],pts_2d[ci],pts_2d[ni]) for j in range(n) if idxs[j] not in (pi,ci,ni)):
                        tris.append((pi,ci,ni)); idxs.pop(i); found=True; break
                if not found: break
            if openings_3d:
                ops2d=[project_to_2d(op) for op in openings_3d]
                tris=[t for t in tris if not any(point_in_polygon_2d(
                    (pts_2d[t[0]][0]+pts_2d[t[1]][0]+pts_2d[t[2]][0])/3,
                    (pts_2d[t[0]][1]+pts_2d[t[1]][1]+pts_2d[t[2]][1])/3,op2d) for op2d in ops2d)]
            return tris

        for stype,label,color,ecolor in [(0,"Losas","rgba(100,180,255,0.55)","rgba(100,180,255,0.8)"),
                                          (1,"Muros","rgba(255,160,80,0.55)","rgba(255,160,80,0.8)")]:
            mx={"x":[],"y":[],"z":[],"i":[],"j":[],"k":[]}; ex={"x":[],"y":[],"z":[]}
            for surf in data.get("SurfaceMembers",[]):
                if surf.get("Type",0)!=stype: continue
                sid=surf.get("Id","")
                pts=[nm.get(nid) for nid in surf.get("Nodes",[])]
                pts=[p for p in pts if p]
                if len(pts)<3: continue
                off=len(mx["x"])
                for p in pts: mx["x"].append(p["X"]); mx["y"].append(p["Y"]); mx["z"].append(p["Z"])
                for i0,i1,i2 in triangulate(pts, opening_map.get(sid)):
                    mx["i"].append(off+i0); mx["j"].append(off+i1); mx["k"].append(off+i2)
                for p in pts: ex["x"].append(p["X"]); ex["y"].append(p["Y"]); ex["z"].append(p["Z"])
                ex["x"].extend([pts[0]["X"],None]); ex["y"].extend([pts[0]["Y"],None]); ex["z"].extend([pts[0]["Z"],None])
            if mx["x"]:
                fig.add_trace(go.Mesh3d(x=mx["x"],y=mx["y"],z=mx["z"],i=mx["i"],j=mx["j"],k=mx["k"],
                    color=color,opacity=0.55,name=label,showlegend=True))
                fig.add_trace(go.Scatter3d(x=ex["x"],y=ex["y"],z=ex["z"],mode='lines',
                    line=dict(color=ecolor,width=2),name=f"Bordes {label}",connectgaps=False,showlegend=False))

    if show_openings:
        ox,oy,oz=[],[],[]
        for op in data.get("SurfaceMemberOpenings",[]):
            pts=[nm.get(nid) for nid in op.get("Nodes",[])]
            pts=[p for p in pts if p]
            if len(pts)<3: continue
            for p in pts: ox.append(p["X"]); oy.append(p["Y"]); oz.append(p["Z"])
            ox.extend([pts[0]["X"],None]); oy.extend([pts[0]["Y"],None]); oz.extend([pts[0]["Z"],None])
        if ox: fig.add_trace(go.Scatter3d(x=ox,y=oy,z=oz,mode='lines',line=dict(color="#ff0",width=3),name="Aberturas",connectgaps=False))

    if show_lcs:
        add_lcs_traces_surfaces(fig, data, nm, lcs_scale_surf)
        add_lcs_traces_bars(fig, data, nm, lcs_scale_bar)

    ng=dict(showgrid=False,showline=False,zeroline=False,showbackground=False)
    fig.update_layout(
        scene=dict(xaxis=dict(title="X (m)",**ng),yaxis=dict(title="Y (m)",**ng),
                   zaxis=dict(title="Z (m)",**ng),aspectmode='data',bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=0,r=160,t=30,b=0),height=650,template="plotly_dark",
        legend=dict(
            orientation="v",x=1.01,y=0.5,xanchor="left",yanchor="middle",
            bgcolor="rgba(20,20,40,0.85)",bordercolor="#0f3460",borderwidth=1,
            font=dict(size=11)))
    st.plotly_chart(fig, use_container_width=True)

    if show_lcs:
        nm_local={n.get("Id"):n for n in data.get("PointConnections",[])}
        err_rows=[]
        for s in data.get("SurfaceMembers",[]):
            if has_lcs_vector(s):
                lcs=compute_surface_lcs(s,nm_local)
                status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
                if status=="error":
                    err_rows.append({"Tipo":"Superficie","Nombre":s.get("Name",""),
                        "LCS enum":s.get("LCS",0),
                        "Eje verificado":"X" if s.get("LCS")==1 else "Y",
                        "Vector JSON":fmt_vec(s),
                        "Angulo error (deg)":f"{angle:.2f}"})
        for b in data.get("CurveMembers",[]):
            if has_lcs_vector(b):
                lcs=compute_bar_lcs(b,nm_local)
                status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
                if status=="error":
                    lcs_type=b.get("LCS")
                    err_rows.append({"Tipo":"Barra","Nombre":b.get("Name",""),
                        "LCS enum":lcs_type,
                        "Eje verificado":"Y" if lcs_type in (0,2) else "Z",
                        "Vector JSON":fmt_vec(b),
                        "Angulo error (deg)":f"{angle:.2f}"})
        if err_rows:
            st.markdown(f"#### ❌ Elementos con LCS incorrecto ({len(err_rows)})")
            st.dataframe(pd.DataFrame(err_rows),use_container_width=True,hide_index=True)
        elif any(has_lcs_vector(s) for s in data.get("SurfaceMembers",[])) or              any(has_lcs_vector(b) for b in data.get("CurveMembers",[])):
            st.success("✅ Todos los LCS con vector definido estan correctamente alineados.")


# ─────────────────────────────────────────────────
# BARRAS
# ─────────────────────────────────────────────────
def render_bars(data):
    st.markdown('<p class="section-header">🔩 Barras</p>', unsafe_allow_html=True)
    bars=data.get("CurveMembers",[])
    if not bars: return st.info("No hay barras.")
    csm=id_name_map(data.get("CrossSections",[]))
    nm={n.get("Id"):n for n in data.get("PointConnections",[])}

    tc=Counter(CURVE_TYPE.get(b.get("Type",0),"Other") for b in bars)
    c1,c2=st.columns([1,2])
    with c1:
        fig=px.pie(values=list(tc.values()),names=list(tc.keys()),title="Por Tipo",color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(template="plotly_dark",height=300,margin=dict(t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        rows=[]
        for b in bars:
            lcs=compute_bar_lcs(b, nm)
            lcs_status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
            rows.append({"ID":b.get("Id",""),"Nombre":b.get("Name",""),
                "Tipo":CURVE_TYPE.get(b.get("Type",0),"?"),
                "Seccion":csm.get(b.get("CrossSection",""),"N/A"),
                "LCS Tipo":CURVE_LCS_TYPE.get(b.get("LCS"),"—") if b.get("LCS") is not None else "—",
                "Vector":fmt_vec(b) if has_lcs_vector(b) else "—",
                "LCS":_status_icon(lcs_status),
                "Angulo (deg)":f"{angle:.2f}" if angle is not None else "—"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=300)

    bars_vec=[b for b in bars if has_lcs_vector(b)]
    if bars_vec:
        st.markdown("---")
        st.markdown(f"#### 🧭 Verificacion LCS — Barras ({len(bars_vec)} con vector)")
        rows2=[]
        for b in bars_vec:
            lcs=compute_bar_lcs(b, nm)
            status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
            lcs_type=b.get("LCS")
            xl=fmt_axis(lcs["x"]) if lcs else "—"; yl=fmt_axis(lcs["y"]) if lcs else "—"; zl=fmt_axis(lcs["z"]) if lcs else "—"
            rows2.append({"Nombre":b.get("Name",""),
                "LCS Tipo":CURVE_LCS_TYPE.get(lcs_type,"—") if lcs_type is not None else "—",
                "Eje verificado":"Y" if lcs_type in (0,2) else ("Z" if lcs_type in (1,3) else "—"),
                "Vector JSON":fmt_vec(b),
                "X local":xl,"Y local":yl,"Z local":zl,
                "Estado":_status_label(status),
                "Angulo error (deg)":f"{angle:.2f}" if angle is not None else "—"})
        df2=pd.DataFrame(rows2)
        ok=len(df2[df2["Estado"]=="✅ OK"]); err=len(df2[df2["Estado"]=="❌ Error"])
        cc1,cc2,cc3=st.columns(3)
        cc1.metric("Con vector LCS",len(df2)); cc2.metric("Correctos",ok); cc3.metric("Errores",err)
        filt=st.radio("Filtrar:",["Todos","Correctos","Errores"],horizontal=True,key="fbar_lcs")
        if filt=="Correctos": df2=df2[df2["Estado"]=="✅ OK"]
        elif filt=="Errores": df2=df2[df2["Estado"]=="❌ Error"]
        st.dataframe(df2, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────
# SUPERFICIES
# ─────────────────────────────────────────────────
def render_surfaces(data):
    st.markdown('<p class="section-header">🧩 Superficies</p>', unsafe_allow_html=True)
    surfs=data.get("SurfaceMembers",[])
    if not surfs: return st.info("No hay superficies.")
    mm=id_name_map(data.get("Materials",[]))
    nm={n.get("Id"):n for n in data.get("PointConnections",[])}

    tc=Counter(SURFACE_TYPE.get(s.get("Type",0),"Other") for s in surfs)
    c1,c2=st.columns([1,2])
    with c1:
        fig=px.pie(values=list(tc.values()),names=list(tc.keys()),title="Por Tipo",color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(template="plotly_dark",height=300,margin=dict(t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        rows=[]
        for s in surfs:
            lcs=compute_surface_lcs(s, nm)
            status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
            rows.append({"ID":s.get("Id",""),"Nombre":s.get("Name",""),
                "Tipo":SURFACE_TYPE.get(s.get("Type",0),"?"),
                "Espesor":s.get("Thickness",""),"Nodos":len(s.get("Nodes",[])),
                "Material":", ".join(mm.get(mid,mid[:8]) for mid in s.get("Materials",[])),
                "LCS Tipo":SURFACE_LCS_TYPE.get(s.get("LCS"),"-") if s.get("LCS") is not None else "—",
                "Vector":fmt_vec(s) if has_lcs_vector(s) else "—",
                "Rot (deg)":f"{s.get('LCSRotation'):.1f}" if s.get("LCSRotation") is not None else "—",
                "LCS":_status_icon(status),
                "Angulo (deg)":f"{angle:.2f}" if angle is not None else "—"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=300)

    surfs_vec=[s for s in surfs if has_lcs_vector(s)]
    if surfs_vec:
        st.markdown("---")
        st.markdown(f"#### 🧭 Verificacion LCS — Superficies ({len(surfs_vec)} con vector)")
        rows2=[]
        for s in surfs_vec:
            lcs=compute_surface_lcs(s, nm)
            status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
            lcs_type=s.get("LCS",0) or 0
            xl=fmt_axis(lcs["x"]) if lcs else "—"; yl=fmt_axis(lcs["y"]) if lcs else "—"; zl=fmt_axis(lcs["z"]) if lcs else "—"
            rows2.append({"Nombre":s.get("Name",""),
                "Tipo sup":SURFACE_TYPE.get(s.get("Type",0),"?"),
                "LCS Tipo":SURFACE_LCS_TYPE.get(lcs_type,"—"),
                "Eje verificado":"X" if lcs_type==1 else ("Y" if lcs_type==2 else "—"),
                "Vector JSON":fmt_vec(s),
                "X local":xl,"Y local":yl,"Z local (normal)":zl,
                "Rot (deg)":f"{s.get('LCSRotation'):.2f}" if s.get("LCSRotation") is not None else "—",
                "Estado":_status_label(status),
                "Angulo error (deg)":f"{angle:.2f}" if angle is not None else "—"})
        df2=pd.DataFrame(rows2)
        ok=len(df2[df2["Estado"]=="✅ OK"]); err=len(df2[df2["Estado"]=="❌ Error"])
        cc1,cc2,cc3=st.columns(3)
        cc1.metric("Con vector LCS",len(df2)); cc2.metric("Correctos",ok); cc3.metric("Errores",err)
        filt=st.radio("Filtrar:",["Todos","Correctos","Errores"],horizontal=True,key="fsurf_lcs")
        if filt=="Correctos": df2=df2[df2["Estado"]=="✅ OK"]
        elif filt=="Errores": df2=df2[df2["Estado"]=="❌ Error"]
        st.dataframe(df2, use_container_width=True, hide_index=True)

    regs=data.get("SurfaceMemberRegions",[])
    if regs:
        st.markdown(f"**Regiones:** {len(regs)}")
        st.dataframe(pd.DataFrame([{"ID":r.get("Id",""),"Nombre":r.get("Name",""),
            "Superficie":r.get("Surface",""),"Espesor":r.get("Thickness",""),
            "Nodos":len(r.get("Nodes",[]))} for r in regs]),use_container_width=True,hide_index=True,height=200)
    ops=data.get("SurfaceMemberOpenings",[])
    if ops:
        st.markdown(f"**Aberturas:** {len(ops)}")
        st.dataframe(pd.DataFrame([{"Nombre":o.get("Name",""),"Superficie":o.get("Surface",""),
            "Nodos":" -> ".join(o.get("Nodes",[]))} for o in ops]),use_container_width=True,hide_index=True)


def render_supports(data):
    st.markdown('<p class="section-header">📌 Apoyos</p>', unsafe_allow_html=True)
    sups=data.get("PointSupports",[])
    if not sups: return st.info("No hay apoyos.")
    st.dataframe(pd.DataFrame([{"Nombre":s.get("Name",""),"Nodo":s.get("Node",""),
        "Ux":SUPPORT_TRANS.get(s.get("Ux",0),"?"),"Uy":SUPPORT_TRANS.get(s.get("Uy",0),"?"),
        "Uz":SUPPORT_TRANS.get(s.get("Uz",0),"?"),"Rx":SUPPORT_ROT.get(s.get("Fix",0),"?"),
        "Ry":SUPPORT_ROT.get(s.get("Fiy",0),"?"),"Rz":SUPPORT_ROT.get(s.get("Fiz",0),"?")} for s in sups]),
        use_container_width=True,hide_index=True)


def render_loads(data):
    st.markdown('<p class="section-header">⚡ Cargas y Combinaciones</p>', unsafe_allow_html=True)
    lm=id_name_map(data.get("LoadCases",[]))
    cases=data.get("LoadCases",[])
    if cases:
        st.markdown("**Casos de Carga**")
        st.dataframe(pd.DataFrame([{"Nombre":c.get("Name",""),
            "Accion":ACTION_TYPE_LC.get(c.get("ActionType",-1),"?"),
            "Tipo":LOAD_TYPE.get(c.get("Type",-1),"?")} for c in cases]),use_container_width=True,hide_index=True)
    combos=data.get("LoadCombinations",[])
    if combos:
        st.markdown("**Combinaciones**")
        for combo in combos:
            st.markdown(f"**{combo.get('Name','?')}** — {COMB_CATEGORY.get(combo.get('Category',0),'?')}")
            lids=combo.get("LoadCases",[]); facs=combo.get("LoadFactors",[]); mults=combo.get("Multipliers",[])
            st.dataframe(pd.DataFrame([{"Caso":lm.get(lids[j],lids[j][:12]),
                "Factor":facs[j] if j<len(facs) else "?","Mult.":mults[j] if j<len(mults) else "?"} for j in range(len(lids))]),
                use_container_width=True,hide_index=True)


def render_actions(data):
    st.markdown('<p class="section-header">🎯 Acciones</p>', unsafe_allow_html=True)
    lm=id_name_map(data.get("LoadCases",[]))
    pa=data.get("PointActions",[])
    if pa:
        st.markdown(f"**Puntuales** ({len(pa)})")
        st.dataframe(pd.DataFrame([{"Nombre":a.get("Name",""),"Nodo":a.get("ReferenceNode",""),
            "X":a.get("X",0),"Y":a.get("Y",0),"Z":a.get("Z",0),
            "Caso":lm.get(a.get("LoadCase",""),"?")} for a in pa]),use_container_width=True,hide_index=True)
    ca=data.get("CurveActions",[])
    if ca:
        st.markdown(f"**Lineales** ({len(ca)})")
        st.dataframe(pd.DataFrame([{"Nombre":a.get("Name",""),"Barra":a.get("CurveMember",""),
            "Dist.":DISTRIBUTION.get(a.get("Distribution",0),"?"),
            "X":a.get("X",0),"Y":a.get("Y",0),"Z":a.get("Z",0),
            "Caso":lm.get(a.get("LoadCase",""),"?")} for a in ca]),use_container_width=True,hide_index=True)
    sa=data.get("SurfaceActions",[])
    if sa:
        st.markdown(f"**Superficiales** ({len(sa)})")
        st.dataframe(pd.DataFrame([{"Nombre":a.get("Name",""),"Superficie":a.get("SurfaceElement",""),
            "Qx":a.get("Qx",0),"Qy":a.get("Qy",0),"Qz":a.get("Qz",0),
            "Caso":lm.get(a.get("LoadCase",""),"?")} for a in sa]),use_container_width=True,hide_index=True)


def render_results_1d(data):
    st.markdown('<p class="section-header">📈 Resultados 1D</p>', unsafe_allow_html=True)
    results=data.get("Results1D",[])
    if not results: return st.info("No hay resultados 1D.")
    lm={**id_name_map(data.get("LoadCases",[])),**id_name_map(data.get("LoadCombinations",[]))}
    nm={n.get("Id"):n for n in data.get("PointConnections",[])}
    result_index={}; bar_summary={}
    for r in results:
        bid=r.get("Member",""); lid=r.get("Load","")
        result_index[(bid,lid)]=r; ratio=nz_ratio_1d(r)
        if bid not in bar_summary: bar_summary[bid]={"nz":0,"z":0,"max":{c:0 for c in COMPS_1D}}
        if ratio>0: bar_summary[bid]["nz"]+=1
        else: bar_summary[bid]["z"]+=1
        for c in COMPS_1D:
            vals=[abs(v) for v in r.get(c,[])]
            if vals: bar_summary[bid]["max"][c]=max(bar_summary[bid]["max"][c],max(vals))
    total=len(results); full=sum(1 for r in results if nz_ratio_1d(r)==1.0)
    partial=sum(1 for r in results if 0<nz_ratio_1d(r)<1.0); empty=sum(1 for r in results if nz_ratio_1d(r)==0)
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Total",total); m2.metric("Completos",full); m3.metric("Parciales",partial); m4.metric("Vacios",empty)
    bar_obj_map={b.get("Id",""):b for b in data.get("CurveMembers",[])}
    rows=[]
    for bid in sorted(bar_summary.keys(), key=lambda x:int(x) if x.isdigit() else 0):
        info=bar_summary[bid]; mv=info["max"]
        b=bar_obj_map.get(bid,{}); lcs=compute_bar_lcs(b,nm) if b else None
        status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
        rows.append({"Barra":f"Bar {bid}","bar_id":bid,
            "Estado":"OK" if info["nz"]>0 else "vacio","Casos NZ":info["nz"],
            "|N|":f"{mv['aN']:.2f}","|Vy|":f"{mv['aVy']:.2f}","|Vz|":f"{mv['aVz']:.2f}",
            "|Mx|":f"{mv['aMx']:.2f}","|My|":f"{mv['aMy']:.2f}","|Mz|":f"{mv['aMz']:.2f}",
            "LCS":_status_icon(status),"Ang LCS":f"{angle:.1f}°" if angle is not None else "—"})
    df=pd.DataFrame(rows)
    filt=st.radio("Filtrar:",["Todos","Con valores","Vacios"],horizontal=True,key="f1d")
    if filt=="Con valores": df=df[df["Estado"]=="OK"]
    elif filt=="Vacios": df=df[df["Estado"]=="vacio"]
    st.dataframe(df.drop(columns=["bar_id"]),use_container_width=True,hide_index=True,height=280)
    st.markdown("---"); st.markdown("#### Diagrama detallado")
    bar_ids=df["bar_id"].tolist()
    if not bar_ids: return
    load_ids=sorted(set(r.get("Load","") for r in results)); load_names=[lm.get(lid,lid[:8]) for lid in load_ids]
    sc1,sc2=st.columns(2)
    sel_bar=sc1.selectbox("Barra:",bar_ids,format_func=lambda x:f"Bar {x}",key="sel_bar")
    sel_load=load_ids[load_names.index(sc2.selectbox("Caso:",load_names,key="sel_load"))]
    r=result_index.get((sel_bar,sel_load))
    if not r: return st.warning("Sin resultado.")
    b=bar_obj_map.get(sel_bar,{})
    if has_lcs_vector(b) or b.get("LCS") is not None:
        lcs=compute_bar_lcs(b, nm); status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
        a_str=f" | Error angular: {angle:.2f} deg" if angle is not None else ""
        st.info(f"🧭 LCS Barra {sel_bar}: {_status_label(status)}{a_str} | Vector: {fmt_vec(b)}")
    secs=r.get("SectionsAt",[])
    comps={"N (kN)":r.get("aN",[]),"Vy (kN)":r.get("aVy",[]),"Vz (kN)":r.get("aVz",[]),
           "Mx (kNm)":r.get("aMx",[]),"My (kNm)":r.get("aMy",[]),"Mz (kNm)":r.get("aMz",[])}
    nz_comps=[n for n,v in comps.items() if any(abs(x)>1e-6 for x in v)]
    defaults=[c for c in ["Vz (kN)","My (kNm)"] if c in nz_comps] or nz_comps[:2]
    sel_comps=st.multiselect("Componentes:",list(comps.keys()),default=defaults,key="mc1d")
    if sel_comps and secs:
        fig=go.Figure()
        for i,comp in enumerate(sel_comps):
            vals=comps.get(comp,[])
            if vals: fig.add_trace(go.Scatter(x=secs,y=vals,name=comp,mode='lines+markers',
                line=dict(color=PLOT_COLORS[i%len(PLOT_COLORS)],width=2),marker=dict(size=5)))
        fig.update_layout(template="plotly_dark",xaxis_title="Posicion (m)",height=400,margin=dict(t=30,b=40),legend=dict(orientation="h",y=1.1))
        st.plotly_chart(fig, use_container_width=True)


def render_mesh_results(data):
    st.markdown('<p class="section-header">🔺 Resultados Malla 2D</p>', unsafe_allow_html=True)
    results=data.get("MeshResults",[])
    if not results: return st.info("No hay resultados de malla.")
    lm={**id_name_map(data.get("LoadCases",[])),**id_name_map(data.get("LoadCombinations",[]))}
    nm={n.get("Id"):n for n in data.get("PointConnections",[])}
    result_index={}; panel_summary={}
    for r in results:
        pid=r.get("Member",""); lid=r.get("Load","")
        result_index[(pid,lid)]=r; ratio=nz_ratio_mesh(r)
        if pid not in panel_summary: panel_summary[pid]={"nz":0,"z":0,"max":{c:0 for c in COMPS_MESH}}
        if ratio>0: panel_summary[pid]["nz"]+=1
        else: panel_summary[pid]["z"]+=1
        for c in COMPS_MESH:
            vals=[abs(v) for v in r.get(c,[])]; 
            if vals: panel_summary[pid]["max"][c]=max(panel_summary[pid]["max"][c],max(vals))
    total=len(results); full=sum(1 for r in results if nz_ratio_mesh(r)==1.0)
    partial=sum(1 for r in results if 0<nz_ratio_mesh(r)<1.0); empty=sum(1 for r in results if nz_ratio_mesh(r)==0)
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Total",total); m2.metric("Completos",full); m3.metric("Parciales",partial); m4.metric("Vacios",empty)
    surf_obj_map={s.get("Id",""):s for s in data.get("SurfaceMembers",[])}
    rows=[]
    for pid in sorted(panel_summary.keys(), key=lambda x:int(x) if x.isdigit() else 0):
        info=panel_summary[pid]; mv=info["max"]
        s=surf_obj_map.get(pid,{}); lcs=compute_surface_lcs(s,nm) if s else None
        status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
        rows.append({"Panel":f"Panel {pid}","panel_id":pid,
            "Estado":"OK" if info["nz"]>0 else "vacio",
            "|mx|":f"{mv['amx']:.2f}","|my|":f"{mv['amy']:.2f}",
            "|nx|":f"{mv['anx']:.2f}","|ny|":f"{mv['any']:.2f}",
            "|vx|":f"{mv['avx']:.2f}","|vy|":f"{mv['avy']:.2f}",
            "LCS":_status_icon(status),"Ang LCS":f"{angle:.1f}°" if angle is not None else "—"})
    df=pd.DataFrame(rows)
    filt=st.radio("Filtrar:",["Todos","Con valores","Vacios"],horizontal=True,key="fmesh")
    if filt=="Con valores": df=df[df["Estado"]=="OK"]
    elif filt=="Vacios": df=df[df["Estado"]=="vacio"]
    st.dataframe(df.drop(columns=["panel_id"]),use_container_width=True,hide_index=True,height=280)
    st.markdown("---"); st.markdown("#### Diagrama detallado")
    panel_ids=df["panel_id"].tolist()
    if not panel_ids: return
    load_ids=sorted(set(r.get("Load","") for r in results)); load_names=[lm.get(lid,lid[:8]) for lid in load_ids]
    sc1,sc2=st.columns(2)
    sel_panel=sc1.selectbox("Panel:",panel_ids,format_func=lambda x:f"Panel {x}",key="sel_panel")
    sel_load=load_ids[load_names.index(sc2.selectbox("Caso:",load_names,key="sel_load_m"))]
    r=result_index.get((sel_panel,sel_load))
    if not r: return st.warning("Sin resultado.")
    s=surf_obj_map.get(sel_panel,{})
    if has_lcs_vector(s) or s.get("LCS") is not None:
        lcs=compute_surface_lcs(s,nm); status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
        a_str=f" | Error angular: {angle:.2f} deg" if angle is not None else ""
        rot=s.get("LCSRotation"); r_str=f" | Rot: {rot:.2f} deg" if rot is not None else ""
        st.info(f"🧭 LCS Panel {sel_panel}: {_status_label(status)}{a_str} | Vector: {fmt_vec(s)}{r_str}")
    comps={c:r.get(c,[]) for c in COMPS_MESH if r.get(c)}
    nz_comps={k:v for k,v in comps.items() if any(abs(x)>1e-6 for x in v)}
    comp_list=list(nz_comps.keys()) if nz_comps else list(comps.keys())
    if not comp_list: return st.info("Sin componentes con valores.")
    sel=st.selectbox("Componente:",comp_list,key="sel_comp_m")
    vals=comps.get(sel,[])
    if vals:
        fig=go.Figure()
        fig.add_trace(go.Bar(x=list(range(1,len(vals)+1)),y=vals,marker_color=["#e94560" if v<0 else "#4a9eff" for v in vals]))
        fig.update_layout(template="plotly_dark",xaxis_title="Nodo FE",yaxis_title=sel,height=350,margin=dict(t=20,b=40))
        st.plotly_chart(fig, use_container_width=True)
        vc1,vc2,vc3=st.columns(3)
        vc1.metric("Min",f"{min(vals):.3f}"); vc2.metric("Max",f"{max(vals):.3f}"); vc3.metric("Nodos FE",len(vals))


# ─────────────────────────────────────────────────
# TAB LCS GLOBAL
# ─────────────────────────────────────────────────
def render_lcs_global(data):
    st.markdown('<p class="section-header">🧭 Sistemas de Coordenadas Locales (LCS)</p>', unsafe_allow_html=True)
    nm={n.get("Id"):n for n in data.get("PointConnections",[])}
    st.info(f"""**Verificacion geometrica:** Se calculan los ejes locales reales desde la geometria del elemento 
y se comparan con el vector `(LCSX, LCSY, LCSZ)` declarado en el JSON.  
Tolerancia de alineacion: **{ANGLE_TOL_DEG}°**  
**Superficies:** Z local = normal al plano | Si LCS=1 → X debe coincidir con vector | Si LCS=2 → Y debe coincidir  
**Barras:** X local = n1→n2 | Si LCS=0 → Y debe coincidir con vector | Si LCS=1 → Z debe coincidir""")

    tab_surf,tab_bars=st.tabs(["🧩 Losas / Superficies","🔩 Barras"])

    with tab_surf:
        surfs=data.get("SurfaceMembers",[])
        if not surfs: st.info("No hay superficies.")
        else:
            rows=[]
            for s in surfs:
                lcs=compute_surface_lcs(s, nm)
                status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
                lcs_type=s.get("LCS",0) or 0
                rows.append({"Nombre":s.get("Name",""),
                    "Tipo":SURFACE_TYPE.get(s.get("Type",0),"?"),
                    "LCS enum":lcs_type,
                    "Eje verificado":"X" if lcs_type==1 else ("Y" if lcs_type==2 else "—"),
                    "Vector JSON":fmt_vec(s) if has_lcs_vector(s) else "—",
                    "X local":fmt_axis(lcs["x"]) if lcs else "—",
                    "Y local":fmt_axis(lcs["y"]) if lcs else "—",
                    "Z local (normal)":fmt_axis(lcs["z"]) if lcs else "—",
                    "Rot (deg)":f"{s.get('LCSRotation'):.2f}" if s.get("LCSRotation") is not None else "—",
                    "Estado":_status_label(status),
                    "Angulo error (deg)":f"{angle:.2f}" if angle is not None else "—"})
            df=pd.DataFrame(rows)
            ok=len(df[df["Estado"]=="✅ OK"]); err=len(df[df["Estado"]=="❌ Error"]); dft=len(df[df["Estado"]=="🔵 Default"])
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Total",len(df)); c2.metric("OK",ok); c3.metric("Error",err); c4.metric("Default",dft)
            filt=st.radio("Mostrar:",["Todas","OK","Error","Default"],horizontal=True,key="glcs_surf")
            if filt=="OK": df=df[df["Estado"]=="✅ OK"]
            elif filt=="Error": df=df[df["Estado"]=="❌ Error"]
            elif filt=="Default": df=df[df["Estado"]=="🔵 Default"]
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_bars:
        bars=data.get("CurveMembers",[])
        if not bars: st.info("No hay barras.")
        else:
            rows=[]
            for b in bars:
                lcs=compute_bar_lcs(b, nm)
                status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
                lcs_type=b.get("LCS")
                rows.append({"Nombre":b.get("Name",""),
                    "Tipo":CURVE_TYPE.get(b.get("Type",0),"?"),
                    "LCS enum":lcs_type if lcs_type is not None else "—",
                    "Eje verificado":"Y" if lcs_type in (0,2) else ("Z" if lcs_type in (1,3) else "—"),
                    "Vector JSON":fmt_vec(b) if has_lcs_vector(b) else "—",
                    "X local (n1→n2)":fmt_axis(lcs["x"]) if lcs else "—",
                    "Y local":fmt_axis(lcs["y"]) if lcs else "—",
                    "Z local":fmt_axis(lcs["z"]) if lcs else "—",
                    "Estado":_status_label(status),
                    "Angulo error (deg)":f"{angle:.2f}" if angle is not None else "—"})
            df=pd.DataFrame(rows)
            ok=len(df[df["Estado"]=="✅ OK"]); err=len(df[df["Estado"]=="❌ Error"]); dft=len(df[df["Estado"]=="🔵 Default"])
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Total",len(df)); c2.metric("OK",ok); c3.metric("Error",err); c4.metric("Default",dft)
            filt=st.radio("Mostrar:",["Todas","OK","Error","Default"],horizontal=True,key="glcs_bar")
            if filt=="OK": df=df[df["Estado"]=="✅ OK"]
            elif filt=="Error": df=df[df["Estado"]=="❌ Error"]
            elif filt=="Default": df=df[df["Estado"]=="🔵 Default"]
            st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────
# VALIDACION
# ─────────────────────────────────────────────────
def render_validation(data):
    st.markdown('<p class="section-header">✅ Validacion</p>', unsafe_allow_html=True)
    mat_ids=set(m.get("Id") for m in data.get("Materials",[]))
    cs_ids=set(s.get("Id") for s in data.get("CrossSections",[]))
    node_ids=set(n.get("Id") for n in data.get("PointConnections",[]))
    bar_ids=set(b.get("Id") for b in data.get("CurveMembers",[]))
    surf_ids=set(s.get("Id") for s in data.get("SurfaceMembers",[]))
    lc_ids=set(c.get("Id") for c in data.get("LoadCases",[]))
    combo_ids=set(c.get("Id") for c in data.get("LoadCombinations",[]))
    all_load_ids=lc_ids|combo_ids
    nm={n.get("Id"):n for n in data.get("PointConnections",[])}

    issues=[]; warns=[]

    for cs in data.get("CrossSections",[]):
        for mid in cs.get("Materials",[]):
            if mid not in mat_ids: issues.append(f"Seccion '{cs.get('Name','')}' → material '{mid[:12]}' no existe")
    for b in data.get("CurveMembers",[]):
        if b.get("CrossSection","") and b.get("CrossSection","") not in cs_ids:
            issues.append(f"Barra '{b.get('Name','')}' → seccion no existe")
        for nid in b.get("Nodes",[]):
            if nid not in node_ids: issues.append(f"Barra '{b.get('Name','')}' → nodo '{nid}' no existe")
    for s in data.get("SurfaceMembers",[]):
        for nid in s.get("Nodes",[]):
            if nid not in node_ids: issues.append(f"Superficie '{s.get('Name','')}' → nodo '{nid}' no existe")
        for mid in s.get("Materials",[]):
            if mid not in mat_ids: issues.append(f"Superficie '{s.get('Name','')}' → material no existe")
    for r in data.get("SurfaceMemberRegions",[]):
        if r.get("Surface","") and r.get("Surface","") not in surf_ids:
            issues.append(f"Region '{r.get('Name','')}' → superficie no existe")
    for o in data.get("SurfaceMemberOpenings",[]):
        if o.get("Surface","") and o.get("Surface","") not in surf_ids:
            issues.append(f"Abertura '{o.get('Name','')}' → superficie no existe")
    for sup in data.get("PointSupports",[]):
        if sup.get("Node","") and sup.get("Node","") not in node_ids:
            issues.append(f"Apoyo '{sup.get('Name','')}' → nodo no existe")
    for a in data.get("CurveActions",[]):
        if a.get("CurveMember","") and a.get("CurveMember","") not in bar_ids:
            issues.append(f"Accion lineal '{a.get('Name','')}' → barra no existe")
    for a in data.get("SurfaceActions",[]):
        if a.get("SurfaceElement","") and a.get("SurfaceElement","") not in surf_ids:
            issues.append(f"Accion sup '{a.get('Name','')}' → superficie no existe")

    # Verificacion LCS geometrica
    lcs_surf_errors=[]
    for s in data.get("SurfaceMembers",[]):
        if has_lcs_vector(s):
            lcs=compute_surface_lcs(s, nm)
            status,angle=check_surface_lcs(s,lcs) if lcs else ("default",None)
            if status=="error":
                issues.append(f"LCS Superficie '{s.get('Name','')}': error angular {angle:.1f}° > {ANGLE_TOL_DEG}°")
                lcs_surf_errors.append(s.get("Name",""))

    lcs_bar_errors=[]
    for b in data.get("CurveMembers",[]):
        if has_lcs_vector(b):
            lcs=compute_bar_lcs(b, nm)
            status,angle=check_bar_lcs(b,lcs) if lcs else ("default",None)
            if status=="error":
                issues.append(f"LCS Barra '{b.get('Name','')}': error angular {angle:.1f}° > {ANGLE_TOL_DEG}°")
                lcs_bar_errors.append(b.get("Name",""))

    z1=sum(1 for r in data.get("Results1D",[]) if nz_ratio_1d(r)==0)
    if z1: warns.append(f"Results1D: {z1}/{len(data.get('Results1D',[]))} vacios")
    zm=sum(1 for r in data.get("MeshResults",[]) if nz_ratio_mesh(r)==0)
    if zm: warns.append(f"MeshResults: {zm}/{len(data.get('MeshResults',[]))} vacios")
    no_cs=[b.get("Name","?") for b in data.get("CurveMembers",[]) if not b.get("CrossSection")]
    if no_cs: warns.append(f"{len(no_cs)} barras sin seccion")
    no_thick=[s.get("Name","?") for s in data.get("SurfaceMembers",[]) if not s.get("Thickness") or s.get("Thickness",0)==0]
    if no_thick: warns.append(f"{len(no_thick)} superficies sin espesor")
    empty_ents=[k for k,v in data.items() if isinstance(v,list) and len(v)==0]
    if empty_ents: warns.append(f"Entidades vacias: {', '.join(empty_ents)}")

    if not issues and not warns: st.success("Sin problemas detectados.")
    if issues:
        st.error(f"🔴 {len(issues)} errores")
        with st.expander(f"Ver errores ({len(issues)})", expanded=len(issues)<=20):
            for i in issues[:60]: st.markdown(f"- {i}")
            if len(issues)>60: st.markdown(f"_... y {len(issues)-60} mas_")
    if warns:
        st.warning(f"🟡 {len(warns)} advertencias")
        with st.expander(f"Ver advertencias ({len(warns)})"):
            for w in warns: st.markdown(f"- {w}")

    st.markdown("---")
    st.markdown("#### Integridad de Referencias")
    surf_lcs_total=sum(1 for s in data.get("SurfaceMembers",[]) if has_lcs_vector(s))
    bar_lcs_total =sum(1 for b in data.get("CurveMembers",[]) if has_lcs_vector(b))
    ref_checks=[
        ("Secciones → Materiales",len(data.get("CrossSections",[])),
         sum(1 for cs in data.get("CrossSections",[]) if all(m in mat_ids for m in cs.get("Materials",[])))),
        ("Barras → Nodos",len(data.get("CurveMembers",[])),
         sum(1 for b in data.get("CurveMembers",[]) if all(n in node_ids for n in b.get("Nodes",[])))),
        ("Superficies → Nodos",len(data.get("SurfaceMembers",[])),
         sum(1 for s in data.get("SurfaceMembers",[]) if all(n in node_ids for n in s.get("Nodes",[])))),
        ("Apoyos → Nodos",len(data.get("PointSupports",[])),
         sum(1 for s in data.get("PointSupports",[]) if s.get("Node","") in node_ids)),
        (f"LCS Superficies OK (tol {ANGLE_TOL_DEG}°)",surf_lcs_total,surf_lcs_total-len(lcs_surf_errors)),
        (f"LCS Barras OK (tol {ANGLE_TOL_DEG}°)",bar_lcs_total,bar_lcs_total-len(lcs_bar_errors)),
    ]
    rows=[]
    for name,total,ok in ref_checks:
        if total==0: status,pct="⬜","—"
        elif ok==total: status,pct="✅","100%"
        else: status,pct="❌",f"{ok}/{total} ({100*ok//total}%)"
        rows.append({"Referencia":name,"Estado":status,"Validas":pct})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_raw_json(data):
    st.markdown('<p class="section-header">🔍 JSON</p>', unsafe_allow_html=True)
    keys=[k for k in data.keys() if isinstance(data[k],list)]
    sk=st.selectbox("Entidad",keys)
    items=data.get(sk,[])
    if items:
        if len(items)>1:
            idx=st.slider("Indice",0,len(items)-1,0)
        else:
            idx=0
            st.caption("1 elemento")
        st.json(items[idx])


# ─────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────
st.markdown("# 🏗️ JSAF Auditor")
st.markdown("Auditoria visual de modelos estructurales en formato JSAF")
uploaded=st.file_uploader("Cargar archivo JSAF (.json)",type=["json"])

if uploaded:
    data=load_json(uploaded)
    tabs=st.tabs(["📊 Resumen","🧱 Materiales","📐 Secciones","📍 Modelo 3D","🔩 Barras",
                   "🧩 Superficies","📌 Apoyos","⚡ Cargas","🎯 Acciones",
                   "📈 Results 1D","🔺 Malla 2D","🧭 LCS","✅ Validacion","🔍 JSON"])
    with tabs[0]:  render_overview(data)
    with tabs[1]:  render_materials(data)
    with tabs[2]:  render_cross_sections(data)
    with tabs[3]:  render_3d_model(data)
    with tabs[4]:  render_bars(data)
    with tabs[5]:  render_surfaces(data)
    with tabs[6]:  render_supports(data)
    with tabs[7]:  render_loads(data)
    with tabs[8]:  render_actions(data)
    with tabs[9]:  render_results_1d(data)
    with tabs[10]: render_mesh_results(data)
    with tabs[11]: render_lcs_global(data)
    with tabs[12]: render_validation(data)
    with tabs[13]: render_raw_json(data)
else:
    st.info("Sube un archivo JSAF (.json) para comenzar.")
