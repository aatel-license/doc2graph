"""
checkpoint.py — Salvataggio e ripristino del progresso.

Granularità: per singolo chunk (non per file intero).
Il checkpoint viene scritto atomicamente via file temporaneo + rename.

Formato del file .checkpoint.json:
{
  "version": 2,
  "file": "percorso/originale.pdf",
  "chunks_total": 12,
  "chunks_done": [0, 1, 2],      ← indici già processati
  "partial_graphs": [ {...}, ... ] ← risultati chunk done
}
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


_VERSION = 2


def checkpoint_path(input_path: Path) -> Path:
    return input_path.parent / (input_path.stem + ".checkpoint.json")


# ── load ──────────────────────────────────────────────────────────────────────

def load_checkpoint(input_path: Path) -> dict | None:
    cp = checkpoint_path(input_path)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        if data.get("version") != _VERSION:
            print(f"  ⚠️  Checkpoint versione {data.get('version')} obsoleto — ignorato")
            return None
        n_done = len(data.get("chunks_done", []))
        n_tot  = data.get("chunks_total", "?")
        print(f"  ♻️  Checkpoint trovato → {cp.name}  "
              f"({n_done}/{n_tot} chunk già processati)")
        return data
    except Exception as exc:
        print(f"  ⚠️  Checkpoint corrotto ({exc}) — ignorato")
        return None


# ── save ──────────────────────────────────────────────────────────────────────

def save_checkpoint(input_path: Path, state: dict) -> None:
    """Scrittura atomica: scrive su tmp poi rinomina."""
    state["version"] = _VERSION
    state["file"] = str(input_path)
    cp = checkpoint_path(input_path)
    try:
        fd, tmp = tempfile.mkstemp(dir=cp.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, cp)
    except Exception as exc:
        print(f"  ⚠️  Impossibile salvare checkpoint: {exc}")


def clear_checkpoint(input_path: Path) -> None:
    cp = checkpoint_path(input_path)
    if cp.exists():
        try:
            cp.unlink()
        except Exception:
            pass


# ── incremental helpers ───────────────────────────────────────────────────────

class ChunkProgress:
    """
    Gestisce il progresso chunk-per-chunk per un singolo file.

    Uso:
        prog = ChunkProgress(input_path, total_chunks)
        prog.resume()   # carica dati esistenti se presenti

        for i, chunk in enumerate(chunks):
            if prog.is_done(i):
                continue
            result = llm_extract_graph(chunk, ...)
            prog.mark_done(i, result)   # salva immediatamente

        all_results = prog.results()
        prog.clear()
    """

    def __init__(self, input_path: Path, total_chunks: int) -> None:
        self._path = input_path
        self._total = total_chunks
        self._done: set[int] = set()
        self._graphs: dict[int, dict] = {}

    def resume(self) -> bool:
        """Carica checkpoint se esiste. Restituisce True se c'erano dati."""
        state = load_checkpoint(self._path)
        if state is None:
            return False
        self._done  = set(state.get("chunks_done", []))
        # Ricostruisce la mappa indice → grafo
        graphs_list = state.get("partial_graphs", [])
        done_list   = sorted(self._done)
        for i, idx in enumerate(done_list):
            if i < len(graphs_list):
                self._graphs[idx] = graphs_list[i]
        return bool(self._done)

    def is_done(self, idx: int) -> bool:
        return idx in self._done

    def mark_done(self, idx: int, graph: dict) -> None:
        self._done.add(idx)
        self._graphs[idx] = graph
        self._persist()

    def _persist(self) -> None:
        done_sorted = sorted(self._done)
        save_checkpoint(self._path, {
            "chunks_total":   self._total,
            "chunks_done":    done_sorted,
            "partial_graphs": [self._graphs[i] for i in done_sorted],
        })

    def results(self) -> list[dict]:
        """Restituisce i grafi nell'ordine originale dei chunk."""
        return [self._graphs[i] for i in sorted(self._graphs.keys())]

    def clear(self) -> None:
        clear_checkpoint(self._path)
