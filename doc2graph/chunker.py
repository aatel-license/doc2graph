"""
chunker.py — Suddivisione del testo in chunk con overlap.

Strategie disponibili:
  • char  — divide per caratteri (default, nessuna dipendenza extra)
  • token — divide per token usando tiktoken (richiede: pip install tiktoken)

La strategia viene scelta automaticamente in base a `use_token_chunking`
nella Config e alla disponibilità di tiktoken.
"""

from __future__ import annotations

import re
from typing import Sequence

from .config import get_config


# ── public API ───────────────────────────────────────────────────────────────

def split_into_chunks(text: str) -> list[str]:
    """
    Divide *text* in chunk secondo la Config corrente.
    Restituisce una lista di stringhe non vuote.
    """
    cfg = get_config()
    if cfg.use_token_chunking:
        try:
            return _split_by_tokens(text, cfg.llm_max_tokens, cfg.chunk_overlap)
        except ImportError:
            print("  ⚠️  tiktoken non installato — uso chunking a caratteri")

    return _split_by_chars(text, cfg.chunk_size, cfg.chunk_overlap)


def estimate_chunks(text: str) -> int:
    """Stima il numero di chunk senza eseguire il taglio."""
    cfg = get_config()
    size = cfg.chunk_size
    overlap = cfg.chunk_overlap
    if len(text) <= size:
        return 1
    step = size - overlap
    return max(1, (len(text) - overlap + step - 1) // step)


# ── strategies ───────────────────────────────────────────────────────────────

def _split_by_chars(text: str, size: int, overlap: int) -> list[str]:
    """Split classico a caratteri con prefer-paragraph boundary."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size

        if end < len(text):
            # Preferisci tagliare su doppio-newline, poi singolo
            cut = text.rfind("\n\n", start, end)
            if cut == -1:
                cut = text.rfind("\n", start, end)
            if cut != -1 and cut > start:
                end = cut

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        start = end - overlap

    return chunks


def _split_by_tokens(text: str, max_tokens: int, overlap_chars: int) -> list[str]:
    """
    Split preciso in token via tiktoken.
    `overlap_chars` viene convertito approssimativamente in token (÷4).
    """
    import tiktoken  # type: ignore

    # Usa cl100k_base come encoding universale (GPT-4 / Claude-compat)
    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        enc = tiktoken.get_encoding("gpt2")

    overlap_tokens = max(0, overlap_chars // 4)
    step = max(1, max_tokens - overlap_tokens)

    tokens = enc.encode(text)
    chunks: list[str] = []

    for start in range(0, len(tokens), step):
        slice_ = tokens[start: start + max_tokens]
        chunk = enc.decode(slice_).strip()
        if chunk:
            chunks.append(chunk)

    return chunks


# ── dry-run helper ────────────────────────────────────────────────────────────

def dry_run_info(files_and_texts: Sequence[tuple[str, str]]) -> None:
    """
    Stampa una stima del numero di chunk e token per ciascun file.
    Usato con --dry-run dalla CLI.
    """
    cfg = get_config()
    total_chunks = 0

    print("\n📊  Dry-run — nessuna chiamata LLM verrà effettuata\n")
    print(f"  Config: chunk_size={cfg.chunk_size}  overlap={cfg.chunk_overlap}"
          f"  workers={cfg.parallel_workers}  model={cfg.llm_model or 'auto'}\n")
    print(f"  {'File':<40} {'Chars':>8} {'Chunks':>7} {'~Tokens':>8}")
    print("  " + "-" * 65)

    for fname, text in files_and_texts:
        n_chunks = estimate_chunks(text)
        n_chars  = len(text)
        n_tokens = n_chars // 4  # stima 4 char/token
        total_chunks += n_chunks
        print(f"  {fname:<40} {n_chars:>8,} {n_chunks:>7} {n_tokens:>8,}")

    print("  " + "-" * 65)
    print(f"  {'TOTALE':<40} {'':>8} {total_chunks:>7}\n")

    # Stima costo in richieste LLM
    w = cfg.parallel_workers
    est_minutes = total_chunks * 30 / max(1, w) / 60
    print(f"  Stima richieste LLM:  {total_chunks}")
    print(f"  Con {w} worker(s):     ~{est_minutes:.1f} min (30s/chunk)\n")
