"""
cli.py — Interfaccia a riga di comando per doc2graph.

Uso base:
    python -m doc2graph file1.pdf file2.docx -o output.html

Modalità merge (zero LLM):
    python -m doc2graph --merge-jsons a.json b.json -o result.html

Dry-run (stima chunk, nessuna chiamata LLM):
    python -m doc2graph --dry-run file1.pdf file2.pdf

Export aggiuntivi:
    python -m doc2graph file.pdf --export json graphml cypher
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="doc2graph",
        description="Estrae un knowledge graph da documenti e genera un visualizzatore HTML.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  %(prog)s report.pdf                        → graph_report.html
  %(prog)s *.pdf *.docx -o unified.html      → grafo unificato
  %(prog)s file.pdf --export json graphml    → HTML + JSON + GraphML
  %(prog)s --merge-jsons a.json b.json -o m.html
  %(prog)s --dry-run file1.pdf file2.pdf     → stima senza LLM
  %(prog)s --resume file.pdf                 → riprende da checkpoint
        """,
    )

    # ── Input ─────────────────────────────────────────────────────────────────
    p.add_argument(
        "files", nargs="*", metavar="FILE",
        help="File o glob da processare (es: *.pdf docs/*.docx)",
    )

    # ── Modalità speciali ──────────────────────────────────────────────────────
    p.add_argument(
        "--merge-jsons", nargs="+", metavar="JSON",
        help="Unisce grafi JSON già estratti (zero LLM)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Stima chunk e token senza chiamare il LLM",
    )

    # ── Output ────────────────────────────────────────────────────────────────
    p.add_argument(
        "-o", "--output", metavar="FILE",
        help="File HTML di output (default: graph_<nome>.html)",
    )
    p.add_argument(
        "--export", nargs="+", metavar="FMT",
        choices=["json", "graphml", "neo4j", "rdf", "cypher"],
        default=[],
        help="Formati di export aggiuntivi: json graphml neo4j rdf cypher",
    )

    # ── Processing ────────────────────────────────────────────────────────────
    p.add_argument(
        "--no-resume", action="store_true",
        help="Ignora checkpoint esistenti e riparte da zero",
    )
    p.add_argument(
        "--no-enrich", action="store_true",
        help="Salta l'arricchimento delle relazioni generiche",
    )
    p.add_argument(
        "--verify", action="store_true",
        help="Abilita verifica LLM degli archi (lento ma più preciso)",
    )
    p.add_argument(
        "--workers", type=int, metavar="N",
        help="Numero di worker paralleli per chunk (default: 1)",
    )

    # ── LLM override ─────────────────────────────────────────────────────────
    p.add_argument("--model",  metavar="ID",  help="Modello LLM (sovrascrive LLM_MODEL nel .env)")
    p.add_argument("--url",    metavar="URL", help="Base URL LLM (sovrascrive LLM_BASE_URL)")
    p.add_argument("--tokens", type=int,      help="Max token risposta (sovrascrive LLM_MAX_TOKENS)")
    p.add_argument("--chunk-size",    type=int, help="Dimensione chunk in caratteri")
    p.add_argument("--chunk-overlap", type=int, help="Overlap tra chunk in caratteri")

    # ── Misc ─────────────────────────────────────────────────────────────────
    p.add_argument("--stats", action="store_true", help="Stampa statistiche del grafo finale")
    p.add_argument("--version", action="version", version="doc2graph 2.0.0")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ── Carica + patch Config ─────────────────────────────────────────────────
    from .config import Config, set_config
    cfg = Config()

    if args.model:       cfg.llm_model = args.model
    if args.url:         cfg.llm_base_url = args.url
    if args.tokens:      cfg.llm_max_tokens = args.tokens
    if args.workers:     cfg.parallel_workers = args.workers
    if args.chunk_size:  cfg.chunk_size = args.chunk_size
    if args.chunk_overlap: cfg.chunk_overlap = args.chunk_overlap

    set_config(cfg)

    # ── Modalità merge-jsons ──────────────────────────────────────────────────
    if args.merge_jsons:
        return _run_merge_jsons(args)

    # ── Espandi glob ──────────────────────────────────────────────────────────
    paths = _resolve_files(args.files)
    if not paths:
        parser.print_help()
        print("\n❌ Nessun file valido trovato.")
        return 1

    # ── Dry-run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        return _run_dry_run(paths)

    # ── Elaborazione reale ────────────────────────────────────────────────────
    from .pipeline import process_file, process_files
    from .renderer import build_html
    from .exporter import export_all

    resume   = not args.no_resume
    no_enrich = args.no_enrich
    no_verify = not args.verify

    if len(paths) == 1:
        graph = process_file(
            paths[0],
            resume=resume,
            no_enrich=no_enrich,
            no_verify=no_verify,
        )
        doc_name = paths[0].stem
    else:
        graph = process_files(
            paths,
            resume=resume,
            no_enrich=no_enrich,
            no_verify=no_verify,
        )
        doc_name = f"{len(paths)}_files"

    if not graph["nodes"]:
        print("\n⚠️  Grafo vuoto — nessun output generato.")
        return 1

    # ── Statistiche ────────────────────────────────────────────────────────────
    if args.stats:
        from .graph import graph_stats
        s = graph_stats(graph)
        print(f"\n📊 Statistiche grafo:")
        print(f"   Nodi:          {s['nodes']}")
        print(f"   Archi:         {s['edges']}")
        print(f"   Tipi nodo:     {s['node_types']}")
        print(f"   Tipi relazione:{len(s['edge_types'])}")
        print(f"   Nodi isolati:  {s['isolated_nodes']}")

    # ── Output HTML ────────────────────────────────────────────────────────────
    out_html = Path(args.output) if args.output else Path(f"graph_{doc_name}.html")
    build_html(graph, doc_name, out_html)

    # ── Export aggiuntivi ──────────────────────────────────────────────────────
    if args.export:
        base = out_html.with_suffix("")
        export_all(graph, base, args.export)

    print(f"\n✨ Completato → {out_html.resolve()}")
    return 0


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_files(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pat in patterns:
        expanded = glob.glob(pat, recursive=True)
        if expanded:
            paths.extend(Path(p) for p in expanded)
        else:
            p = Path(pat)
            if p.exists():
                paths.append(p)
            else:
                print(f"  ⚠️  File non trovato: {pat}")
    # Deduplica mantenendo ordine
    seen: set[Path] = set()
    result: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _run_merge_jsons(args: argparse.Namespace) -> int:
    from .pipeline import merge_json_files
    from .renderer import build_html
    from .exporter import export_all

    json_paths = [Path(p) for p in args.merge_jsons]
    missing = [p for p in json_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"❌ File non trovato: {p}")
        return 1

    print(f"🔗 Merge di {len(json_paths)} file JSON (zero LLM)…")
    graph = merge_json_files(json_paths)

    if not graph["nodes"]:
        print("⚠️  Grafo vuoto.")
        return 1

    out_html = Path(args.output) if args.output else Path("graph_merged.html")
    build_html(graph, "merged", out_html)

    if args.export:
        export_all(graph, out_html.with_suffix(""), args.export)

    print(f"\n✨ Completato → {out_html.resolve()}")
    return 0


def _run_dry_run(paths: list[Path]) -> int:
    from .extractors import extract_text
    from .chunker import dry_run_info

    texts: list[tuple[str, str]] = []
    for p in paths:
        print(f"  📄 Leggo {p.name}…")
        t = extract_text(p)
        texts.append((p.name, t))

    dry_run_info(texts)
    return 0
