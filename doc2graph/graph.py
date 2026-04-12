"""
graph.py — Operazioni sul grafo di conoscenza.

  • merge_graphs    : unifica più grafi (fuzzy dedup sui nodi)
  • prune_graph     : rimuove orfani, self-loop, duplicati
  • normalize_label : normalizzazione stringa per confronto
"""

from __future__ import annotations

import re
import unicodedata

from .config import get_config


# ── normalizzazione ───────────────────────────────────────────────────────────

def normalize_label(label: str) -> str:
    s = label.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ── fuzzy helper ──────────────────────────────────────────────────────────────

def _fuzzy_ratio(a: str, b: str) -> int:
    """
    Restituisce un punteggio [0,100] di similarità.
    Usa rapidfuzz se disponibile, altrimenti SequenceMatcher.
    """
    try:
        from rapidfuzz import fuzz  # type: ignore
        return int(fuzz.ratio(a, b))
    except ImportError:
        from difflib import SequenceMatcher
        return int(SequenceMatcher(None, a, b).ratio() * 100)


def _find_existing_key(
    label: str,
    ntype: str,
    all_nodes: dict[str, dict],
    threshold: int,
) -> str | None:
    """
    Cerca un nodo già presente con lo stesso tipo e label simile.
    Restituisce la chiave se trovato, None altrimenti.
    """
    norm = normalize_label(label)
    exact_key = f"{norm}::{ntype.lower()}"
    if exact_key in all_nodes:
        return exact_key

    # Fuzzy scan (solo stesso tipo)
    for key, node in all_nodes.items():
        if node["type"].lower() != ntype.lower():
            continue
        existing_norm = normalize_label(node["label"])
        if _fuzzy_ratio(norm, existing_norm) >= threshold:
            return key

    return None


# ── merge ─────────────────────────────────────────────────────────────────────

def merge_graphs(graph_list: list[dict]) -> dict:
    """
    Unifica più grafi in uno solo.

    Deduplicazione nodi:
      - Chiave esatta: normalize_label(label)::type.lower()
      - Fuzzy match: se similarità >= FUZZY_MERGE_THRESHOLD (default 90)
        → stesso nodo, properties vengono unite

    Properties vengono unite (il valore più recente sovrascrive).
    """
    cfg = get_config()
    threshold = cfg.fuzzy_merge_threshold

    all_nodes: dict[str, dict] = {}   # key → node dict
    all_edges: list[dict] = []
    counter = 0

    for g in graph_list:
        local_map: dict[str, str] = {}   # orig_id → global_id

        for node in g.get("nodes", []):
            orig_id = node.get("id", "")
            label   = (node.get("label") or "").strip()
            ntype   = (node.get("type") or "Nodo").strip()

            existing_key = _find_existing_key(label, ntype, all_nodes, threshold)

            if existing_key:
                # Merge properties
                existing = all_nodes[existing_key]
                existing["properties"] = {
                    **existing.get("properties", {}),
                    **node.get("properties", {}),
                }
                if not existing.get("description") and node.get("description"):
                    existing["description"] = node["description"]
                global_id = existing["id"]
            else:
                counter += 1
                global_id = f"n{counter}"
                norm_key  = f"{normalize_label(label)}::{ntype.lower()}"
                all_nodes[norm_key] = {
                    "id":          global_id,
                    "label":       label,
                    "type":        ntype,
                    "properties":  node.get("properties", {}),
                    "description": node.get("description", ""),
                }

            local_map[orig_id] = global_id

        for edge in g.get("edges", []):
            src = local_map.get(edge.get("source", ""), "")
            tgt = local_map.get(edge.get("target", ""), "")
            if src and tgt:
                all_edges.append({
                    "source":     src,
                    "target":     tgt,
                    "type":       edge.get("type", "RELAZIONATO_A"),
                    "label":      edge.get("label", ""),
                    "properties": edge.get("properties", {}),
                    "evidence":   edge.get("evidence", ""),
                })

    return {
        "nodes": list(all_nodes.values()),
        "edges": all_edges,
    }


# ── prune ─────────────────────────────────────────────────────────────────────

def prune_graph(graph: dict) -> dict:
    """
    Rimuove:
      • Edge con source o target inesistente (orfani)
      • Self-loop (source == target)
      • Edge duplicati (stessa terna source, target, type)
    """
    valid_ids = {n["id"] for n in graph["nodes"]}

    clean_edges = [
        e for e in graph["edges"]
        if e["source"] in valid_ids
        and e["target"] in valid_ids
        and e["source"] != e["target"]
    ]

    seen: set[tuple] = set()
    dedup_edges: list[dict] = []
    for e in clean_edges:
        key = (e["source"], e["target"], e["type"])
        if key not in seen:
            seen.add(key)
            dedup_edges.append(e)

    removed = len(graph["edges"]) - len(dedup_edges)
    if removed:
        print(f"  🧹 Prune: rimossi {removed} archi (orfani/duplicati/self-loop)")

    graph["edges"] = dedup_edges
    return graph


# ── stats ─────────────────────────────────────────────────────────────────────

def graph_stats(graph: dict) -> dict:
    """Restituisce statistiche base del grafo."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "Nodo")
        type_counts[t] = type_counts.get(t, 0) + 1

    edge_type_counts: dict[str, int] = {}
    for e in edges:
        t = e.get("type", "?")
        edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "node_types": type_counts,
        "edge_types": edge_type_counts,
        "isolated_nodes": _count_isolated(graph),
    }


def _count_isolated(graph: dict) -> int:
    connected = set()
    for e in graph.get("edges", []):
        connected.add(e["source"])
        connected.add(e["target"])
    return sum(1 for n in graph.get("nodes", []) if n["id"] not in connected)
