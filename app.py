import streamlit as st
import json
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
    border: 1px solid #0f3460; border-radius: 12px; padding: 1rem;
    text-align: center;
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

MATERIAL_TYPE = {0: "Other", 1: "Concrete", 2: "Steel", 3: "Timber", 4: "Aluminium", 5: "Masonry"}
CS_SHAPE = {0: "Circle", 1: "Rectangle", 6: "I Section", 9: "T Section", 14: "U Section", 16: "Pipe"}
CS_TYPE = {0: "Parametric", 1: "Manufactured", 2: "Compound", 3: "General"}
CURVE_TYPE = {0: "General", 1: "Beam", 2: "Column", 10: "SlabRib"}
SURFACE_TYPE = {0: "Plate", 1: "Wall", 2: "Shell", 3: "Ribbed Slab"}
SUPPORT_TRANS = {0: "Free", 1: "Rigid", 2: "Flexible", 3: "Comp. Only", 4: "Tension Only"}
SUPPORT_ROT = {0: "Free", 1: "Rigid", 2: "Flexible"}
ACTION_TYPE_LC = {0: "Permanent", 1: "Variable", 2: "Accidental"}
LOAD_TYPE = {0: "Self Weight", 1: "Others", 2: "Prestress", 3: "Dynamic", 4: "Static", 5: "Temperature", 6: "Wind", 7: "Snow", 8: "Maintenance", 9: "Fire", 10: "Moving", 11: "Seismic", 12: "Standard"}
COMB_CATEGORY = {0: "Undefined", 1: "ULS", 2: "SLS", 3: "ALS", 4: "National Std"}
COORD_SYS = {0: "Global", 1: "Local"}
DISTRIBUTION = {0: "Uniform", 1: "Trapezoidal"}
PLOT_COLORS = ["#e94560", "#4a9eff", "#51cf66", "#ffd43b", "#cc5de8", "#ff922b"]

COMPS_1D = ['aN', 'aVy', 'aVz', 'aMx', 'aMy', 'aMz']
COMPS_MESH = ['amx', 'amy', 'amxy', 'avx', 'avy', 'anx', 'any', 'anxy']


def load_json(file):
    return json.load(file)

def mc(value, label):
    return f'<div class="metric-card"><h3>{value}</h3><p>{label}</p></div>'

def id_name_map(items):
    return {it.get("Id", ""): it.get("Name", it.get("Id", "?")) for it in (items or [])}

def nz_ratio_1d(r):
    total = len(COMPS_1D)
    nz = sum(1 for c in COMPS_1D if any(abs(v) > 1e-6 for v in r.get(c, [])))
    return nz / total

def nz_ratio_mesh(r):
    total = len(COMPS_MESH)
    nz = sum(1 for c in COMPS_MESH if any(abs(v) > 1e-6 for v in r.get(c, [])))
    return nz / total


# ═══════════════════════════════════════
# HELPERS 2D GEOMETRY
# ═══════════════════════════════════════
def project_to_2d(points_3d):
    if len(points_3d) < 3:
        return [(p[0], p[1]) for p in points_3d]
    p0, p1, p2 = points_3d[0], points_3d[1], points_3d[2]
    v1 = (p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2])
    v2 = (p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2])
    nx = abs(v1[1]*v2[2] - v1[2]*v2[1])
    ny = abs(v1[2]*v2[0] - v1[0]*v2[2])
    nz = abs(v1[0]*v2[1] - v1[1]*v2[0])
    if nz >= nx and nz >= ny:
        return [(p[0], p[1]) for p in points_3d]
    elif ny >= nx:
        return [(p[0], p[2]) for p in points_3d]
    else:
        return [(p[1], p[2]) for p in points_3d]

def point_in_polygon_2d(px, py, polygon):
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ═══════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════
def render_overview(data):
    st.markdown('<p class="section-header">📊 Resumen del Modelo</p>', unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    c1.markdown(f"### {data.get('Name', 'N/A')}")
    c2.markdown(f"`{data.get('Description', '')}`")

    groups = [
        ("GEOMETRÍA", [("Materials","Materiales"),("CrossSections","Secciones"),("PointConnections","Nodos"),
            ("CurveMembers","Barras"),("SurfaceMembers","Superficies"),("SurfaceMemberOpenings","Aberturas"),
            ("SurfaceMemberRegions","Regiones"),("PointSupports","Apoyos")]),
        ("CARGAS", [("LoadCases","Casos"),("LoadCombinations","Combinaciones"),
            ("PointActions","Puntuales"),("CurveActions","Lineales"),("SurfaceActions","Superficiales")]),
        ("RESULTADOS", [("Results1D","1D Barras"),("MeshResults","2D Malla"),("Macros","Macros")]),
    ]
    for gn, ents in groups:
        st.markdown(f'<p class="group-label">{gn}</p>', unsafe_allow_html=True)
        cols = st.columns(len(ents))
        for col, (k, l) in zip(cols, ents):
            col.markdown(mc(len(data.get(k, [])), l), unsafe_allow_html=True)


# ═══════════════════════════════════════
# MATERIALES
# ═══════════════════════════════════════
def render_materials(data):
    st.markdown('<p class="section-header">🧱 Materiales</p>', unsafe_allow_html=True)
    mats = data.get("Materials", [])
    if not mats: return st.info("No hay materiales.")
    rows = []
    for m in mats:
        mt = m.get("Type", 0)
        row = {"Nombre": m.get("Name",""), "Tipo": MATERIAL_TYPE.get(mt, str(mt)),
               "E (MPa)": f"{m.get('EModulus',0)/1e6:.1f}" if m.get("EModulus",0)>1000 else f"{m.get('EModulus',0):.1f}",
               "G (MPa)": f"{m.get('GModulus',0)/1e6:.1f}" if m.get("GModulus",0)>1000 else f"{m.get('GModulus',0):.1f}",
               "ν": m.get("PoissonCoefficient",""),
               "ρ (kg/m³)": f"{m.get('UnitMass',0)/9.81:.0f}" if m.get("UnitMass",0)>100 else f"{m.get('UnitMass',0):.1f}"}
        if mt == 1: row["Fck (MPa)"] = f"{m.get('Fck',0)/1e6:.1f}" if m.get("Fck",0)>1000 else f"{m.get('Fck',0):.1f}"
        elif mt == 2:
            row["Fy (MPa)"] = f"{m.get('Fy',0)/1e6:.1f}" if m.get("Fy",0)>1000 else f"{m.get('Fy',0):.1f}"
            row["Fu (MPa)"] = f"{m.get('Fu',0)/1e6:.1f}" if m.get("Fu",0)>1000 else f"{m.get('Fu',0):.1f}"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════
# SECCIONES
# ═══════════════════════════════════════
def render_cross_sections(data):
    st.markdown('<p class="section-header">📐 Secciones</p>', unsafe_allow_html=True)
    secs = data.get("CrossSections", [])
    if not secs: return st.info("No hay secciones.")
    mm = id_name_map(data.get("Materials", []))
    rows = [{"Nombre": s.get("Name",""), "Tipo": CS_TYPE.get(s.get("Type",-1),"?"),
             "Forma": CS_SHAPE.get(s.get("Shape",-1), str(s.get("Shape",-1))),
             "Parámetros (m)": ", ".join(f"{p:.3f}" for p in s.get("Parameters",[])),
             "Material": ", ".join(mm.get(mid, mid[:8]) for mid in s.get("Materials",[]))} for s in secs]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════
# MODELO 3D
# ═══════════════════════════════════════
def render_3d_model(data):
    st.markdown('<p class="section-header">📍 Modelo 3D</p>', unsafe_allow_html=True)
    nodes = data.get("PointConnections", [])
    if not nodes: return st.info("No hay nodos.")
    nm = {n.get("Id"): n for n in nodes}
    sup_ids = set(s.get("Node","") for s in data.get("PointSupports",[]))

    st.markdown("**Capas:**")
    cc = st.columns(6)
    show_nodes = cc[0].checkbox("Nodos", False)
    show_sups = cc[1].checkbox("Apoyos", True)
    show_cols = cc[2].checkbox("Columnas", True)
    show_beams = cc[3].checkbox("Vigas", True)
    show_panels = cc[4].checkbox("Paneles", True)
    show_openings = cc[5].checkbox("Aberturas", True)

    fig = go.Figure()

    if show_nodes:
        ns = [n for n in nodes if n.get("Id") not in sup_ids]
        if ns:
            fig.add_trace(go.Scatter3d(
                x=[n["X"] for n in ns], y=[n["Y"] for n in ns], z=[n["Z"] for n in ns],
                mode='markers', marker=dict(size=2, color="#4a9eff", opacity=0.5),
                text=[n.get("Name","") for n in ns],
                hovertemplate="<b>%{text}</b><br>(%{x:.1f}, %{y:.1f}, %{z:.1f})<extra></extra>",
                name="Nodos"))

    if show_sups:
        sn = [nm[sid] for sid in sup_ids if sid in nm]
        if sn:
            fig.add_trace(go.Scatter3d(
                x=[n["X"] for n in sn], y=[n["Y"] for n in sn], z=[n["Z"] for n in sn],
                mode='markers', marker=dict(size=5, color="#e94560", symbol='diamond'),
                text=[n.get("Name","") for n in sn],
                hovertemplate="<b>%{text}</b> (Apoyo)<extra></extra>", name="Apoyos"))

    bars = data.get("CurveMembers", [])
    bar_groups = {}
    for bar in bars:
        bt = CURVE_TYPE.get(bar.get("Type", 0), "Other")
        if bt == "Column" and not show_cols: continue
        if bt != "Column" and not show_beams: continue
        if bt not in bar_groups: bar_groups[bt] = {"x": [], "y": [], "z": []}
        bn = bar.get("Nodes", [])
        if len(bn) >= 2:
            n1, n2 = nm.get(bn[0]), nm.get(bn[1])
            if n1 and n2:
                bar_groups[bt]["x"].extend([n1["X"], n2["X"], None])
                bar_groups[bt]["y"].extend([n1["Y"], n2["Y"], None])
                bar_groups[bt]["z"].extend([n1["Z"], n2["Z"], None])

    cmap = {"Column": "#ff6b6b", "Beam": "#51cf66", "General": "#748ffc", "SlabRib": "#ffd43b"}
    for bt, co in bar_groups.items():
        fig.add_trace(go.Scatter3d(x=co["x"], y=co["y"], z=co["z"],
            mode='lines', line=dict(color=cmap.get(bt,"#748ffc"), width=3),
            name=bt, connectgaps=False))

    if show_panels:
        # Mapa de openings por superficie
        opening_map = {}
        for op in data.get("SurfaceMemberOpenings", []):
            sid = op.get("Surface", "")
            pts_op = [nm.get(nid) for nid in op.get("Nodes", [])]
            pts_op = [p for p in pts_op if p]
            if len(pts_op) >= 3:
                if sid not in opening_map:
                    opening_map[sid] = []
                opening_map[sid].append([(p["X"], p["Y"], p["Z"]) for p in pts_op])

        for stype, label, color, ecolor in [(0,"Losas","rgba(100,180,255,0.55)","rgba(100,180,255,0.8)"),
                                              (1,"Muros","rgba(255,160,80,0.55)","rgba(255,160,80,0.8)")]:
            mx = {"x":[],"y":[],"z":[],"i":[],"j":[],"k":[]}
            ex = {"x":[],"y":[],"z":[]}
            for surf in data.get("SurfaceMembers", []):
                if surf.get("Type", 0) != stype: continue
                surf_id = surf.get("Id", "")
                pts = [nm.get(nid) for nid in surf.get("Nodes", [])]
                pts = [p for p in pts if p]
                if len(pts) < 3: continue

                off = len(mx["x"])
                for p in pts:
                    mx["x"].append(p["X"]); mx["y"].append(p["Y"]); mx["z"].append(p["Z"])

                # Proyectar openings a 2D para test punto-en-polígono
                surf_openings_2d = []
                if surf_id in opening_map:
                    for op_3d in opening_map[surf_id]:
                        surf_openings_2d.append(project_to_2d(op_3d))

                for t in range(len(pts)-2):
                    p0, p1, p2 = pts[0], pts[t+1], pts[t+2]

                    if surf_openings_2d:
                        cx = (p0["X"] + p1["X"] + p2["X"]) / 3
                        cy = (p0["Y"] + p1["Y"] + p2["Y"]) / 3
                        cz = (p0["Z"] + p1["Z"] + p2["Z"]) / 3
                        c2d = project_to_2d([(cx, cy, cz)])[0]

                        skip = False
                        for op_2d in surf_openings_2d:
                            if point_in_polygon_2d(c2d[0], c2d[1], op_2d):
                                skip = True
                                break
                        if skip:
                            continue

                    mx["i"].append(off); mx["j"].append(off+t+1); mx["k"].append(off+t+2)

                for p in pts:
                    ex["x"].append(p["X"]); ex["y"].append(p["Y"]); ex["z"].append(p["Z"])
                ex["x"].extend([pts[0]["X"], None])
                ex["y"].extend([pts[0]["Y"], None])
                ex["z"].extend([pts[0]["Z"], None])

            if mx["x"]:
                fig.add_trace(go.Mesh3d(x=mx["x"],y=mx["y"],z=mx["z"],
                    i=mx["i"],j=mx["j"],k=mx["k"],color=color,opacity=0.55,name=label,showlegend=True))
                fig.add_trace(go.Scatter3d(x=ex["x"],y=ex["y"],z=ex["z"],
                    mode='lines',line=dict(color=ecolor,width=2),
                    name=f"Bordes {label}",connectgaps=False,showlegend=False))

    if show_openings:
        openings = data.get("SurfaceMemberOpenings", [])
        if openings:
            ox_list, oy_list, oz_list = [], [], []
            for op in openings:
                pts = [nm.get(nid) for nid in op.get("Nodes", [])]
                pts = [p for p in pts if p]
                if len(pts) < 3: continue
                for p in pts:
                    ox_list.append(p["X"]); oy_list.append(p["Y"]); oz_list.append(p["Z"])
                ox_list.extend([pts[0]["X"], None])
                oy_list.extend([pts[0]["Y"], None])
                oz_list.extend([pts[0]["Z"], None])
            if ox_list:
                fig.add_trace(go.Scatter3d(x=ox_list, y=oy_list, z=oz_list,
                    mode='lines', line=dict(color="#ff0", width=3),
                    name="Aberturas", connectgaps=False))

    no_grid = dict(showgrid=False, showline=False, zeroline=False, showbackground=False)
    fig.update_layout(
        scene=dict(xaxis=dict(title="X (m)", **no_grid),
                   yaxis=dict(title="Y (m)", **no_grid),
                   zaxis=dict(title="Z (m)", **no_grid),
                   aspectmode='data', bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=0,r=0,t=30,b=0),height=600,template="plotly_dark",
        legend=dict(orientation="h",y=1.02,x=0.5,xanchor="center"))
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════
# BARRAS / SUPERFICIES / APOYOS
# ═══════════════════════════════════════
def render_bars(data):
    st.markdown('<p class="section-header">🔩 Barras</p>', unsafe_allow_html=True)
    bars = data.get("CurveMembers", [])
    if not bars: return st.info("No hay barras.")
    csm = id_name_map(data.get("CrossSections", []))
    tc = Counter(CURVE_TYPE.get(b.get("Type",0),"Other") for b in bars)
    c1, c2 = st.columns([1, 2])
    with c1:
        fig = px.pie(values=list(tc.values()),names=list(tc.keys()),title="Por Tipo",
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(template="plotly_dark",height=300,margin=dict(t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        rows = [{"ID":b.get("Id",""),"Nombre":b.get("Name",""),
                 "Tipo":CURVE_TYPE.get(b.get("Type",0),"?"),
                 "Nodos":" → ".join(b.get("Nodes",[])),
                 "Sección":csm.get(b.get("CrossSection",""),"N/A")} for b in bars]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=300)

def render_surfaces(data):
    st.markdown('<p class="section-header">🧩 Superficies</p>', unsafe_allow_html=True)
    surfs = data.get("SurfaceMembers", [])
    if not surfs: return st.info("No hay superficies.")
    mm = id_name_map(data.get("Materials", []))
    tc = Counter(SURFACE_TYPE.get(s.get("Type",0),"Other") for s in surfs)
    c1, c2 = st.columns([1, 2])
    with c1:
        fig = px.pie(values=list(tc.values()),names=list(tc.keys()),title="Por Tipo",
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(template="plotly_dark",height=300,margin=dict(t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        rows = [{"ID":s.get("Id",""),"Nombre":s.get("Name",""),
                 "Tipo":SURFACE_TYPE.get(s.get("Type",0),"?"),
                 "Espesor":s.get("Thickness",""),"Nodos":len(s.get("Nodes",[])),
                 "Material":", ".join(mm.get(mid,mid[:8]) for mid in s.get("Materials",[]))} for s in surfs]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=300)

    regs = data.get("SurfaceMemberRegions",[])
    if regs:
        st.markdown(f"**Regiones:** {len(regs)}")
        st.dataframe(pd.DataFrame([{"ID":r.get("Id",""),"Nombre":r.get("Name",""),
            "Superficie":r.get("Surface",""),"Espesor":r.get("Thickness",""),
            "Nodos":len(r.get("Nodes",[]))} for r in regs]),
            use_container_width=True,hide_index=True,height=200)

    ops = data.get("SurfaceMemberOpenings",[])
    if ops:
        st.markdown(f"**Aberturas:** {len(ops)}")
        st.dataframe(pd.DataFrame([{"Nombre":o.get("Name",""),"Superficie":o.get("Surface",""),
            "Nodos":" → ".join(o.get("Nodes",[]))} for o in ops]),use_container_width=True,hide_index=True)

def render_supports(data):
    st.markdown('<p class="section-header">📌 Apoyos</p>', unsafe_allow_html=True)
    sups = data.get("PointSupports", [])
    if not sups: return st.info("No hay apoyos.")
    st.dataframe(pd.DataFrame([{"Nombre":s.get("Name",""),"Nodo":s.get("Node",""),
        "Ux":SUPPORT_TRANS.get(s.get("Ux",0),"?"),"Uy":SUPPORT_TRANS.get(s.get("Uy",0),"?"),
        "Uz":SUPPORT_TRANS.get(s.get("Uz",0),"?"),"Rx":SUPPORT_ROT.get(s.get("Fix",0),"?"),
        "Ry":SUPPORT_ROT.get(s.get("Fiy",0),"?"),"Rz":SUPPORT_ROT.get(s.get("Fiz",0),"?")} for s in sups]),
        use_container_width=True,hide_index=True)


# ═══════════════════════════════════════
# CARGAS / ACCIONES
# ═══════════════════════════════════════
def render_loads(data):
    st.markdown('<p class="section-header">⚡ Cargas y Combinaciones</p>', unsafe_allow_html=True)
    lm = id_name_map(data.get("LoadCases", []))
    cases = data.get("LoadCases", [])
    if cases:
        st.markdown("**Casos de Carga**")
        st.dataframe(pd.DataFrame([{"Nombre":c.get("Name",""),
            "Acción":ACTION_TYPE_LC.get(c.get("ActionType",-1),"?"),
            "Tipo":LOAD_TYPE.get(c.get("Type",-1),"?")} for c in cases]),
            use_container_width=True,hide_index=True)
    combos = data.get("LoadCombinations", [])
    if combos:
        st.markdown("**Combinaciones**")
        for combo in combos:
            st.markdown(f"**{combo.get('Name','?')}** — {COMB_CATEGORY.get(combo.get('Category',0),'?')}")
            lids = combo.get("LoadCases",[])
            facs = combo.get("LoadFactors",[])
            mults = combo.get("Multipliers",[])
            st.dataframe(pd.DataFrame([{"Caso":lm.get(lids[j],lids[j][:12]),
                "Factor":facs[j] if j<len(facs) else "?",
                "Mult.":mults[j] if j<len(mults) else "?"} for j in range(len(lids))]),
                use_container_width=True,hide_index=True)

def render_actions(data):
    st.markdown('<p class="section-header">🎯 Acciones</p>', unsafe_allow_html=True)
    lm = id_name_map(data.get("LoadCases",[]))
    pa = data.get("PointActions",[])
    if pa:
        st.markdown(f"**Puntuales** ({len(pa)})")
        st.dataframe(pd.DataFrame([{"Nombre":a.get("Name",""),"Nodo":a.get("ReferenceNode",""),
            "X":a.get("X",0),"Y":a.get("Y",0),"Z":a.get("Z",0),
            "Caso":lm.get(a.get("LoadCase",""),"?")} for a in pa]),use_container_width=True,hide_index=True)
    ca = data.get("CurveActions",[])
    if ca:
        st.markdown(f"**Lineales** ({len(ca)})")
        st.dataframe(pd.DataFrame([{"Nombre":a.get("Name",""),"Barra":a.get("CurveMember",""),
            "Dist.":DISTRIBUTION.get(a.get("Distribution",0),"?"),
            "X":a.get("X",0),"Y":a.get("Y",0),"Z":a.get("Z",0),
            "Caso":lm.get(a.get("LoadCase",""),"?")} for a in ca]),use_container_width=True,hide_index=True)
    sa = data.get("SurfaceActions",[])
    if sa:
        st.markdown(f"**Superficiales** ({len(sa)})")
        st.dataframe(pd.DataFrame([{"Nombre":a.get("Name",""),"Superficie":a.get("SurfaceElement",""),
            "Qx":a.get("Qx",0),"Qy":a.get("Qy",0),"Qz":a.get("Qz",0),
            "Caso":lm.get(a.get("LoadCase",""),"?")} for a in sa]),use_container_width=True,hide_index=True)


# ═══════════════════════════════════════
# RESULTS 1D
# ═══════════════════════════════════════
def render_results_1d(data):
    st.markdown('<p class="section-header">📈 Resultados 1D (Fuerzas Internas)</p>', unsafe_allow_html=True)
    results = data.get("Results1D", [])
    if not results: return st.info("No hay resultados 1D.")

    lm = {**id_name_map(data.get("LoadCases",[])), **id_name_map(data.get("LoadCombinations",[]))}

    result_index = {}
    bar_summary = {}
    for r in results:
        bid = r.get("Member", "")
        lid = r.get("Load", "")
        result_index[(bid, lid)] = r
        ratio = nz_ratio_1d(r)
        if bid not in bar_summary:
            bar_summary[bid] = {"nonzero": 0, "zero": 0, "max_vals": {c: 0 for c in COMPS_1D}}
        if ratio > 0: bar_summary[bid]["nonzero"] += 1
        else: bar_summary[bid]["zero"] += 1
        for c in COMPS_1D:
            vals = [abs(v) for v in r.get(c, [])]
            if vals: bar_summary[bid]["max_vals"][c] = max(bar_summary[bid]["max_vals"][c], max(vals))

    total = len(results)
    full = sum(1 for r in results if nz_ratio_1d(r) == 1.0)
    partial = sum(1 for r in results if 0 < nz_ratio_1d(r) < 1.0)
    empty = sum(1 for r in results if nz_ratio_1d(r) == 0)
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total", total); mc2.metric("🟢 Completos", full)
    mc3.metric("🟡 Parciales", partial); mc4.metric("🔴 Vacíos", empty)

    rows = []
    for bid in sorted(bar_summary.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        info = bar_summary[bid]; mv = info["max_vals"]
        rows.append({"Barra": f"Bar {bid}", "bar_id": bid,
            "Estado": "✅" if info["nonzero"] > 0 else "⬜",
            "Casos ≠0": info["nonzero"], "Casos =0": info["zero"],
            "|N|": f"{mv['aN']:.2f}", "|Vy|": f"{mv['aVy']:.2f}", "|Vz|": f"{mv['aVz']:.2f}",
            "|Mx|": f"{mv['aMx']:.2f}", "|My|": f"{mv['aMy']:.2f}", "|Mz|": f"{mv['aMz']:.2f}"})
    df = pd.DataFrame(rows)

    filt = st.radio("Filtrar:", ["Todos", "Con valores ≠ 0", "Todo cero"], horizontal=True, key="f1d")
    if filt == "Con valores ≠ 0": df = df[df["Estado"] == "✅"]
    elif filt == "Todo cero": df = df[df["Estado"] == "⬜"]
    st.dataframe(df.drop(columns=["bar_id"]), use_container_width=True, hide_index=True, height=300)

    st.markdown("---"); st.markdown("#### 📊 Diagrama detallado")
    bar_ids = df["bar_id"].tolist()
    if not bar_ids: return

    load_ids = sorted(set(r.get("Load","") for r in results))
    load_names = [lm.get(lid, lid[:8]) for lid in load_ids]
    sc1, sc2 = st.columns(2)
    sel_bar = sc1.selectbox("Barra:", bar_ids, format_func=lambda x: f"Bar {x}", key="sel_bar")
    sel_load_name = sc2.selectbox("Caso:", load_names, key="sel_load")
    sel_load = load_ids[load_names.index(sel_load_name)]

    r = result_index.get((sel_bar, sel_load))
    if not r: return st.warning("Sin resultado.")

    ratio = nz_ratio_1d(r); nz_count = int(ratio * 6)
    if ratio == 1.0: st.success(f"✅ Completo — {nz_count}/6 componentes")
    elif ratio > 0: st.warning(f"🟡 Parcial — {nz_count}/6 componentes")
    else: st.error("🔴 Vacío — 0/6 componentes")

    secs = r.get("SectionsAt", [])
    comps = {"N (kN)": r.get("aN",[]), "Vy (kN)": r.get("aVy",[]), "Vz (kN)": r.get("aVz",[]),
             "Mx (kNm)": r.get("aMx",[]), "My (kNm)": r.get("aMy",[]), "Mz (kNm)": r.get("aMz",[])}
    nz_comps = [n for n, v in comps.items() if any(abs(x) > 1e-6 for x in v)]
    defaults = [c for c in ["Vz (kN)", "My (kNm)"] if c in nz_comps] or nz_comps[:2]
    sel_comps = st.multiselect("Componentes:", list(comps.keys()), default=defaults, key="mc1d")

    if sel_comps and secs:
        fig = go.Figure()
        for i, comp in enumerate(sel_comps):
            vals = comps.get(comp, [])
            if vals:
                fig.add_trace(go.Scatter(x=secs, y=vals, name=comp, mode='lines+markers',
                    line=dict(color=PLOT_COLORS[i % len(PLOT_COLORS)], width=2), marker=dict(size=5)))
        fig.update_layout(template="plotly_dark", xaxis_title="Posición (m)", yaxis_title="Valor",
                          height=400, margin=dict(t=30, b=40), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    summary = [{"Componente": k, "Mín": f"{min(v):.3f}" if v else "—",
                "Máx": f"{max(v):.3f}" if v else "—",
                "Estado": "✅" if any(abs(x) > 1e-6 for x in v) else "⬜"} for k, v in comps.items()]
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════
# MESH RESULTS
# ═══════════════════════════════════════
def render_mesh_results(data):
    st.markdown('<p class="section-header">🔺 Resultados Malla 2D</p>', unsafe_allow_html=True)
    results = data.get("MeshResults", [])
    if not results: return st.info("No hay resultados de malla.")

    lm = {**id_name_map(data.get("LoadCases",[])), **id_name_map(data.get("LoadCombinations",[]))}

    result_index = {}; panel_summary = {}
    for r in results:
        pid = r.get("Member", ""); lid = r.get("Load", "")
        result_index[(pid, lid)] = r; ratio = nz_ratio_mesh(r)
        if pid not in panel_summary:
            panel_summary[pid] = {"nonzero": 0, "zero": 0, "max_vals": {c: 0 for c in COMPS_MESH}}
        if ratio > 0: panel_summary[pid]["nonzero"] += 1
        else: panel_summary[pid]["zero"] += 1
        for c in COMPS_MESH:
            vals = [abs(v) for v in r.get(c, [])]
            if vals: panel_summary[pid]["max_vals"][c] = max(panel_summary[pid]["max_vals"][c], max(vals))

    total = len(results)
    full = sum(1 for r in results if nz_ratio_mesh(r) == 1.0)
    partial = sum(1 for r in results if 0 < nz_ratio_mesh(r) < 1.0)
    empty = sum(1 for r in results if nz_ratio_mesh(r) == 0)
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total", total); mc2.metric("🟢 Completos", full)
    mc3.metric("🟡 Parciales", partial); mc4.metric("🔴 Vacíos", empty)

    rows = []
    for pid in sorted(panel_summary.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        info = panel_summary[pid]; mv = info["max_vals"]
        rows.append({"Panel": f"Panel {pid}", "panel_id": pid,
            "Estado": "✅" if info["nonzero"] > 0 else "⬜",
            "Casos ≠0": info["nonzero"], "Casos =0": info["zero"],
            "|mx|": f"{mv['amx']:.2f}", "|my|": f"{mv['amy']:.2f}",
            "|nx|": f"{mv['anx']:.2f}", "|ny|": f"{mv['any']:.2f}",
            "|vx|": f"{mv['avx']:.2f}", "|vy|": f"{mv['avy']:.2f}"})
    df = pd.DataFrame(rows)

    filt = st.radio("Filtrar:", ["Todos", "Con valores ≠ 0", "Todo cero"], horizontal=True, key="fmesh")
    if filt == "Con valores ≠ 0": df = df[df["Estado"] == "✅"]
    elif filt == "Todo cero": df = df[df["Estado"] == "⬜"]
    st.dataframe(df.drop(columns=["panel_id"]), use_container_width=True, hide_index=True, height=300)

    st.markdown("---"); st.markdown("#### 📊 Diagrama detallado")
    panel_ids = df["panel_id"].tolist()
    if not panel_ids: return

    load_ids = sorted(set(r.get("Load","") for r in results))
    load_names = [lm.get(lid, lid[:8]) for lid in load_ids]
    sc1, sc2 = st.columns(2)
    sel_panel = sc1.selectbox("Panel:", panel_ids, format_func=lambda x: f"Panel {x}", key="sel_panel")
    sel_load_name = sc2.selectbox("Caso:", load_names, key="sel_load_m")
    sel_load = load_ids[load_names.index(sel_load_name)]

    r = result_index.get((sel_panel, sel_load))
    if not r: return st.warning("Sin resultado.")

    ratio = nz_ratio_mesh(r); nz_count = int(ratio * 8)
    if ratio == 1.0: st.success(f"✅ Completo — {nz_count}/8 componentes")
    elif ratio > 0: st.warning(f"🟡 Parcial — {nz_count}/8 componentes")
    else: st.error("🔴 Vacío — 0/8 componentes")

    comps = {c: r.get(c, []) for c in COMPS_MESH if r.get(c)}
    nz_comps = {k: v for k, v in comps.items() if any(abs(x) > 1e-6 for x in v)}
    comp_list = list(nz_comps.keys()) if nz_comps else list(comps.keys())
    if not comp_list: return st.info("Sin componentes con valores.")

    sel = st.selectbox("Componente:", comp_list, key="sel_comp_m")
    vals = comps.get(sel, [])
    if vals:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=list(range(1, len(vals)+1)), y=vals,
            marker_color=["#e94560" if v < 0 else "#4a9eff" for v in vals]))
        fig.update_layout(template="plotly_dark", xaxis_title="Nodo FE", yaxis_title=sel,
                          height=350, margin=dict(t=20, b=40))
        st.plotly_chart(fig, use_container_width=True)
        vc1, vc2, vc3 = st.columns(3)
        vc1.metric("Mín", f"{min(vals):.3f}"); vc2.metric("Máx", f"{max(vals):.3f}"); vc3.metric("Nodos FE", len(vals))


# ═══════════════════════════════════════
# VALIDACIÓN
# ═══════════════════════════════════════
def render_validation(data):
    st.markdown('<p class="section-header">✅ Validación</p>', unsafe_allow_html=True)

    # Construir conjuntos de IDs
    mat_ids = set(m.get("Id") for m in data.get("Materials",[]))
    cs_ids = set(s.get("Id") for s in data.get("CrossSections",[]))
    node_ids = set(n.get("Id") for n in data.get("PointConnections",[]))
    bar_ids = set(b.get("Id") for b in data.get("CurveMembers",[]))
    surf_ids = set(s.get("Id") for s in data.get("SurfaceMembers",[]))
    lc_ids = set(c.get("Id") for c in data.get("LoadCases",[]))
    combo_ids = set(c.get("Id") for c in data.get("LoadCombinations",[]))
    all_load_ids = lc_ids | combo_ids

    issues = []
    warns = []

    # ── REFERENCIAS CRUZADAS ──
    # Secciones → Materiales
    for cs in data.get("CrossSections",[]):
        for mid in cs.get("Materials",[]):
            if mid not in mat_ids:
                issues.append(f"Sección '{cs.get('Name','')}' → material '{mid[:12]}' no existe")

    # Barras → Secciones y Nodos
    for b in data.get("CurveMembers",[]):
        csid = b.get("CrossSection","")
        if csid and csid not in cs_ids:
            issues.append(f"Barra '{b.get('Name','')}' → sección '{csid[:12]}' no existe")
        for nid in b.get("Nodes",[]):
            if nid not in node_ids:
                issues.append(f"Barra '{b.get('Name','')}' → nodo '{nid}' no existe")

    # Superficies → Nodos y Materiales
    for s in data.get("SurfaceMembers",[]):
        for nid in s.get("Nodes",[]):
            if nid not in node_ids:
                issues.append(f"Superficie '{s.get('Name','')}' → nodo '{nid}' no existe")
        for mid in s.get("Materials",[]):
            if mid not in mat_ids:
                issues.append(f"Superficie '{s.get('Name','')}' → material '{mid[:12]}' no existe")

    # Regiones → Superficies y Nodos
    for r in data.get("SurfaceMemberRegions",[]):
        sid = r.get("Surface","")
        if sid and sid not in surf_ids:
            issues.append(f"Región '{r.get('Name','')}' → superficie '{sid}' no existe")
        for nid in r.get("Nodes",[]):
            if nid not in node_ids:
                issues.append(f"Región '{r.get('Name','')}' → nodo '{nid}' no existe")

    # Openings → Superficies y Nodos
    for o in data.get("SurfaceMemberOpenings",[]):
        sid = o.get("Surface","")
        if sid and sid not in surf_ids:
            issues.append(f"Abertura '{o.get('Name','')}' → superficie '{sid}' no existe")
        for nid in o.get("Nodes",[]):
            if nid not in node_ids:
                issues.append(f"Abertura '{o.get('Name','')}' → nodo '{nid}' no existe")

    # Apoyos → Nodos
    for sup in data.get("PointSupports",[]):
        nid = sup.get("Node","")
        if nid and nid not in node_ids:
            issues.append(f"Apoyo '{sup.get('Name','')}' → nodo '{nid}' no existe")

    # Combinaciones → Casos de carga
    for combo in data.get("LoadCombinations",[]):
        for lid in combo.get("LoadCases",[]):
            if lid not in all_load_ids:
                issues.append(f"Combinación '{combo.get('Name','')}' → caso '{lid[:12]}' no existe")

    # Acciones → Casos de carga, Nodos, Barras, Superficies
    for a in data.get("PointActions",[]):
        if a.get("LoadCase","") not in all_load_ids:
            issues.append(f"Acción puntual '{a.get('Name','')}' → caso no existe")
        rn = a.get("ReferenceNode","")
        if rn and rn not in node_ids:
            issues.append(f"Acción puntual '{a.get('Name','')}' → nodo '{rn}' no existe")

    for a in data.get("CurveActions",[]):
        if a.get("LoadCase","") not in all_load_ids:
            issues.append(f"Acción lineal '{a.get('Name','')}' → caso no existe")
        cm = a.get("CurveMember","")
        if cm and cm not in bar_ids:
            issues.append(f"Acción lineal '{a.get('Name','')}' → barra '{cm}' no existe")

    for a in data.get("SurfaceActions",[]):
        if a.get("LoadCase","") not in all_load_ids:
            issues.append(f"Acción superficial '{a.get('Name','')}' → caso no existe")
        se = a.get("SurfaceElement","")
        if se and se not in surf_ids:
            issues.append(f"Acción superficial '{a.get('Name','')}' → superficie '{se}' no existe")

    # Results1D → Barras y Casos
    for r in data.get("Results1D",[]):
        if r.get("Member","") not in bar_ids:
            issues.append(f"Result1D '{r.get('Name','')}' → barra '{r.get('Member','')}' no existe")
        if r.get("Load","") not in all_load_ids:
            issues.append(f"Result1D '{r.get('Name','')}' → caso '{r.get('Load','')[:12]}' no existe")

    # MeshResults → Superficies y Casos
    for r in data.get("MeshResults",[]):
        if r.get("Member","") not in surf_ids:
            issues.append(f"MeshResult '{r.get('Name','')}' → superficie '{r.get('Member','')}' no existe")
        if r.get("Load","") not in all_load_ids:
            issues.append(f"MeshResult '{r.get('Name','')}' → caso '{r.get('Load','')[:12]}' no existe")

    # Macros → Superficies
    for m in data.get("Macros",[]):
        if m.get("Surface","") not in surf_ids:
            issues.append(f"Macro '{m.get('Name','')}' → superficie '{m.get('Surface','')}' no existe")

    # ── ADVERTENCIAS ──
    # Resultados vacíos
    z1 = sum(1 for r in data.get("Results1D",[]) if nz_ratio_1d(r)==0)
    zm = sum(1 for r in data.get("MeshResults",[]) if nz_ratio_mesh(r)==0)
    if z1: warns.append(f"Results1D: {z1}/{len(data.get('Results1D',[]))} vacíos")
    if zm: warns.append(f"MeshResults: {zm}/{len(data.get('MeshResults',[]))} vacíos")

    # Entidades vacías
    empty = [k for k, v in data.items() if isinstance(v, list) and len(v) == 0]
    if empty: warns.append(f"Entidades vacías: {', '.join(empty)}")

    # Superficies sin material
    no_mat = sum(1 for s in data.get("SurfaceMembers",[]) if not s.get("Materials"))
    if no_mat: warns.append(f"{no_mat} superficies sin material asignado")

    # Superficies sin región
    reg_surfs = set(r.get("Surface","") for r in data.get("SurfaceMemberRegions",[]))
    no_reg = [s.get("Id") for s in data.get("SurfaceMembers",[]) if s.get("Id") not in reg_surfs]
    if no_reg: warns.append(f"{len(no_reg)} superficies sin región: {', '.join(no_reg[:10])}")

    # Barras sin sección
    no_cs = sum(1 for b in data.get("CurveMembers",[]) if not b.get("CrossSection"))
    if no_cs: warns.append(f"{no_cs} barras sin sección asignada")

    # Duplicados
    dup_surf = [k for k,v in Counter(s.get("Id") for s in data.get("SurfaceMembers",[])).items() if v > 1]
    if dup_surf: warns.append(f"IDs de superficie duplicados: {', '.join(dup_surf[:10])}")
    dup_bar = [k for k,v in Counter(b.get("Id") for b in data.get("CurveMembers",[])).items() if v > 1]
    if dup_bar: warns.append(f"IDs de barra duplicados: {', '.join(dup_bar[:10])}")

    # ── MOSTRAR ──
    total_checks = len(issues) + len(warns)
    if not issues and not warns:
        st.success("✅ Sin problemas. Todas las referencias cruzadas son válidas.")
    if issues:
        st.error(f"🔴 {len(issues)} errores de referencia")
        with st.expander(f"Ver errores ({len(issues)})", expanded=len(issues) <= 20):
            for i in issues[:50]:
                st.markdown(f"- {i}")
            if len(issues) > 50:
                st.markdown(f"_... y {len(issues)-50} más_")
    if warns:
        st.warning(f"🟡 {len(warns)} advertencias")
        with st.expander(f"Ver advertencias ({len(warns)})"):
            for w in warns:
                st.markdown(f"- {w}")

    # Resumen de integridad
    st.markdown("---")
    st.markdown("#### 📋 Integridad de Referencias")
    ref_checks = [
        ("Secciones → Materiales", len(data.get("CrossSections",[])),
         sum(1 for cs in data.get("CrossSections",[]) if all(m in mat_ids for m in cs.get("Materials",[])))),
        ("Barras → Secciones", len(data.get("CurveMembers",[])),
         sum(1 for b in data.get("CurveMembers",[]) if b.get("CrossSection","") in cs_ids or not b.get("CrossSection"))),
        ("Barras → Nodos", len(data.get("CurveMembers",[])),
         sum(1 for b in data.get("CurveMembers",[]) if all(n in node_ids for n in b.get("Nodes",[])))),
        ("Superficies → Nodos", len(data.get("SurfaceMembers",[])),
         sum(1 for s in data.get("SurfaceMembers",[]) if all(n in node_ids for n in s.get("Nodes",[])))),
        ("Superficies → Materiales", len(data.get("SurfaceMembers",[])),
         sum(1 for s in data.get("SurfaceMembers",[]) if all(m in mat_ids for m in s.get("Materials",[])))),
        ("Regiones → Superficies", len(data.get("SurfaceMemberRegions",[])),
         sum(1 for r in data.get("SurfaceMemberRegions",[]) if r.get("Surface","") in surf_ids)),
        ("Aberturas → Superficies", len(data.get("SurfaceMemberOpenings",[])),
         sum(1 for o in data.get("SurfaceMemberOpenings",[]) if o.get("Surface","") in surf_ids)),
        ("Apoyos → Nodos", len(data.get("PointSupports",[])),
         sum(1 for s in data.get("PointSupports",[]) if s.get("Node","") in node_ids)),
        ("Acciones → Casos", len(data.get("PointActions",[]))+len(data.get("CurveActions",[]))+len(data.get("SurfaceActions",[])),
         sum(1 for a in data.get("PointActions",[]) if a.get("LoadCase","") in all_load_ids) +
         sum(1 for a in data.get("CurveActions",[]) if a.get("LoadCase","") in all_load_ids) +
         sum(1 for a in data.get("SurfaceActions",[]) if a.get("LoadCase","") in all_load_ids)),
    ]
    rows = []
    for name, total, ok in ref_checks:
        if total == 0:
            status = "⬜"
            pct = "—"
        elif ok == total:
            status = "✅"
            pct = "100%"
        else:
            status = "❌"
            pct = f"{ok}/{total} ({100*ok//total}%)"
        rows.append({"Referencia": name, "Estado": status, "Válidas": pct})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_raw_json(data):
    st.markdown('<p class="section-header">🔍 JSON</p>', unsafe_allow_html=True)
    keys = [k for k in data.keys() if isinstance(data[k], list)]
    sk = st.selectbox("Entidad", keys)
    items = data.get(sk, [])
    if items:
        idx = st.slider("Índice", 0, len(items)-1, 0)
        st.json(items[idx])


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════
st.markdown("# 🏗️ JSAF Auditor")
st.markdown("Auditoría visual de modelos estructurales en formato JSAF")
uploaded = st.file_uploader("Cargar archivo JSAF (.json)", type=["json"])

if uploaded:
    data = load_json(uploaded)
    tabs = st.tabs(["📊 Resumen","🧱 Materiales","📐 Secciones","📍 Modelo 3D","🔩 Barras",
                     "🧩 Superficies","📌 Apoyos","⚡ Cargas","🎯 Acciones",
                     "📈 Results 1D","🔺 Malla 2D","✅ Validación","🔍 JSON"])
    with tabs[0]: render_overview(data)
    with tabs[1]: render_materials(data)
    with tabs[2]: render_cross_sections(data)
    with tabs[3]: render_3d_model(data)
    with tabs[4]: render_bars(data)
    with tabs[5]: render_surfaces(data)
    with tabs[6]: render_supports(data)
    with tabs[7]: render_loads(data)
    with tabs[8]: render_actions(data)
    with tabs[9]: render_results_1d(data)
    with tabs[10]: render_mesh_results(data)
    with tabs[11]: render_validation(data)
    with tabs[12]: render_raw_json(data)
else:
    st.info("👆 Sube un archivo JSAF (.json) para comenzar.")
