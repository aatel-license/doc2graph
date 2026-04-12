"""
renderer.py — Generazione del visualizzatore HTML interattivo stile Neo4j.
Usa il template originale del progetto (physics engine completo, context menu, Cypher export).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

NODE_COLORS = [
    "#4C8EDA", "#D75F5F", "#57C7E3", "#F16667", "#6DCE9E",
    "#FFC454", "#DA7194", "#845EC2", "#00C9A7", "#FF9671",
    "#F9F871", "#C34B96", "#2C73D2", "#0081CF", "#FF6F91",
]


def _assign_colors(nodes: list) -> dict:
    type_color: dict[str, str] = {}
    for node in nodes:
        t = node.get("type", "Nodo")
        if t not in type_color:
            type_color[t] = NODE_COLORS[len(type_color) % len(NODE_COLORS)]
    return type_color


def build_html(graph: dict, doc_name: str, output_path: Path) -> None:
    nodes = graph["nodes"]
    edges = graph["edges"]

    type_color: dict[str, str] = {}
    for node in nodes:
        t = node.get("type", "Nodo")
        if t not in type_color:
            idx = len(type_color) % len(NODE_COLORS)
            type_color[t] = NODE_COLORS[idx]

    js_nodes = []
    for node in nodes:
        color = type_color.get(node.get("type", "Nodo"), "#4C8EDA")
        js_nodes.append({
            "id":    node["id"],
            "label": node.get("label", ""),
            "type":  node.get("type", "Nodo"),
            "color": color,
            "desc":  node.get("description", ""),
            "props": node.get("properties", {}),
        })

    js_edges = []
    for edge in edges:
        js_edges.append({
            "source":   edge["source"],
            "target":   edge["target"],
            "type":     edge.get("type", ""),
            "label":    edge.get("label", ""),
            "props":    edge.get("properties", {}),
            "evidence": edge.get("evidence", ""),
        })

    legend_items = "".join(
        f'<div class="legend-item" data-type="{t}">'
        f'<span class="legend-dot" style="background:{c}"></span><span>{t}</span></div>'
        for t, c in sorted(type_color.items())
    )

    stats     = f"{len(nodes)} nodi &middot; {len(edges)} relazioni &middot; {len(type_color)} tipi"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    cypher_lines = []
    for node in nodes:
        props = node.get("properties", {})
        ntype = node.get("type", "Nodo")
        label = node.get("label", "").replace("'", "\\'")
        prop_str = ", ".join(
            f"{k}: '{str(v).replace(chr(39), chr(92)+chr(39))}'"
            for k, v in props.items()
        )
        if prop_str:
            cypher_lines.append(f"CREATE (:{ntype} {{id: '{node['id']}', name: '{label}', {prop_str}}});")
        else:
            cypher_lines.append(f"CREATE (:{ntype} {{id: '{node['id']}', name: '{label}'}});")
    for edge in edges:
        ev     = edge.get("evidence", "").replace("'", "\\'")[:80]
        lbl    = edge.get("label", "").replace("'", "\\'")
        eprops = edge.get("properties", {})
        prop_parts = [f"evidence:'{ev}'"]
        if lbl:
            prop_parts.append(f"label:'{lbl}'")
        for k, v in eprops.items():
            prop_parts.append(f"{k}:'{str(v).replace(chr(39), chr(92)+chr(39))}'")
        cypher_lines.append(
            f"MATCH (a {{id:'{edge['source']}'}}), (b {{id:'{edge['target']}'}}) "
            f"CREATE (a)-[:{edge['type']} {{{', '.join(prop_parts)}}}]->(b);"
        )
    cypher_str = "\n".join(cypher_lines)

    nodes_json  = json.dumps(js_nodes,  ensure_ascii=False)
    edges_json  = json.dumps(js_edges,  ensure_ascii=False)
    cypher_json = json.dumps(cypher_str, ensure_ascii=False)

    html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"it\">\n"
        "<head>\n"
        "<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"<title>Graph \u2014 {doc_name}</title>\n"
        + _CSS
        + "</head>\n<body>\n"
        + _HEADER.format(doc_name=doc_name, stats=stats)
        + _SIDEBAR.format(legend_items=legend_items, timestamp=timestamp)
        + _CANVAS_AND_MODALS
        + _SCRIPT.format(
            nodes_json=nodes_json,
            edges_json=edges_json,
            cypher_json=cypher_json,
        )
        + f"\n<footer>doc2graph \u00b7 LLM Knowledge Graph Extractor \u00b7 {timestamp}</footer>\n"
        + "</body>\n</html>"
    )

    output_path.write_text(html, encoding="utf-8")
    print(f"\n\u2705  HTML salvato \u2192 {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Template parts (kept as module-level strings so the f-string in build_html
# stays readable and avoids the "f-string backslash" restriction).
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#1A1A2E;--panel:#16213E;--panel2:#0F3460;
  --accent:#E94560;--accent2:#F5A623;
  --text:#E0E0E0;--dim:#888;--border:#2A2A5A;
  --r:10px;--font:'Inter','Segoe UI',sans-serif;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);
     height:100vh;display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;
       padding:9px 18px;background:var(--panel);border-bottom:1px solid var(--border);flex-shrink:0}
.hl{display:flex;align-items:center;gap:10px}
.logo{font-size:17px;font-weight:700;color:#00C9A7;display:flex;align-items:center;gap:6px}
.logo svg{width:26px;height:26px}
.dtitle{font-size:12px;color:var(--dim);border-left:1px solid var(--border);padding-left:10px;max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge{font-size:11px;color:var(--dim);background:var(--panel2);padding:3px 10px;border-radius:20px}
.hr{display:flex;gap:7px;align-items:center}
.btn{cursor:pointer;padding:5px 13px;border:none;border-radius:6px;font-size:12px;font-weight:600;transition:.15s}
.btn-a{background:var(--accent);color:#fff}.btn-a:hover{background:#ff6a80}
.btn-o{background:transparent;border:1px solid var(--border);color:var(--text)}.btn-o:hover{background:var(--panel2)}
.main{display:flex;flex:1;overflow:hidden}
.sb{width:260px;min-width:200px;background:var(--panel);border-right:1px solid var(--border);
    display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.ss{padding:12px 14px;border-bottom:1px solid var(--border)}
.ss h3{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:8px}
.search{width:100%;padding:6px 9px;background:var(--bg);border:1px solid var(--border);
        border-radius:6px;color:var(--text);font-size:12px;outline:none}
.search:focus{border-color:var(--accent2)}
.cg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px}
.cb{padding:6px;font-size:11px;text-align:center;cursor:pointer;background:var(--bg);
    border:1px solid var(--border);border-radius:5px;color:var(--text);transition:.12s;user-select:none}
.cb:hover{background:var(--panel2);border-color:var(--accent2)}
.cb-toggle.active{background:var(--accent2);color:#111;border-color:var(--accent2)}
.cb-toggle{background:var(--bg);color:var(--dim)}
.slider-row{display:flex;align-items:center;gap:7px;margin-bottom:7px}
.slider-row label{font-size:11px;color:var(--dim);min-width:78px;flex-shrink:0}
.slider-row span{font-size:11px;color:var(--accent2);min-width:28px;text-align:right;flex-shrink:0}
.sli{flex:1;-webkit-appearance:none;height:4px;border-radius:2px;
     background:var(--border);outline:none;cursor:pointer}
.sli::-webkit-slider-thumb{-webkit-appearance:none;width:13px;height:13px;
     border-radius:50%;background:var(--accent2);cursor:pointer;transition:.1s}
.sli::-webkit-slider-thumb:hover{background:#ffd060}
.sli::-moz-range-thumb{width:13px;height:13px;border-radius:50%;
     background:var(--accent2);border:none;cursor:pointer}
.ls{overflow-y:auto;flex:1;padding:12px 14px}
.legend-item{display:flex;align-items:center;gap:7px;font-size:12px;margin-bottom:5px;
             cursor:pointer;padding:3px 5px;border-radius:4px;transition:.12s;user-select:none}
.legend-item:hover,.legend-item.active{background:var(--panel2)}
.legend-dot{width:11px;height:11px;border-radius:50%;flex-shrink:0}
.ts{padding:8px 14px;border-top:1px solid var(--border);font-size:10px;color:var(--dim)}
#wrap{flex:1;position:relative;overflow:hidden}
canvas{display:block;width:100%;height:100%;cursor:grab}
canvas.dragging{cursor:grabbing}
#tip{position:absolute;pointer-events:none;display:none;
     background:var(--panel);border:1px solid var(--border);border-radius:7px;
     padding:10px 12px;font-size:12px;max-width:260px;z-index:20;line-height:1.5}
#tip strong{color:var(--accent2);font-size:13px}
#tip em{color:var(--dim);font-size:11px}
#tip .ev{margin-top:5px;padding-top:5px;border-top:1px solid var(--border);
         font-size:11px;color:#aaa;font-style:italic}
#info{position:absolute;right:14px;bottom:14px;width:260px;
      background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
      padding:13px;display:none;z-index:15;max-height:300px;overflow-y:auto}
#info h4{font-size:14px;font-weight:700;color:var(--accent2);margin-bottom:3px}
#info .it{font-size:11px;color:var(--dim);margin-bottom:8px}
#info .ir{font-size:12px;border-bottom:1px solid var(--border);padding:4px 0;display:flex;gap:8px}
#info .ik{color:var(--dim);min-width:75px}
.xi{float:right;cursor:pointer;color:var(--dim);font-size:16px;line-height:1}
.mo{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:100;
    align-items:center;justify-content:center}
.mo.show{display:flex}
#ctx-menu{
  position:fixed;display:none;z-index:200;
  background:var(--panel);border:1px solid var(--border);
  border-radius:8px;padding:5px 0;min-width:190px;
  box-shadow:0 8px 28px rgba(0,0,0,.6);font-size:13px;
}
#ctx-menu .ctx-title{
  padding:5px 14px 3px;font-size:10px;
  text-transform:uppercase;letter-spacing:1px;color:var(--dim);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;
}
#ctx-menu .ctx-sep{height:1px;background:var(--border);margin:4px 0}
#ctx-menu .ctx-item{
  display:flex;align-items:center;gap:9px;padding:7px 14px;
  cursor:pointer;color:var(--text);transition:.12s;user-select:none;
}
#ctx-menu .ctx-item:hover{background:var(--panel2);color:#fff}
#ctx-menu .ctx-item.danger{color:#ff8080}
#ctx-menu .ctx-item.danger:hover{background:#5a1010}
.md{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    width:640px;max-width:94vw;max-height:78vh;display:flex;flex-direction:column}
.mh{display:flex;justify-content:space-between;align-items:center;
    padding:13px 16px;border-bottom:1px solid var(--border)}
.mh h3{font-size:13px;font-weight:700;color:var(--accent2)}
.mb{padding:14px;overflow-y:auto;flex:1}
pre.cy{background:var(--bg);border-radius:6px;padding:11px;font-size:11px;color:#00C9A7;
       overflow-x:auto;white-space:pre;line-height:1.6}
.mf{padding:9px 16px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:7px}
footer{font-size:10px;color:var(--dim);text-align:center;padding:4px;
       background:var(--panel);border-top:1px solid var(--border);flex-shrink:0}
</style>
"""

_HEADER = """<header>
  <div class="hl">
    <div class="logo">
      <svg viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">
        <circle cx="14" cy="30" r="7" fill="#00C9A7"/>
        <circle cx="46" cy="13" r="7" fill="#F5A623"/>
        <circle cx="46" cy="47" r="7" fill="#E94560"/>
        <circle cx="30" cy="30" r="5" fill="#4C8EDA"/>
        <line x1="14" y1="30" x2="30" y2="30" stroke="#555" stroke-width="2"/>
        <line x1="30" y1="30" x2="46" y2="13" stroke="#555" stroke-width="2"/>
        <line x1="30" y1="30" x2="46" y2="47" stroke="#555" stroke-width="2"/>
        <line x1="46" y1="13" x2="46" y2="47" stroke="#555" stroke-width="2"/>
      </svg>
      Graph Explorer
    </div>
    <span class="dtitle">&#128196; {doc_name}</span>
  </div>
  <div class="hr">
    <span class="badge">{stats}</span>
    <button class="btn btn-o" onclick="openCypher()">Cypher</button>
    <button class="btn btn-a" onclick="resetView()">&#8634; Reset</button>
  </div>
</header>
<div class="main">
"""

_SIDEBAR = """  <div class="sb">
    <div class="ss">
      <h3>&#128269; Cerca nodo</h3>
      <input class="search" id="q" type="text" placeholder="Nome&#8230;" oninput="search(this.value)">
    </div>
    <div class="ss">
      <h3>&#9881;&#65039; Controlli</h3>
      <div class="cg">
        <div class="cb" onclick="fitView()">Adatta</div>
        <div class="cb cb-toggle active" id="btn-phys" onclick="togglePhys()">Physics ON</div>
        <div class="cb" onclick="zoom(1.3)">Zoom +</div>
        <div class="cb" onclick="zoom(0.77)">Zoom &#8722;</div>
        <div class="cb" onclick="unpinAll()">Sblocca</div>
        <div class="cb" onclick="showAll()">Tutto</div>
        <div class="cb" onclick="savePNG()">PNG</div>
      </div>
    </div>
    <div class="ss">
      <h3>&#128279; Fisica grafo</h3>
      <div class="slider-row">
        <label>Lung. archi</label>
        <input class="sli" id="sl-spring" type="range" min="40" max="500" value="150"
               oninput="setSpringL(+this.value)">
        <span id="lbl-spring">150</span>
      </div>
      <div class="slider-row">
        <label>Repulsione</label>
        <input class="sli" id="sl-rep" type="range" min="500" max="15000" step="500" value="5000"
               oninput="setRepulsion(+this.value)">
        <span id="lbl-rep">5000</span>
      </div>
      <div class="slider-row">
        <label>Gravit&#224;</label>
        <input class="sli" id="sl-grav" type="range" min="0" max="60" step="1" value="12"
               oninput="setGravity(+this.value)">
        <span id="lbl-grav">0.012</span>
      </div>
      <div class="slider-row">
        <label>Damping</label>
        <input class="sli" id="sl-damp" type="range" min="50" max="99" step="1" value="85"
               oninput="setDamp(+this.value)">
        <span id="lbl-damp">0.85</span>
      </div>
    </div>
    <h3 style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);padding:12px 14px 4px">&#127991;&#65039; Tipi nodo</h3>
    <div class="ls">{legend_items}</div>
    <div class="ts">Generato: {timestamp}</div>
  </div>

  <div id="wrap">
    <canvas id="c"></canvas>
    <div id="tip"></div>
    <div id="info">
      <span class="xi" onclick="closeInfo()">&#215;</span>
      <h4 id="i-label"></h4>
      <div class="it" id="i-type"></div>
      <div id="i-props"></div>
    </div>
  </div>
</div>
"""

_CANVAS_AND_MODALS = """<div id="ctx-menu">
  <div class="ctx-title" id="ctx-node-name">Nodo</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item" onclick="ctxFilterNode()">&#128269; Solo questo nodo</div>
  <div class="ctx-item" onclick="ctxExpand(1)">&#127758; Espandi 1&#176; livello</div>
  <div class="ctx-item" onclick="ctxExpand(2)">&#127758; Espandi 2&#176; livello</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item" onclick="ctxPinToggle()">&#128204; <span id="ctx-pin-lbl">Fissa posizione</span></div>
  <div class="ctx-item" onclick="ctxCopyLabel()">&#128203; Copia etichetta</div>
  <div class="ctx-sep"></div>
  <div class="ctx-item" onclick="showAll();closeCtx()">&#9851; Reset filtro</div>
  <div class="ctx-item danger" onclick="ctxHideNode()">&#128584; Nascondi nodo</div>
</div>

<div class="mo" id="cm">
  <div class="md">
    <div class="mh">
      <h3>&#128309; Export Cypher (Neo4j)</h3>
      <button class="btn btn-o" style="padding:2px 8px;font-size:16px" onclick="closeCypher()">&#215;</button>
    </div>
    <div class="mb"><pre class="cy" id="cy-text"></pre></div>
    <div class="mf">
      <button class="btn btn-o" onclick="copyCy()">&#128203; Copia</button>
      <button class="btn btn-a" onclick="dlCy()">&#8595; .cypher</button>
    </div>
  </div>
</div>
"""

_SCRIPT = """<script>
const NODES_DATA = {nodes_json};
const EDGES_DATA = {edges_json};
const CYPHER     = {cypher_json};

const canvas = document.getElementById("c");
const ctx    = canvas.getContext("2d");
const DPR    = devicePixelRatio;

const nodes = NODES_DATA.map((d, i) => {{
  const angle = (2 * Math.PI * i) / NODES_DATA.length;
  const r     = Math.min(400, 80 + NODES_DATA.length * 7);
  return {{ ...d, x: Math.cos(angle)*r, y: Math.sin(angle)*r,
            vx:0, vy:0, hidden:false, highlighted:false }};
}});

const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]));
const edges   = EDGES_DATA.map(e => ({{
  ...e, source: nodeMap[e.source], target: nodeMap[e.target]
}})).filter(e => e.source && e.target);

let tx=0, ty=0, scale=1, physicsOn=true;

function resize() {{
  canvas.width  = canvas.offsetWidth  * DPR;
  canvas.height = canvas.offsetHeight * DPR;
  ctx.setTransform(1,0,0,1,0,0);
}}
window.addEventListener("resize", () => {{ resize(); fitView(); }});
resize();

function fitView() {{
  const vis = nodes.filter(n => !n.hidden);
  if (!vis.length) return;
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
  vis.forEach(n=>{{ minX=Math.min(minX,n.x);maxX=Math.max(maxX,n.x);
                    minY=Math.min(minY,n.y);maxY=Math.max(maxY,n.y); }});
  const pw=canvas.width/DPR, ph=canvas.height/DPR;
  const gw=maxX-minX+120, gh=maxY-minY+120;
  scale=Math.min(pw/gw, ph/gh, 2)*0.9;
  tx=pw/2-(minX+maxX)/2*scale;
  ty=ph/2-(minY+maxY)/2*scale;
}}

function setSpringL(v){{ SPRING_L=v; document.getElementById("lbl-spring").textContent=v; }}
function setRepulsion(v){{ REPULSION=v; document.getElementById("lbl-rep").textContent=v; }}
function setGravity(v){{ GRAVITY=v/1000; document.getElementById("lbl-grav").textContent=(v/1000).toFixed(3); }}
function setDamp(v){{ DAMP=v/100; document.getElementById("lbl-damp").textContent=(v/100).toFixed(2); }}

let REPULSION=5000, SPRING_K=0.03, SPRING_L=150, DAMP=0.85, GRAVITY=0.012;

const EDGE_PALETTE=["#57C7E3","#6DCE9E","#FFC454","#DA7194","#C990C0",
  "#F79767","#4FC1E0","#A0D568","#FFCE54","#ED5565",
  "#AC92EC","#48CFAD","#FC6E51","#5D9CEC","#F6BB42"];
const edgeColorMap={{}};let _epi=0;
function getEdgeColor(t){{
  if(!edgeColorMap[t]){{ edgeColorMap[t]=EDGE_PALETTE[_epi++%EDGE_PALETTE.length]; }}
  return edgeColorMap[t];
}}

(()=>{{
  const pc={{}},ps={{}};
  edges.forEach(e=>{{ const k=[e.source.id,e.target.id].sort().join("||"); pc[k]=(pc[k]||0)+1; }});
  edges.forEach(e=>{{ const k=[e.source.id,e.target.id].sort().join("||");
    ps[k]=ps[k]||0; e._bendIdx=ps[k]; e._bendTotal=pc[k]; ps[k]++; }});
}})();

function drawEdge(e,sel){{
  const [sx,sy]=worldToScreen(e.source.x,e.source.y);
  const [ex,ey]=worldToScreen(e.target.x,e.target.y);
  const dx=ex-sx,dy=ey-sy,len=Math.sqrt(dx*dx+dy*dy);
  if(len<2) return;
  const col=sel?"#FFA500":getEdgeColor(e.type);
  const NR=22*scale,ux=dx/len,uy=dy/len;
  const ax=sx+ux*NR,ay=sy+uy*NR,bx=ex-ux*NR,by=ey-uy*NR;
  const tot=e._bendTotal||1,idx=e._bendIdx||0,mb=40*scale;
  const bend=tot===1?Math.min(28*scale,len*0.12):(idx-(tot-1)/2)*(mb*2/Math.max(tot-1,1));
  const px=-uy,py=ux,mx2=(ax+bx)/2,my2=(ay+by)/2;
  const cpx=mx2+px*bend,cpy=my2+py*bend;
  ctx.beginPath();ctx.moveTo(ax*DPR,ay*DPR);
  ctx.quadraticCurveTo(cpx*DPR,cpy*DPR,bx*DPR,by*DPR);
  ctx.strokeStyle=col;ctx.lineWidth=(sel?2.5:1.8)*DPR;ctx.globalAlpha=sel?1:0.75;ctx.stroke();ctx.globalAlpha=1;
  const tx2=bx-cpx,ty2=by-cpy,tlen=Math.sqrt(tx2*tx2+ty2*ty2)||1;
  const tux=tx2/tlen,tuy=ty2/tlen,hw=(sel?7:5.5)*scale,hl=(sel?13:10)*scale,ppx=-tuy,ppy=tux;
  ctx.beginPath();ctx.moveTo(bx*DPR,by*DPR);
  ctx.lineTo((bx-tux*hl+ppx*hw)*DPR,(by-tuy*hl+ppy*hw)*DPR);
  ctx.lineTo((bx-tux*hl-ppx*hw)*DPR,(by-tuy*hl-ppy*hw)*DPR);
  ctx.closePath();ctx.fillStyle=col;ctx.globalAlpha=sel?1:0.85;ctx.fill();ctx.globalAlpha=1;
  if(scale<0.3) return;
  const lx=0.25*ax+0.5*cpx+0.25*bx,ly=0.25*ay+0.5*cpy+0.25*by;
  const tfs=Math.max(9,Math.min(12,11*scale)),lfs=Math.max(8,Math.min(10,9*scale));
  ctx.textAlign="center";ctx.textBaseline="middle";
  ctx.font=`600 ${{tfs*DPR}}px Inter,sans-serif`;
  const tw2=ctx.measureText(e.type).width,ph2=tfs*DPR*1.4,pw2=tw2+10*DPR,pr=ph2/2;
  ctx.beginPath();ctx.roundRect(lx*DPR-pw2/2,ly*DPR-ph2/2,pw2,ph2,pr);
  ctx.fillStyle=sel?"rgba(255,140,0,0.88)":`${{col}}cc`;
  ctx.shadowColor="rgba(0,0,0,0.5)";ctx.shadowBlur=4*DPR;ctx.fill();
  ctx.shadowBlur=0;ctx.fillStyle="#fff";ctx.fillText(e.type,lx*DPR,ly*DPR);
  if(e.label&&scale>0.6){{
    const ly2=ly+tfs*scale*1.6;
    ctx.font=`italic ${{lfs*DPR}}px Inter,sans-serif`;
    const lw2=ctx.measureText(e.label).width+8*DPR,lh2=lfs*DPR*1.4;
    ctx.beginPath();ctx.roundRect(lx*DPR-lw2/2,ly2*DPR-lh2/2,lw2,lh2,lh2/2);
    ctx.fillStyle="rgba(0,0,0,0.45)";ctx.fill();
    ctx.fillStyle=sel?"#FFE0A0":"#ddd";ctx.fillText(e.label,lx*DPR,ly2*DPR);
  }}
}}

function worldToScreen(x,y){{ return [x*scale+tx,y*scale+ty]; }}

function draw(){{
  ctx.clearRect(0,0,canvas.width,canvas.height);
  edges.forEach(e=>{{ if(e.source.hidden||e.target.hidden) return;
    const sel=!!(selectedNode&&(e.source===selectedNode||e.target===selectedNode));
    if(!sel) drawEdge(e,false); }});
  edges.forEach(e=>{{ if(e.source.hidden||e.target.hidden) return;
    const sel=!!(selectedNode&&(e.source===selectedNode||e.target===selectedNode));
    if(sel) drawEdge(e,true); }});
  const NR=22;
  nodes.forEach(n=>{{
    if(n.hidden) return;
    const [sx,sy]=worldToScreen(n.x,n.y);
    const r=NR*scale*DPR,sel=(n===selectedNode),hi=n.highlighted;
    if(sel){{ctx.beginPath();ctx.arc(sx*DPR,sy*DPR,r+6*DPR,0,Math.PI*2);ctx.fillStyle="rgba(255,165,0,0.25)";ctx.fill();}}
    ctx.beginPath();ctx.arc(sx*DPR,sy*DPR,r,0,Math.PI*2);
    ctx.fillStyle=hi?"#FFD700":sel?"#FF8C00":n.color;ctx.fill();
    ctx.strokeStyle=hi||sel?"#FFA500":"rgba(255,255,255,0.15)";ctx.lineWidth=(sel?3:1.5)*DPR;ctx.stroke();
    const fs2=Math.max(9,Math.min(13,13*scale));
    ctx.font=`bold ${{fs2*DPR}}px Inter,sans-serif`;ctx.fillStyle="#fff";ctx.textAlign="center";ctx.textBaseline="middle";
    let lbl=n.label;
    while(lbl.length>2&&ctx.measureText(lbl).width>r*1.7) lbl=lbl.slice(0,-1);
    if(lbl!==n.label) lbl=lbl.slice(0,-1)+"…";
    ctx.fillText(lbl,sx*DPR,sy*DPR);
    if(scale>0.5){{
      const fs3=Math.max(8,9*scale);ctx.font=`${{fs3*DPR}}px Inter,sans-serif`;
      ctx.fillStyle="rgba(255,255,255,0.55)";ctx.fillText(n.type,sx*DPR,(sy+NR*scale+10)*DPR);
    }}
    if(n.pinned){{ctx.beginPath();ctx.arc((sx+NR*scale*0.7)*DPR,(sy-NR*scale*0.7)*DPR,4*DPR,0,Math.PI*2);ctx.fillStyle="#F5A623";ctx.fill();}}
  }});
}}

let dragNode=null,dragOffX=0,dragOffY=0,panStart=null,panTx=0,panTy=0;
let selectedNode=null,mouseDownNode=null,mouseDownPos=null,didDrag=false;
const DRAG_THRESHOLD=4;

function loop(){{ if(physicsOn) stepPhysics(); draw(); requestAnimationFrame(loop); }}
loop();
setTimeout(fitView,400);

function screenToWorld(sx,sy){{ return [(sx-tx)/scale,(sy-ty)/scale]; }}
function nodeAt(sx,sy){{
  const [wx,wy]=screenToWorld(sx,sy);
  return nodes.find(n=>!n.hidden&&Math.hypot(n.x-wx,n.y-wy)<22)||null;
}}
function edgeAt(sx,sy){{
  const [wx,wy]=screenToWorld(sx,sy);
  for(const e of edges){{
    if(e.source.hidden||e.target.hidden) continue;
    const dx=e.target.x-e.source.x,dy=e.target.y-e.source.y,len=Math.sqrt(dx*dx+dy*dy);
    if(len<1) continue;
    const t=((wx-e.source.x)*dx+(wy-e.source.y)*dy)/(len*len);
    if(t<0||t>1) continue;
    if(Math.hypot(wx-(e.source.x+t*dx),wy-(e.source.y+t*dy))<8/scale) return e;
  }}
  return null;
}}

canvas.addEventListener("mousedown",e=>{{
  if(e.button!==0) return;
  const r=canvas.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top;
  const n=nodeAt(sx,sy);mouseDownPos={{x:sx,y:sy}};didDrag=false;
  if(n){{ mouseDownNode=n;const [wx,wy]=screenToWorld(sx,sy);dragOffX=wx-n.x;dragOffY=wy-n.y; }}
  else{{ mouseDownNode=null;panStart={{x:sx,y:sy}};panTx=tx;panTy=ty; }}
}});

canvas.addEventListener("mousemove",e=>{{
  const r=canvas.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top;
  if(mouseDownNode&&!dragNode){{
    if(Math.hypot(sx-mouseDownPos.x,sy-mouseDownPos.y)>DRAG_THRESHOLD){{
      dragNode=mouseDownNode;didDrag=true;canvas.classList.add("dragging");
    }}
  }}
  if(dragNode){{
    const [wx,wy]=screenToWorld(sx,sy);dragNode.x=wx-dragOffX;dragNode.y=wy-dragOffY;
    dragNode.vx=0;dragNode.vy=0;dragNode.pinned=true;
    document.getElementById("tip").style.display="none";return;
  }}
  if(panStart){{ tx=panTx+(sx-panStart.x);ty=panTy+(sy-panStart.y);return; }}
  const n=nodeAt(sx,sy),tip=document.getElementById("tip");
  if(n){{
    let html=`<strong>${{n.label}}</strong> <em>[${{n.type}}]</em>`;
    if(n.pinned) html+=` <span style="color:#F5A623;font-size:10px">&#128204;</span>`;
    if(n.desc) html+=`<br><span style="color:var(--dim)">${{n.desc}}</span>`;
    const pk=Object.keys(n.props||{{}});
    if(pk.length) html+="<br>"+pk.map(k=>`<b>${{k}}:</b> ${{n.props[k]}}`).join("<br>");
    tip.innerHTML=html;tip.style.display="block";
    tip.style.left=(sx+14)+"px";tip.style.top=(sy-10)+"px";
  }} else {{
    const eg=edgeAt(sx,sy);
    if(eg){{
      let html=`<strong style="color:var(--accent2)">${{eg.type}}</strong>`;
      if(eg.label) html+=` <em style="color:#ccc;font-size:11px">&#8212; ${{eg.label}}</em>`;
      html+=`<br><span style="color:var(--dim);font-size:11px">${{eg.source.label}} &#8594; ${{eg.target.label}}</span>`;
      const ep=Object.keys(eg.props||{{}});
      if(ep.length) html+="<br>"+ep.map(k=>`<span style="color:var(--dim)">${{k}}:</span> <b>${{eg.props[k]}}</b>`).join(" &nbsp;");
      if(eg.evidence) html+=`<div class="ev">"${{eg.evidence.slice(0,120)}}${{eg.evidence.length>120?"&#8230;":""}}"</div>`;
      tip.innerHTML=html;tip.style.display="block";
      tip.style.left=(sx+14)+"px";tip.style.top=(sy-10)+"px";
    }} else {{ tip.style.display="none"; }}
  }}
}});

canvas.addEventListener("mouseup",e=>{{
  canvas.classList.remove("dragging");dragNode=null;panStart=null;
  if(!didDrag){{
    const r=canvas.getBoundingClientRect(),n=nodeAt(e.clientX-r.left,e.clientY-r.top);
    selectedNode=n||null;if(n) showInfo(n);else closeInfo();
  }}
  mouseDownNode=null;
}});

canvas.addEventListener("dblclick",e=>{{
  const r=canvas.getBoundingClientRect(),n=nodeAt(e.clientX-r.left,e.clientY-r.top);
  if(n){{ n.pinned=false;n.vx=0;n.vy=0; }}
}});

canvas.addEventListener("wheel",e=>{{
  e.preventDefault();
  const r=canvas.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top;
  const f=e.deltaY<0?1.15:1/1.15,ns=Math.max(0.1,Math.min(5,scale*f));
  tx=sx-(sx-tx)/scale*ns;ty=sy-(sy-ty)/scale*ns;scale=ns;
}},{{passive:false}});

let lastDist=0;
canvas.addEventListener("touchstart",e=>{{
  if(e.touches.length===2) lastDist=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);
}},{{passive:true}});
canvas.addEventListener("touchmove",e=>{{
  if(e.touches.length===2){{
    const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);
    if(lastDist) scale=Math.max(0.1,Math.min(5,scale*d/lastDist));lastDist=d;
  }}
}},{{passive:true}});

function stepPhysics(){{
  const vis=nodes.filter(n=>!n.hidden);if(vis.length<2) return;
  for(let i=0;i<vis.length;i++){{
    for(let j=i+1;j<vis.length;j++){{
      const a=vis[i],b=vis[j];let dx=b.x-a.x,dy=b.y-a.y;
      const d2=dx*dx+dy*dy+1,f=REPULSION/d2,d=Math.sqrt(d2);dx/=d;dy/=d;
      a.vx-=f*dx;a.vy-=f*dy;b.vx+=f*dx;b.vy+=f*dy;
    }}
  }}
  edges.forEach(e=>{{
    if(e.source.hidden||e.target.hidden) return;
    const dx=e.target.x-e.source.x,dy=e.target.y-e.source.y,d=Math.sqrt(dx*dx+dy*dy)+0.01;
    const f=SPRING_K*(d-SPRING_L),fx=f*dx/d,fy=f*dy/d;
    e.source.vx+=fx;e.source.vy+=fy;e.target.vx-=fx;e.target.vy-=fy;
  }});
  vis.forEach(n=>{{n.vx-=n.x*GRAVITY;n.vy-=n.y*GRAVITY;}});
  vis.forEach(n=>{{
    if(n===dragNode||n.pinned) return;
    n.vx*=DAMP;n.vy*=DAMP;n.x+=n.vx;n.y+=n.vy;
  }});
}}

function showInfo(n){{
  document.getElementById("i-label").textContent=n.label;
  document.getElementById("i-type").textContent="["+n.type+"]";
  const cc=edges.filter(e=>e.source===n||e.target===n).length;
  let rows=`<div class="ir"><span class="ik">Relazioni</span><span>${{cc}}</span></div>`;
  if(n.desc) rows+=`<div class="ir"><span class="ik">Desc.</span><span>${{n.desc}}</span></div>`;
  Object.entries(n.props||{{}}).forEach(([k,v])=>{{rows+=`<div class="ir"><span class="ik">${{k}}</span><span>${{v}}</span></div>`;}});
  document.getElementById("i-props").innerHTML=rows;
  document.getElementById("info").style.display="block";
}}
function closeInfo(){{ document.getElementById("info").style.display="none";selectedNode=null; }}
function zoom(f){{ scale=Math.max(0.1,Math.min(5,scale*f)); }}
function togglePhys(){{
  physicsOn=!physicsOn;
  const btn=document.getElementById("btn-phys");
  btn.textContent=physicsOn?"Physics ON":"Physics OFF";
  btn.classList.toggle("active",physicsOn);
  if(physicsOn) nodes.forEach(n=>{{if(n.pinned){{n.vx=0;n.vy=0;}}}});
}}
function unpinAll(){{ nodes.forEach(n=>{{n.pinned=false;n.vx=0;n.vy=0;}}); }}
function resetView(){{ fitView(); }}
function showAll(){{ nodes.forEach(n=>n.hidden=false);fitView(); }}
function search(q){{
  q=q.toLowerCase().trim();
  nodes.forEach(n=>{{n.hidden=q?!n.label.toLowerCase().includes(q):false;n.highlighted=false;}});
  if(q) nodes.filter(n=>!n.hidden).forEach(n=>n.highlighted=true);
}}
document.querySelectorAll(".legend-item").forEach(el=>{{
  el.addEventListener("click",()=>{{
    el.classList.toggle("active");
    const active=[...document.querySelectorAll(".legend-item.active")].map(e=>e.dataset.type);
    if(!active.length){{nodes.forEach(n=>n.hidden=false);return;}}
    nodes.forEach(n=>n.hidden=!active.includes(n.type));fitView();
  }});
}});
function savePNG(){{ const a=document.createElement("a");a.href=canvas.toDataURL("image/png");a.download="graph.png";a.click(); }}
function openCypher(){{ document.getElementById("cy-text").textContent=CYPHER;document.getElementById("cm").classList.add("show"); }}
function closeCypher(){{ document.getElementById("cm").classList.remove("show"); }}
function copyCy(){{ navigator.clipboard?.writeText(CYPHER); }}
function dlCy(){{
  const a=document.createElement("a");
  a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(CYPHER);
  a.download="graph.cypher";a.click();
}}

let ctxNode=null;
function closeCtx(){{ document.getElementById("ctx-menu").style.display="none";ctxNode=null; }}
canvas.addEventListener("contextmenu",function(e){{
  e.preventDefault();
  const r=canvas.getBoundingClientRect(),n=nodeAt(e.clientX-r.left,e.clientY-r.top);
  if(!n){{ closeCtx();return; }}
  ctxNode=n;selectedNode=n;showInfo(n);
  document.getElementById("ctx-node-name").textContent=n.label+" ["+n.type+"]";
  document.getElementById("ctx-pin-lbl").textContent=n.pinned?"Sblocca posizione":"Fissa posizione";
  const menu=document.getElementById("ctx-menu");menu.style.display="block";
  const mw=menu.offsetWidth,mh=menu.offsetHeight,vw=window.innerWidth,vh=window.innerHeight;
  menu.style.left=(e.clientX+mw>vw?e.clientX-mw:e.clientX+4)+"px";
  menu.style.top=(e.clientY+mh>vh?e.clientY-mh:e.clientY+4)+"px";
}});
document.addEventListener("click",closeCtx);
document.addEventListener("keydown",function(e){{if(e.key==="Escape") closeCtx();}});

function getNeighborIds(sn,depth){{
  const visited=new Set([sn.id]);let frontier=[sn.id];
  for(let d=0;d<depth;d++){{
    const next=[];
    edges.forEach(function(e){{
      if(frontier.indexOf(e.source.id)!==-1&&!visited.has(e.target.id)){{visited.add(e.target.id);next.push(e.target.id);}}
      if(frontier.indexOf(e.target.id)!==-1&&!visited.has(e.source.id)){{visited.add(e.source.id);next.push(e.source.id);}}
    }});
    frontier=next;if(!frontier.length) break;
  }}
  return visited;
}}
function ctxFilterNode(){{ if(!ctxNode) return;const k=getNeighborIds(ctxNode,1);nodes.forEach(n=>n.hidden=!k.has(n.id));fitView();closeCtx(); }}
function ctxExpand(d){{ if(!ctxNode) return;const k=getNeighborIds(ctxNode,d);nodes.forEach(n=>n.hidden=!k.has(n.id));fitView();closeCtx(); }}
function ctxPinToggle(){{ if(!ctxNode) return;ctxNode.pinned=!ctxNode.pinned;if(!ctxNode.pinned){{ctxNode.vx=0;ctxNode.vy=0;}}closeCtx(); }}
function ctxCopyLabel(){{ if(!ctxNode) return;if(navigator.clipboard) navigator.clipboard.writeText(ctxNode.label);closeCtx(); }}
function ctxHideNode(){{ if(!ctxNode) return;ctxNode.hidden=true;if(selectedNode===ctxNode) closeInfo();closeCtx(); }}
</script>
"""
