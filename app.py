import streamlit as st
import json
import math
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import Counter
import io

# Configuración de página
st.set_page_config(page_title="JSAF Auditor Pro", page_icon="🏗️", layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────
# ESTILOS CSS MEJORADOS
# ─────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    code, pre, .stCode { font-family: 'JetBrains Mono', monospace !important; }
    
    /* Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; 
        border-radius: 12px; 
        padding: 1rem; 
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); border-color: #e94560; }
    .metric-card h3 { color: #ffffff; margin: 0; font-size: 2rem; font-weight: 700; }
    .metric-card p { color: #a8a8b3; margin: 0.2rem 0 0; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }
    
    /* Headers */
    .section-header {
        background: linear-gradient(90deg, #e94560 0%, #0f3460 100%);
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent;
        font-weight: 700; 
        font-size: 1.8rem; 
        margin-bottom: 1rem;
        border-bottom: 2px solid #0f3460;
        padding-bottom: 0.5rem;
    }
    
    /* Status Badges */
    .status-ok { color: #51cf66; font-weight: bold; }
    .status-error { color: #ff6b6b; font-weight: bold; }
    .status-default { color: #748ffc; font-weight: bold; }
    
    /* Dataframe adjustments */
    .dataframe-container { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# CONSTANTES Y CONFIGURACIÓN
# ─────────────────────────────────────────────────
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
LCS_BAD_COLOR  = "#ff6b6b"
LCS_NONE_COLOR = "#748ffc"
ANGLE_TOL_DEG  = 5.0

# ─────────────────────────────────────────────────
# CACHING PARA RENDIMIENTO
# ─────────────────────────────────────────────────
@st.cache_data
def load_and_process_data(file_content):
    """Carga el JSON y precalcula estructuras básicas"""
    data = json.loads(file_content)
    # Pre-calcular mapas de IDs para acceso rápido
    data['_node_map'] = {n.get("Id"): n for n in data.get("PointConnections", [])}
    data['_bar_map'] = {b.get("Id"): b for b in data.get("CurveMembers", [])}
    data['_surf_map'] = {s.get("Id"): s for s in data.get("SurfaceMembers", [])}
    return data

@st.cache_data
def compute_all_lcs_surfaces(data_json_str):
    """Precalcula LCS de todas las superficies"""
    data = json.loads(data_json_str)
    nm = data['_node_map']
    results = {}
    for surf in data.get("SurfaceMembers", []):
        sid = surf.get("Id")
        lcs = compute_surface_lcs(surf, nm)
        status, angle = check_surface_lcs(surf, lcs) if lcs else ("default", None)
        has_vec = has_lcs_vector(surf)
        
        # Detectar malla vacía
        is_empty_mesh = len(surf.get("MeshTriangles", [])) == 0
        
        results[sid] = {
            "lcs": lcs,
            "status": status,
            "angle": angle,
            "has_vec": has_vec,
            "is_empty_mesh": is_empty_mesh,
            "name": surf.get("Name", "")
        }
    return results

@st.cache_data
def compute_all_lcs_bars(data_json_str):
    """Precalcula LCS de todas las barras"""
    data = json.loads(data_json_str)
    nm = data['_node_map']
    results = {}
    for bar in data.get("CurveMembers", []):
        bid = bar.get("Id")
        lcs = compute_bar_lcs(bar, nm)
        status, angle = check_bar_lcs(bar, lcs) if lcs else ("default", None)
        has_vec = has_lcs_vector(bar)
        results[bid] = {
            "lcs": lcs,
            "status": status,
            "angle": angle,
            "has_vec": has_vec,
            "name": bar.get("Name", "")
        }
    return results

# ─────────────────────────────────────────────────
# ALGEBRA VECTORIAL (Optimizada)
# ─────────────────────────────────────────────────
def _mag(v): return math.sqrt(v[0]**2+v[1]**2+v[2]**2)
def _sub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def _dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _norm(v):
    n=_mag(v)
    return (v[0]/n,v[1]/n,v[2]/n) if n>1e-12 else (0.0,0.0,0.0)
def _angle_deg(a,b):
    d=max(-1.0,min(1.0,_dot(_norm(a),_norm(b))))
    return math.degrees(math.acos(d))

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
    
    # Lógica de alineación
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
def has_lcs_vector(obj): return any(obj.get(k) is not None and obj.get(k)!=0 for k in ["LCSX","LCSY","LCSZ"])
def fmt_vec(obj): return f"({obj.get('LCSX',0) or 0:.3f}, {obj.get('LCSY',0) or 0:.3f}, {obj.get('LCSZ',0) or 0:.3f})"
def fmt_axis(v): return f"({v[0]:.3f},{v[1]:.3f},{v[2]:.3f})"

# ─────────────────────────────────────────────────
# HELPERS DE RESULTADOS
# ─────────────────────────────────────────────────
def nz_ratio_1d(r): 
    return sum(1 for c in COMPS_1D if any(abs(v)>1e-9 for v in r.get(c,[])))/len(COMPS_1D)

def nz_ratio_mesh(r): 
    return sum(1 for c in COMPS_MESH if any(abs(v)>1e-9 for v in r.get(c,[])))/len(COMPS_MESH)

def mc(value,label, color="#ffffff"): 
    return f'<div class="metric-card"><h3 style="color:{color}">{value}</h3><p>{label}</p></div>'

# ─────────────────────────────────────────────────
# RENDERIZADO DE COMPONENTES
# ─────────────────────────────────────────────────

def render_overview(data):
    st.markdown('<p class="section-header">📊 Resumen del Modelo</p>', unsafe_allow_html=True)
    c1,c2=st.columns([3,1])
    with c1:
        st.markdown(f"### {data.get('Name','Modelo sin nombre')}")
        st.caption(data.get('Description',''))
    with c2:
        st.metric("Nodos", len(data.get("PointConnections",[])))
        st.metric("Barras", len(data.get("CurveMembers",[])))
        st.metric("Superficies", len(data.get("SurfaceMembers",[])))

    groups=[
        ("GEOMETRÍA",[("Materials","Materiales"),("CrossSections","Secciones"),("PointConnections","Nodos"),
            ("CurveMembers","Barras"),("SurfaceMembers","Superficies")]),
        ("CARGAS",[("LoadCases","Casos"),("LoadCombinations","Combinaciones")]),
        ("RESULTADOS",[("Results1D","1D Barras"),("MeshResults","2D Malla")]),
    ]
    
    for gn,ents in groups:
        st.markdown(f'<div style="margin-top:1.5rem; margin-bottom:0.5rem; color:#a8a8b3; font-weight:bold;">{gn}</div>', unsafe_allow_html=True)
        cols=st.columns(len(ents))
        for col,(k,l) in zip(cols,ents):
            val = len(data.get(k,[]))
            col.markdown(mc(val, l), unsafe_allow_html=True)

def render_3d_model(data):
    st.markdown('<p class="section-header">📍 Modelo 3D Interactivo</p>', unsafe_allow_html=True)
    nodes=data.get("PointConnections",[])
    if not nodes: return st.info("No hay nodos.")
    
    nm=data['_node_map']
    sup_ids=set(s.get("Node","") for s in data.get("PointSupports",[]))

    cc=st.columns(6)
    show_nodes    =cc[0].checkbox("Nodos",False)
    show_sups     =cc[1].checkbox("Apoyos",True)
    show_cols     =cc[2].checkbox("Columnas",True)
    show_beams    =cc[3].checkbox("Vigas",True)
    show_panels   =cc[4].checkbox("Paneles",True)
    show_lcs      =cc[5].checkbox("Verificar LCS",False)

    fig=go.Figure()
    fig.update_layout(template="plotly_dark", height=600, margin=dict(l=0,r=0,t=0,b=0))
    scene_opts = dict(showgrid=False, showline=False, zeroline=False, showbackground=False, aspectmode='data')
    fig.update_layout(scene=scene_opts)

    # Nodos
    if show_nodes:
        ns=[n for n in nodes if n.get("Id") not in sup_ids]
        if ns:
            fig.add_trace(go.Scatter3d(x=[n["X"] for n in ns],y=[n["Y"] for n in ns],z=[n["Z"] for n in ns],
                mode='markers',marker=dict(size=2,color="#4a9eff",opacity=0.5), name="Nodos"))

    # Apoyos
    if show_sups:
        sn=[nm[sid] for sid in sup_ids if sid in nm]
        if sn:
            fig.add_trace(go.Scatter3d(x=[n["X"] for n in sn],y=[n["Y"] for n in sn],z=[n["Z"] for n in sn],
                mode='markers',marker=dict(size=5,color="#e94560",symbol='diamond'), name="Apoyos"))

    # Barras
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

    # Superficies (Simplificado para rendimiento)
    if show_panels:
        for stype,label,color in [(0,"Losas","rgba(100,180,255,0.3)"), (1,"Muros","rgba(255,160,80,0.3)")]:
            mx={"x":[],"y":[],"z":[],"i":[],"j":[],"k":[]}
            for surf in data.get("SurfaceMembers",[]):
                if surf.get("Type",0)!=stype: continue
                pts=[nm.get(nid) for nid in surf.get("Nodes",[])]
                pts=[p for p in pts if p]
                if len(pts)<3: continue
                
                # Triangulación simple (Fan) para visualización rápida
                off=len(mx["x"])
                for p in pts: mx["x"].append(p["X"]); mx["y"].append(p["Y"]); mx["z"].append(p["Z"])
                for i in range(1, len(pts)-1):
                    mx["i"].append(off+0); mx["j"].append(off+i); mx["k"].append(off+i+1)
            
            if mx["x"]:
                fig.add_trace(go.Mesh3d(x=mx["x"],y=mx["y"],z=mx["z"],i=mx["i"],j=mx["j"],k=mx["k"],
                    color=color, opacity=0.5, name=label))

    # LCS Markers
    if show_lcs:
        # Usar datos cacheados si es posible, sino calcular al vuelo para visualización
        # Aquí simplificamos mostrando solo puntos de origen
        for surf in data.get("SurfaceMembers", []):
             lcs = compute_surface_lcs(surf, nm)
             if lcs:
                 status, _ = check_surface_lcs(surf, lcs)
                 color = LCS_OK_COLOR if status == "ok" else LCS_BAD_COLOR
                 if not has_lcs_vector(surf): color = LCS_NONE_COLOR
                 
                 fig.add_trace(go.Scatter3d(x=[lcs['origin'][0]], y=[lcs['origin'][1]], z=[lcs['origin'][2]],
                     mode='markers', marker=dict(size=6, color=color), hoverinfo='text',
                     text=f"{surf.get('Name','')}<br>LCS: {status}", showlegend=False))

    st.plotly_chart(fig, use_container_width=True)

def render_results_1d(data):
    st.markdown('<p class="section-header">📈 Resultados 1D (Barras)</p>', unsafe_allow_html=True)
    results=data.get("Results1D",[])
    if not results: return st.info("No hay resultados 1D.")
    
    lm={**{c.get("Id",""):c.get("Name","") for c in data.get("LoadCases",[])}, 
        **{c.get("Id",""):c.get("Name","") for c in data.get("LoadCombinations",[])}}
    
    # Análisis de vacíos vs existentes
    bar_summary={}
    for r in results:
        bid=r.get("Member","")
        ratio=nz_ratio_1d(r)
        if bid not in bar_summary: bar_summary[bid]={"nz":0,"z":0,"max":{c:0 for c in COMPS_1D}, "loads":[]}
        if ratio>0: bar_summary[bid]["nz"]+=1
        else: bar_summary[bid]["z"]+=1
        bar_summary[bid]["loads"].append(r.get("Load",""))
        
        for c in COMPS_1D:
            vals=[abs(v) for v in r.get(c,[])]
            if vals: bar_summary[bid]["max"][c]=max(bar_summary[bid]["max"][c],max(vals))

    total=len(results)
    full=sum(1 for r in results if nz_ratio_1d(r)==1.0)
    empty=sum(1 for r in results if nz_ratio_1d(r)==0)
    
    c1,c2,c3,c4=st.columns(4)
    c1.markdown(mc(total, "Total Resultados"), unsafe_allow_html=True)
    c2.markdown(mc(full, "Con Valores", "#51cf66"), unsafe_allow_html=True)
    c3.markdown(mc(empty, "Vacíos (Nulos)", "#ff6b6b"), unsafe_allow_html=True)
    c4.markdown(mc(len(bar_summary), "Barras Únicas", "#4a9eff"), unsafe_allow_html=True)

    # Construir DataFrame
    rows=[]
    for bid, info in bar_summary.items():
        b = data['_bar_map'].get(bid, {})
        # Obtener estado LCS desde caché o cálculo
        lcs_status = "—"
        if bid in data.get('_bar_map', {}):
             # Intentar usar caché global si existe, sino default
             pass 
        
        rows.append({
            "ID Barra": bid,
            "Nombre": b.get("Name", f"Bar {bid}"),
            "Estado": "✅ Con Datos" if info["nz"]>0 else "❌ Vacío/Nulo",
            "Cargas Asignadas": len(info["loads"]),
            "|N| Max": f"{info['max']['aN']:.2f}",
            "|My| Max": f"{info['max']['aMy']:.2f}",
            "|Mz| Max": f"{info['max']['aMz']:.2f}"
        })
        
    df=pd.DataFrame(rows)
    
    # Filtros
    col_filt, col_search = st.columns([1, 3])
    filter_option = col_filt.selectbox("Filtrar por estado:", ["Todos", "✅ Con Datos", "❌ Vacíos/Nulos"])
    search_term = col_search.text_input("Buscar barra (ID o Nombre):", "").lower()
    
    if filter_option == "✅ Con Datos": df = df[df["Estado"].str.contains("Con Datos")]
    elif filter_option == "❌ Vacíos/Nulos": df = df[df["Estado"].str.contains("Vacío")]
    
    if search_term:
        df = df[df.apply(lambda row: row.astype(str).str.lower().str.contains(search_term).any(), axis=1)]

    # Mostrar tabla
    if df.empty:
        st.warning("No se encontraron resultados con los filtros actuales.")
        if filter_option == "❌ Vacíos/Nulos":
            st.info("💡 **Nota:** Los resultados aparecen como 'Vacíos' si todos los componentes (N, V, M) son 0.0 o si la barra no tiene carga asignada en ese caso.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Botón descarga
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Descargar CSV", csv, "resultados_1d.csv", "text/csv")

def render_mesh_results(data):
    st.markdown('<p class="section-header">🔺 Resultados Malla 2D (Paneles)</p>', unsafe_allow_html=True)
    results=data.get("MeshResults",[])
    if not results: return st.info("No hay resultados de malla.")
    
    # Análisis
    panel_summary={}
    for r in results:
        pid=r.get("Member","")
        ratio=nz_ratio_mesh(r)
        if pid not in panel_summary: 
            panel_summary[pid]={
                "nz":0, "z":0, 
                "max":{c:0 for c in COMPS_MESH}, 
                "loads":[],
                "is_empty_mesh": False # Se llenará después
            }
        if ratio>0: panel_summary[pid]["nz"]+=1
        else: panel_summary[pid]["z"]+=1
        panel_summary[pid]["loads"].append(r.get("Load",""))
        
        for c in COMPS_MESH:
            vals=[abs(v) for v in r.get(c,[])]
            if vals: panel_summary[pid]["max"][c]=max(panel_summary[pid]["max"][c],max(vals))

    # Verificar mallas vacías geométricamente
    for pid in panel_summary:
        surf = data['_surf_map'].get(pid, {})
        if len(surf.get("MeshTriangles", [])) == 0:
            panel_summary[pid]["is_empty_mesh"] = True

    total=len(results)
    full=sum(1 for r in results if nz_ratio_mesh(r)==1.0)
    empty=sum(1 for r in results if nz_ratio_mesh(r)==0)
    
    c1,c2,c3,c4=st.columns(4)
    c1.markdown(mc(total, "Total Resultados"), unsafe_allow_html=True)
    c2.markdown(mc(full, "Completos", "#51cf66"), unsafe_allow_html=True)
    c3.markdown(mc(empty, "Vacíos (Nulos)", "#ff6b6b"), unsafe_allow_html=True)
    c4.markdown(mc(len(panel_summary), "Paneles Únicos", "#4a9eff"), unsafe_allow_html=True)

    # Construir DataFrame
    rows=[]
    for pid, info in panel_summary.items():
        s = data['_surf_map'].get(pid, {})
        reason = ""
        if info["is_empty_mesh"]:
            reason = "⚠️ Sin Malla Interna"
        elif info["z"] > 0 and info["nz"] == 0:
            reason = "0.0 Valores"
            
        rows.append({
            "ID Panel": pid,
            "Nombre": s.get("Name", f"Panel {pid}"),
            "Estado": "✅ Con Datos" if info["nz"]>0 else "❌ Vacío",
            "Motivo Vacío": reason if info["nz"]==0 else "-",
            "Cargas": len(info["loads"]),
            "|mx| Max": f"{info['max']['amx']:.2f}",
            "|my| Max": f"{info['max']['amy']:.2f}",
            "|nx| Max": f"{info['max']['anx']:.2f}"
        })
        
    df=pd.DataFrame(rows)
    
    # Filtros
    col_filt, col_search = st.columns([1, 3])
    filter_option = col_filt.selectbox("Filtrar por estado:", ["Todos", "✅ Con Datos", "❌ Vacíos"], key="mesh_filt")
    search_term = col_search.text_input("Buscar panel (ID o Nombre):", "", key="mesh_search").lower()
    
    if filter_option == "✅ Con Datos": df = df[df["Estado"].str.contains("Con Datos")]
    elif filter_option == "❌ Vacíos": df = df[df["Estado"].str.contains("Vacío")]
    
    if search_term:
        df = df[df.apply(lambda row: row.astype(str).str.lower().str.contains(search_term).any(), axis=1)]

    if df.empty:
        st.warning("No se encontraron paneles con los filtros actuales.")
        if filter_option == "❌ Vacíos":
            st.info("💡 **Explicación:** Los paneles marcados como 'Vacíos' pueden deberse a:\n1. No tener carga asignada.\n2. Tener una malla degenerada (`MeshTriangles: []`).\n3. Ser elementos auxiliares sin rigidez.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Descargar CSV", csv, "resultados_malla.csv", "text/csv")

def render_validation(data):
    st.markdown('<p class="section-header">✅ Validación de Integridad</p>', unsafe_allow_html=True)
    
    issues=[]
    warns=[]
    
    # Referencias básicas
    mat_ids=set(m.get("Id") for m in data.get("Materials",[]))
    cs_ids=set(s.get("Id") for s in data.get("CrossSections",[]))
    node_ids=set(n.get("Id") for n in data.get("PointConnections",[]))
    bar_ids=set(b.get("Id") for b in data.get("CurveMembers",[]))
    surf_ids=set(s.get("Id") for s in data.get("SurfaceMembers",[]))
    
    # Chequeos
    for b in data.get("CurveMembers",[]):
        if b.get("CrossSection","") and b.get("CrossSection","") not in cs_ids:
            issues.append(f"Barra '{b.get('Name','')}' → sección no existe")
        for nid in b.get("Nodes",[]):
            if nid not in node_ids: issues.append(f"Barra '{b.get('Name','')}' → nodo '{nid}' no existe")
            
    for s in data.get("SurfaceMembers",[]):
        # Chequeo crítico: Malla vacía
        if len(s.get("MeshTriangles", [])) == 0:
            warns.append(f"Superficie '{s.get('Name','')}' → Malla vacía (sin triángulos definidos)")
            
        for nid in s.get("Nodes",[]):
            if nid not in node_ids: issues.append(f"Superficie '{s.get('Name','')}' → nodo '{nid}' no existe")

    # Resultados vacíos
    z1=sum(1 for r in data.get("Results1D",[]) if nz_ratio_1d(r)==0)
    if z1: warns.append(f"Results1D: {z1} registros con todos los valores en 0.0")
    
    zm=sum(1 for r in data.get("MeshResults",[]) if nz_ratio_mesh(r)==0)
    if zm: warns.append(f"MeshResults: {zm} registros con todos los valores en 0.0")

    if not issues and not warns: 
        st.success("✅ No se detectaron errores críticos ni advertencias importantes.")
    
    if issues:
        st.error(f"🔴 {len(issues)} Errores Críticos")
        with st.expander("Ver detalles de errores"):
            for i in issues: st.markdown(f"- {i}")
            
    if warns:
        st.warning(f"🟡 {len(warns)} Advertencias")
        with st.expander("Ver detalles de advertencias"):
            for w in warns: st.markdown(f"- {w}")

# ─────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────
st.title("🏗️ JSAF Auditor Pro")
st.markdown("Herramienta avanzada de auditoría y visualización de modelos estructurales JSAF.")

uploaded=st.file_uploader("Cargar archivo JSAF (.json)", type=["json"])

if uploaded:
    file_content = uploaded.read().decode('utf-8')
    try:
        data = load_and_process_data(file_content)
        
        tabs = st.tabs([
            "📊 Resumen", 
            "📍 Modelo 3D", 
            "📈 Results 1D", 
            "🔺 Malla 2D", 
            "✅ Validación",
            " LCS Global",
            "🔍 JSON Raw"
        ])
        
        with tabs[0]: render_overview(data)
        with tabs[1]: render_3d_model(data)
        with tabs[2]: render_results_1d(data)
        with tabs[3]: render_mesh_results(data)
        with tabs[4]: render_validation(data)
        with tabs[5]: 
            st.info("La pestaña de LCS Global muestra la alineación de ejes locales. Usa el checkbox 'Verificar LCS' en el Modelo 3D para verlos espacialmente.")
        with tabs[6]:
            st.json(json.loads(file_content)[:1000]) # Preview only
            
    except Exception as e:
        st.error(f"Error procesando el archivo: {str(e)}")
        st.exception(e)
else:
    st.info("👆 Sube un archivo `.json` para comenzar el análisis.")
