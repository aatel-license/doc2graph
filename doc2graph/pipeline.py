"""
pipeline.py — Orchestrazione del processo di estrazione.

  process_file      : estrae grafo da un singolo file
  process_files     : unifica più file in un grafo solo
  merge_json_files  : --merge-jsons mode (zero LLM)
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .checkpoint import ChunkProgress
from .chunker import split_into_chunks
from .config import get_config
from .extractors import extract_text
from .graph import merge_graphs, prune_graph
from .llm import enrich_relations, llm_extract_graph, llm_verify_relations

# ── progress bar (opzionale) ──────────────────────────────────────────────────

try:
    from rich.progress import (  # type: ignore
        Progress, SpinnerColumn, BarColumn,
        TextColumn, TimeElapsedColumn, MofNCompleteColumn,
    )
    _RICH = True
except ImportError:
    _RICH = False


# ── single file ───────────────────────────────────────────────────────────────

def process_file(
    path: Path,
    *,
    resume: bool = True,
    no_enrich: bool = False,
    no_verify: bool = True,
) -> dict:
    """
    Estrae un grafo da *path*.

    Args:
        resume     : se True, riprende da checkpoint se esiste
        no_enrich  : salta la fase di arricchimento relazioni
        no_verify  : salta la verifica LLM (lenta e costosa)

    Returns:
        dict con "nodes" e "edges"
    """
    cfg = get_config()

    print(f"\n{'─'*60}")
    print(f"📄 {path.name}")
    print(f"{'─'*60}")

    # 1. Estrai testo
    text = extract_text(path)
    if not text.strip():
        print("  ⚠️  Nessun testo estratto — file saltato")
        return {"nodes": [], "edges": []}

    print(f"  📝 Testo estratto: {len(text):,} caratteri")

    # 2. Chunk
    chunks = split_into_chunks(text)
    print(f"  ✂️  {len(chunks)} chunk (size={cfg.chunk_size}, overlap={cfg.chunk_overlap})")

    # 3. Checkpoint
    prog = ChunkProgress(path, len(chunks))
    if resume:
        prog.resume()

    # 4. Estrazione grafo (sequenziale o parallela)
    workers = cfg.parallel_workers
    todo = [i for i in range(len(chunks)) if not prog.is_done(i)]

    if todo:
        if workers > 1 and len(todo) > 1:
            _extract_parallel(chunks, todo, prog, workers)
        else:
            _extract_sequential(chunks, todo, prog)

    partial_graphs = prog.results()

    # 5. Merge dei grafi parziali
    print(f"\n  🔗 Merge di {len(partial_graphs)} grafi parziali…")
    merged = merge_graphs(partial_graphs)
    merged = prune_graph(merged)

    # 6. Post-processing
    if not no_enrich:
        merged = enrich_relations(merged)

    if not no_verify and merged["edges"]:
        merged = llm_verify_relations(merged)

    # 7. Pulisci checkpoint (successo)
    prog.clear()

    n = len(merged["nodes"])
    e = len(merged["edges"])
    print(f"\n  ✅ Grafo finale: {n} nodi, {e} archi")
    return merged


def _extract_sequential(
    chunks: list[str],
    todo: list[int],
    prog: ChunkProgress,
) -> None:
    total = len(chunks)
    if _RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as bar:
            task = bar.add_task("Estrazione chunk", total=len(todo))
            for idx in todo:
                result = llm_extract_graph(chunks[idx], idx + 1, total)
                prog.mark_done(idx, result)
                bar.advance(task)
    else:
        for idx in todo:
            result = llm_extract_graph(chunks[idx], idx + 1, total)
            prog.mark_done(idx, result)


def _extract_parallel(
    chunks: list[str],
    todo: list[int],
    prog: ChunkProgress,
    workers: int,
) -> None:
    total = len(chunks)
    print(f"  ⚡ Modalità parallela: {workers} worker(s)")

    futures_map: dict = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for idx in todo:
            f = ex.submit(llm_extract_graph, chunks[idx], idx + 1, total)
            futures_map[f] = idx

        if _RICH:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            ) as bar:
                task = bar.add_task("Estrazione parallela", total=len(todo))
                for future in as_completed(futures_map):
                    idx = futures_map[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        print(f"\n  ⚠️  Chunk {idx} fallito: {exc}")
                        result = {"nodes": [], "edges": []}
                    prog.mark_done(idx, result)
                    bar.advance(task)
        else:
            for future in as_completed(futures_map):
                idx = futures_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"\n  ⚠️  Chunk {idx} fallito: {exc}")
                    result = {"nodes": [], "edges": []}
                prog.mark_done(idx, result)


# ── multi-file ────────────────────────────────────────────────────────────────

def process_files(
    paths: list[Path],
    *,
    resume: bool = True,
    no_enrich: bool = False,
    no_verify: bool = True,
) -> dict:
    """
    Processa più file e unifica i grafi in uno solo.
    """
    all_graphs: list[dict] = []

    for path in paths:
        try:
            g = process_file(path, resume=resume, no_enrich=True, no_verify=True)
            all_graphs.append(g)
        except Exception as exc:
            print(f"\n  ❌ Errore su {path.name}: {exc}")

    if not all_graphs:
        return {"nodes": [], "edges": []}

    print(f"\n{'='*60}")
    print(f"🔗 Merge finale di {len(all_graphs)} file…")
    merged = merge_graphs(all_graphs)
    merged = prune_graph(merged)

    if not no_enrich:
        merged = enrich_relations(merged)

    if not no_verify and merged["edges"]:
        merged = llm_verify_relations(merged)

    print(f"\n✅ Grafo unificato: {len(merged['nodes'])} nodi, {len(merged['edges'])} archi")
    return merged


# ── merge-jsons mode (zero LLM) ───────────────────────────────────────────────

def merge_json_files(json_paths: list[Path]) -> dict:
    """
    Unisce grafi già estratti (file .json) senza chiamare il LLM.
    """
    graphs: list[dict] = []
    for jp in json_paths:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            graphs.append(data)
            print(f"  📥 {jp.name}: {len(data.get('nodes',[]))} nodi, "
                  f"{len(data.get('edges',[]))} archi")
        except Exception as exc:
            print(f"  ⚠️  {jp.name}: {exc}")

    if not graphs:
        return {"nodes": [], "edges": []}

    merged = merge_graphs(graphs)
    merged = prune_graph(merged)
    print(f"\n✅ Merge completato: {len(merged['nodes'])} nodi, {len(merged['edges'])} archi")
    return merged
