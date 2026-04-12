"""
exporter.py — Export del grafo in formati diversi dall'HTML.

Formati supportati:
  • JSON      — grafo grezzo (nodes + edges)
  • GraphML   — compatibile con Gephi, yEd, Neo4j Desktop
  • Neo4j CSV — nodes.csv + relationships.csv per neo4j-admin import
  • RDF/Turtle — triple RDF per sistemi semantici
  • Cypher    — script .cypher per importazione diretta in Neo4j
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from datetime import datetime


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_id(s: str) -> str:
    """Rende sicura una stringa come attributo XML / identificatore."""
    return re.sub(r"[^\w\-]", "_", s)


def _escape_xml(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))


def _escape_cypher(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


# ── JSON ──────────────────────────────────────────────────────────────────────

def export_json(graph: dict, path: Path) -> None:
    path.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  📄 JSON → {path}")


# ── GraphML ───────────────────────────────────────────────────────────────────

def export_graphml(graph: dict, path: Path) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/graphml"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://graphml.graphdrawing.org/graphml '
        'http://graphml.graphdrawing.org/graphml/1.0/graphml.xsd">',
        '',
        '  <!-- Node attributes -->',
        '  <key id="label"       for="node" attr.name="label"       attr.type="string"/>',
        '  <key id="type"        for="node" attr.name="type"        attr.type="string"/>',
        '  <key id="description" for="node" attr.name="description" attr.type="string"/>',
        '  <key id="properties"  for="node" attr.name="properties"  attr.type="string"/>',
        '',
        '  <!-- Edge attributes -->',
        '  <key id="etype"    for="edge" attr.name="type"     attr.type="string"/>',
        '  <key id="elabel"   for="edge" attr.name="label"    attr.type="string"/>',
        '  <key id="evidence" for="edge" attr.name="evidence" attr.type="string"/>',
        '  <key id="eprops"   for="edge" attr.name="properties" attr.type="string"/>',
        '',
        '  <graph id="G" edgedefault="directed">',
    ]

    for node in graph.get("nodes", []):
        nid   = _escape_xml(node["id"])
        label = _escape_xml(node.get("label", ""))
        ntype = _escape_xml(node.get("type", "Nodo"))
        desc  = _escape_xml(node.get("description", ""))
        props = _escape_xml(json.dumps(node.get("properties", {}), ensure_ascii=False))
        lines += [
            f'    <node id="{nid}">',
            f'      <data key="label">{label}</data>',
            f'      <data key="type">{ntype}</data>',
            f'      <data key="description">{desc}</data>',
            f'      <data key="properties">{props}</data>',
            f'    </node>',
        ]

    for i, edge in enumerate(graph.get("edges", [])):
        src  = _escape_xml(edge["source"])
        tgt  = _escape_xml(edge["target"])
        etype  = _escape_xml(edge.get("type", ""))
        elabel = _escape_xml(edge.get("label", ""))
        evid   = _escape_xml(edge.get("evidence", ""))
        eprops = _escape_xml(json.dumps(edge.get("properties", {}), ensure_ascii=False))
        lines += [
            f'    <edge id="e{i}" source="{src}" target="{tgt}">',
            f'      <data key="etype">{etype}</data>',
            f'      <data key="elabel">{elabel}</data>',
            f'      <data key="evidence">{evid}</data>',
            f'      <data key="eprops">{eprops}</data>',
            f'    </edge>',
        ]

    lines += ["  </graph>", "</graphml>"]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  🗂️  GraphML → {path}")


# ── Neo4j CSV ─────────────────────────────────────────────────────────────────

def export_neo4j_csv(graph: dict, base_path: Path) -> None:
    """
    Genera due file compatibili con neo4j-admin database import:
      <base>_nodes.csv
      <base>_relationships.csv
    """
    nodes_path = base_path.parent / (base_path.stem + "_nodes.csv")
    rels_path  = base_path.parent / (base_path.stem + "_relationships.csv")

    with open(nodes_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([":ID", "label:string", ":LABEL", "description:string",
                    "properties:string"])
        for node in graph.get("nodes", []):
            w.writerow([
                node["id"],
                node.get("label", ""),
                node.get("type", "Nodo"),
                node.get("description", ""),
                json.dumps(node.get("properties", {}), ensure_ascii=False),
            ])

    with open(rels_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([":START_ID", ":END_ID", ":TYPE", "label:string",
                    "evidence:string", "properties:string"])
        for edge in graph.get("edges", []):
            w.writerow([
                edge["source"],
                edge["target"],
                edge.get("type", "RELAZIONATO_A"),
                edge.get("label", ""),
                edge.get("evidence", ""),
                json.dumps(edge.get("properties", {}), ensure_ascii=False),
            ])

    print(f"  📊 Neo4j CSV → {nodes_path.name} + {rels_path.name}")


# ── RDF / Turtle ──────────────────────────────────────────────────────────────

def export_rdf_turtle(graph: dict, path: Path, base_uri: str = "http://doc2graph.local/") -> None:
    lines = [
        f"@prefix d2g: <{base_uri}> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "",
    ]

    type_map: dict[str, str] = {}
    for node in graph.get("nodes", []):
        t = node.get("type", "Nodo")
        if t not in type_map:
            type_map[t] = f"d2g:{_safe_id(t)}"
        nid = _safe_id(node["id"])
        lbl = node.get("label", "").replace('"', '\\"')
        lines.append(f"d2g:{nid}")
        lines.append(f'    rdf:type {type_map[t]} ;')
        lines.append(f'    rdfs:label "{lbl}" ;')
        for k, v in node.get("properties", {}).items():
            v_str = str(v).replace('"', '\\"')
            lines.append(f'    d2g:{_safe_id(k)} "{v_str}" ;')
        lines[-1] = lines[-1].rstrip(" ;") + " ."
        lines.append("")

    for i, edge in enumerate(graph.get("edges", [])):
        src  = _safe_id(edge["source"])
        tgt  = _safe_id(edge["target"])
        etype = _safe_id(edge.get("type", "relazionato_a"))
        evid  = edge.get("evidence", "").replace('"', '\\"')[:200]
        lines.append(f"d2g:{src} d2g:{etype} d2g:{tgt} .")
        if evid:
            lines.append(f'# evidence: "{evid}"')
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  🔗 RDF/Turtle → {path}")


# ── Cypher ────────────────────────────────────────────────────────────────────

def export_cypher(graph: dict, path: Path) -> None:
    lines = [
        f"// Generated by doc2graph — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "// Import: cypher-shell -u neo4j -p password < this_file.cypher",
        "",
    ]

    for node in graph.get("nodes", []):
        ntype = node.get("type", "Nodo")
        label = _escape_cypher(node.get("label", ""))
        desc  = _escape_cypher(node.get("description", ""))
        prop_parts = [f"id: '{node['id']}'", f"name: '{label}'"]
        if desc:
            prop_parts.append(f"description: '{desc}'")
        for k, v in node.get("properties", {}).items():
            prop_parts.append(f"{_safe_id(k)}: '{_escape_cypher(str(v))}'")
        lines.append(f"MERGE (:{ntype} {{{', '.join(prop_parts)}}});")

    lines.append("")

    for edge in graph.get("edges", []):
        etype = edge.get("type", "RELAZIONATO_A")
        lbl   = _escape_cypher(edge.get("label", ""))
        evid  = _escape_cypher(edge.get("evidence", ""))[:200]
        prop_parts = []
        if lbl:
            prop_parts.append(f"label: '{lbl}'")
        if evid:
            prop_parts.append(f"evidence: '{evid}'")
        for k, v in edge.get("properties", {}).items():
            prop_parts.append(f"{_safe_id(k)}: '{_escape_cypher(str(v))}'")
        props_str = f" {{{', '.join(prop_parts)}}}" if prop_parts else ""
        lines.append(
            f"MATCH (a {{id:'{edge['source']}'}}), (b {{id:'{edge['target']}'}}) "
            f"MERGE (a)-[:{etype}{props_str}]->(b);"
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ⚡ Cypher → {path}")


# ── export all ────────────────────────────────────────────────────────────────

def export_all(graph: dict, base_path: Path, formats: list[str]) -> None:
    """
    Esporta il grafo in tutti i formati richiesti.

    Args:
        formats: lista di stringhe tra "json", "graphml", "neo4j", "rdf", "cypher"
    """
    dispatch = {
        "json":    lambda: export_json(graph, base_path.with_suffix(".json")),
        "graphml": lambda: export_graphml(graph, base_path.with_suffix(".graphml")),
        "neo4j":   lambda: export_neo4j_csv(graph, base_path),
        "rdf":     lambda: export_rdf_turtle(graph, base_path.with_suffix(".ttl")),
        "cypher":  lambda: export_cypher(graph, base_path.with_suffix(".cypher")),
    }
    for fmt in formats:
        fn = dispatch.get(fmt.lower())
        if fn:
            try:
                fn()
            except Exception as exc:
                print(f"  ⚠️  Export {fmt} fallito: {exc}")
        else:
            print(f"  ⚠️  Formato export sconosciuto: {fmt}")
