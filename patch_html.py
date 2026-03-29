"""
ISTRUZIONI: esegui questo script nella stessa cartella di doc2graph.py
Applica automaticamente le 3 patch al file originale.

    python patch_doc2graph.py
"""

from pathlib import Path
import sys

TARGET = Path("doc2graph_multi_files.py")

if not TARGET.exists():
    print(f"❌  {TARGET} non trovato nella cartella corrente.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 1 — CSS context menu
# ─────────────────────────────────────────────────────────────────────────────
OLD_CSS = """.mo.show{{display:flex}}"""

NEW_CSS = """.mo.show{{display:flex}}
#ctx-menu{{
  position:fixed;display:none;z-index:200;
  background:var(--panel);border:1px solid var(--border);
  border-radius:8px;padding:5px 0;min-width:190px;
  box-shadow:0 8px 28px rgba(0,0,0,.6);font-size:13px;
}}
#ctx-menu .ctx-title{{
  padding:5px 14px 3px;font-size:10px;
  text-transform:uppercase;letter-spacing:1px;color:var(--dim);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;
}}
#ctx-menu .ctx-sep{{height:1px;background:var(--border);margin:4px 0}}
#ctx-menu .ctx-item{{
  display:flex;align-items:center;gap:9px;padding:7px 14px;
  cursor:pointer;color:var(--text);transition:.12s;user-select:none;
}}
#ctx-menu .ctx-item:hover{{background:var(--panel2);color:#fff}}
#ctx-menu .ctx-item.danger{{color:#ff8080}}
#ctx-menu .ctx-item.danger:hover{{background:#5a1010}}"""

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 2 — HTML menu (cerca il div del modal cypher e aggiunge il menu prima)
# ─────────────────────────────────────────────────────────────────────────────
OLD_HTML = """<div class="mo" id="cm">"""

NEW_HTML = """<div id="ctx-menu">
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

<div class="mo" id="cm">"""

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 3 — JavaScript context menu (aggiunge dopo dlCy)
# ─────────────────────────────────────────────────────────────────────────────
OLD_JS = """function dlCy(){{
  const a=document.createElement("a");
  a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(CYPHER);
  a.download="graph.cypher";a.click();
}}"""

NEW_JS = """function dlCy(){{
  const a=document.createElement("a");
  a.href="data:text/plain;charset=utf-8,"+encodeURIComponent(CYPHER);
  a.download="graph.cypher";a.click();
}}

// ── Context menu ────────────────────────────────────────────────────────────
let ctxNode=null;

function closeCtx(){{
  document.getElementById("ctx-menu").style.display="none";
  ctxNode=null;
}}

canvas.addEventListener("contextmenu",function(e){{
  e.preventDefault();
  var r=canvas.getBoundingClientRect();
  var n=nodeAt(e.clientX-r.left, e.clientY-r.top);
  if(!n){{ closeCtx(); return; }}
  ctxNode=n;
  selectedNode=n;
  showInfo(n);
  document.getElementById("ctx-node-name").textContent=n.label+" ["+n.type+"]";
  document.getElementById("ctx-pin-lbl").textContent=n.pinned?"Sblocca posizione":"Fissa posizione";
  var menu=document.getElementById("ctx-menu");
  menu.style.display="block";
  var mw=menu.offsetWidth, mh=menu.offsetHeight;
  var vw=window.innerWidth,  vh=window.innerHeight;
  menu.style.left=(e.clientX+mw>vw ? e.clientX-mw : e.clientX+4)+"px";
  menu.style.top =(e.clientY+mh>vh ? e.clientY-mh : e.clientY+4)+"px";
}});

document.addEventListener("click", closeCtx);
document.addEventListener("keydown",function(e){{ if(e.key==="Escape") closeCtx(); }});

function getNeighborIds(startNode, depth){{
  var visited=new Set([startNode.id]);
  var frontier=[startNode.id];
  for(var d=0;d<depth;d++){{
    var next=[];
    edges.forEach(function(e){{
      if(frontier.indexOf(e.source.id)!==-1 && !visited.has(e.target.id)){{
        visited.add(e.target.id); next.push(e.target.id);
      }}
      if(frontier.indexOf(e.target.id)!==-1 && !visited.has(e.source.id)){{
        visited.add(e.source.id); next.push(e.source.id);
      }}
    }});
    frontier=next;
    if(!frontier.length) break;
  }}
  return visited;
}}

function ctxFilterNode(){{
  if(!ctxNode) return;
  var keep=getNeighborIds(ctxNode,1);
  nodes.forEach(function(n){{ n.hidden=!keep.has(n.id); }});
  fitView(); closeCtx();
}}

function ctxExpand(depth){{
  if(!ctxNode) return;
  var keep=getNeighborIds(ctxNode,depth);
  nodes.forEach(function(n){{ n.hidden=!keep.has(n.id); }});
  fitView(); closeCtx();
}}

function ctxPinToggle(){{
  if(!ctxNode) return;
  ctxNode.pinned=!ctxNode.pinned;
  if(!ctxNode.pinned){{ ctxNode.vx=0; ctxNode.vy=0; }}
  closeCtx();
}}

function ctxCopyLabel(){{
  if(!ctxNode) return;
  if(navigator.clipboard) navigator.clipboard.writeText(ctxNode.label);
  closeCtx();
}}

function ctxHideNode(){{
  if(!ctxNode) return;
  ctxNode.hidden=true;
  if(selectedNode===ctxNode) closeInfo();
  closeCtx();
}}"""

# ─────────────────────────────────────────────────────────────────────────────
# APPLICA LE PATCH
# ─────────────────────────────────────────────────────────────────────────────
errors = []

if OLD_CSS not in src:
    errors.append("❌  PATCH 1 (CSS): stringa non trovata — controlla che doc2graph.py non sia già patchato")
if OLD_HTML not in src:
    errors.append("❌  PATCH 2 (HTML): stringa non trovata")
if OLD_JS not in src:
    errors.append("❌  PATCH 3 (JS): stringa non trovata")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)

patched = src
patched = patched.replace(OLD_CSS,  NEW_CSS,  1)
patched = patched.replace(OLD_HTML, NEW_HTML, 1)
patched = patched.replace(OLD_JS,   NEW_JS,   1)

# Backup
backup = TARGET.with_suffix(".py.bak")
backup.write_text(src, encoding="utf-8")
print(f"💾  Backup salvato → {backup}")

TARGET.write_text(patched, encoding="utf-8")
print("✅  PATCH 1 (CSS)  applicata")
print("✅  PATCH 2 (HTML) applicata")
print("✅  PATCH 3 (JS)   applicata")
print(f"\n🎉  {TARGET} aggiornato con successo!")
print("    Rigenera i tuoi HTML con doc2graph.py per vedere il context menu.")