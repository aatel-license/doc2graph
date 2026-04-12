"""
llm.py — Tutto ciò che riguarda le chiamate al modello LLM.

Responsabilità:
  • _call_llm          : chiamata con retry + backoff (gestisce RateLimitError)
  • llm_extract_graph  : estrazione grafo da un chunk di testo
  • enrich_relations   : arricchisce edge con tipo generico
  • llm_verify_relations: verifica la validità degli edge (tutti, a batch)
  • safe_parse_llm_json: parsing JSON robusto con 4 strategie fallback
  • repair_json        : riparazione JSON malformato
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any

from openai import OpenAI, RateLimitError  # type: ignore

from .config import get_config

# ── client singleton ──────────────────────────────────────────────────────────

_client: OpenAI | None = None
_resolved_model: str = ""


def get_client() -> OpenAI:
    global _client
    if _client is None:
        cfg = get_config()
        _client = OpenAI(base_url=cfg.llm_base_url, api_key=cfg.llm_api_key)
    return _client


def resolve_model() -> str:
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    cfg = get_config()
    if cfg.llm_model:
        _resolved_model = cfg.llm_model
        return _resolved_model

    print("⚠️  LLM_MODEL non impostato — auto-discovery…")
    try:
        models = get_client().models.list()
        available = [m.id for m in models.data]
        if not available:
            raise RuntimeError("Nessun modello disponibile sul server LLM.")
        _resolved_model = available[0]
        print(f"  Modelli disponibili: {available}")
        print(f"  ✅ Uso: {_resolved_model}")
        return _resolved_model
    except Exception as exc:
        raise SystemExit(
            f"❌ Impossibile interrogare {cfg.llm_base_url}/models: {exc}\n"
            "   Verifica che il server LLM sia avviato e raggiungibile."
        ) from exc


# ── prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei un esperto di knowledge graph e Neo4j.
Il tuo compito è analizzare testo ed estrarne un grafo di conoscenza strutturato.
Rispondi ESCLUSIVAMENTE con un JSON valido, senza markdown, senza backtick, senza spiegazioni.

Struttura obbligatoria:
{
  "nodes": [
    {
      "id": "n1",
      "label": "NomeNodo",
      "type": "Categoria",
      "properties": { "chiave": "valore" },
      "description": "Breve descrizione opzionale"
    }
  ],
  "edges": [
    {
      "source": "n1",
      "target": "n2",
      "type": "TIPO_RELAZIONE",
      "label": "etichetta leggibile breve",
      "properties": { "dal": "2020", "ruolo": "CEO" },
      "evidence": "frase testuale che giustifica questa relazione"
    }
  ]
}

REGOLE SUI NODI:
- Tipi concisi: Persona, Organizzazione, Concetto, Prodotto, Evento, Luogo, Tecnologia, Legge, Dato, Documento
- Estrai nelle properties SOLO valori esplicitamente citati (date, numeri, ruoli, stati)
- Max 5 properties per nodo
- Gli id devono essere stringhe univoche brevi (n1, n2, ...)

REGOLE CRITICHE SULLE RELAZIONI:
1. MAI usare relazioni generiche. Sono VIETATE: RELAZIONATO_A, CONNESSO_A, ASSOCIATO_A,
   COLLEGATO_A, MENZIONA, HA_RELAZIONE, E_CONNESSO, APPARTIENE.
   Ogni relazione deve descrivere il VERBO PRECISO del testo.

2. Il campo "type" deve essere il verbo in MAIUSCOLO_UNDERSCORE ricavato letteralmente dal testo.
   Esempi CORRETTI:
   - "Mario ha fondato Acme" → FONDA
   - "La legge vieta l'uso di X" → VIETA_USO_DI
   - "Il sistema elabora i dati" → ELABORA
   - "L'azienda acquisisce il competitor" → ACQUISISCE
   - "Il contratto scade nel 2025" → SCADE_IN

3. Il campo "label" è una frase brevissima (max 5 parole) leggibile da umano.

4. Nelle "properties" degli edge metti i dettagli quantitativi se presenti:
   data, durata, importo, modalità, condizione, percentuale, ruolo specifico.

5. Includi SOLO relazioni ESPLICITAMENTE dichiarate nel testo.
   Ogni edge DEVE avere "evidence": citazione testuale diretta che la giustifica.

6. NON aggiungere IS_A, PART_OF, INSTANCE_OF se non scritti nel testo.
"""

ENRICH_PROMPT = """Sei un esperto di knowledge graph.
Ricevi un JSON con nodes e edges. Alcuni edges hanno type generico o label vuota.

Il tuo compito:
1. Per ogni edge con type generico: sostituiscilo con il verbo preciso ricavato dall'evidence.
2. Per ogni edge con label vuota: scrivi una label leggibile di max 5 parole.
3. Aggiungi properties se l'evidence contiene dettagli (date, importi, ruoli, condizioni).
4. NON aggiungere, rimuovere o spostare nodi o edges: migliora solo type, label, properties.

Tipi generici DA SOSTITUIRE: RELAZIONATO_A, CONNESSO_A, ASSOCIATO_A, COLLEGATO_A,
MENZIONA, HA_RELAZIONE, E_CONNESSO, APPARTIENE, RIFERITO_A, LEGATO_A,
RELATED_TO, CONNECTED_TO, ASSOCIATED_WITH, LINKED_TO, MENTIONS.

Rispondi ESCLUSIVAMENTE con il JSON aggiornato, stesso formato dell'input, senza markdown.
"""

VERIFY_PROMPT = """Sei un revisore di knowledge graph.
Valuta le seguenti relazioni estratte da un documento.
Per ognuna indica se è valida in base all'evidence fornita.
Rispondi SOLO con un JSON array: [{"idx": 0, "valid": true, "reason": "..."}]
"""

GENERIC_TYPES: frozenset[str] = frozenset({
    "RELAZIONATO_A", "CONNESSO_A", "ASSOCIATO_A", "COLLEGATO_A", "MENZIONA",
    "HA_RELAZIONE", "E_CONNESSO", "APPARTIENE", "RIFERITO_A", "LEGATO_A",
    "RELATED_TO", "CONNECTED_TO", "ASSOCIATED_WITH", "LINKED_TO", "MENTIONS",
})


# ── core LLM call ─────────────────────────────────────────────────────────────

def _call_llm(
    messages: list[dict],
    max_tokens: int,
    temperature: float | None = None,
) -> str:
    cfg = get_config()
    model = resolve_model()
    temp = temperature if temperature is not None else cfg.llm_temperature

    for attempt in range(1, cfg.llm_retry + 1):
        try:
            response = get_client().chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temp,
                timeout=cfg.llm_timeout,
            )
            raw = response.choices[0].message.content or ""
            if not raw.strip():
                reason = response.choices[0].finish_reason or "?"
                print(f"\n  ⚠️  Risposta vuota (tentativo {attempt}/{cfg.llm_retry}) "
                      f"finish_reason={reason}")
                if reason == "length":
                    print(f"     → LLM_MAX_TOKENS ({max_tokens}) troppo basso. "
                          "Aumenta LLM_MAX_TOKENS nel .env")
                if attempt < cfg.llm_retry:
                    _wait(attempt)
                continue
            return raw.strip()

        except RateLimitError:
            wait = min(120, 5 * (2 ** attempt))
            print(f"\n  ⚠️  Rate limit (tentativo {attempt}/{cfg.llm_retry}) "
                  f"— attendo {wait}s…")
            time.sleep(wait)

        except Exception as exc:
            s = str(exc)
            print(f"\n  ❌ Errore LLM (tentativo {attempt}/{cfg.llm_retry}): {s}")
            _diagnose_error(s)
            if attempt < cfg.llm_retry:
                _wait(attempt)

    return ""


def _wait(attempt: int) -> None:
    wait = 2 ** attempt
    print(f"     → Ritento tra {wait}s…", flush=True)
    time.sleep(wait)


def _diagnose_error(err: str) -> None:
    cfg = get_config()
    if "Connection refused" in err or "connect" in err.lower():
        print(f"     → Server non raggiungibile su {cfg.llm_base_url}")
    elif "model" in err.lower() and "not found" in err.lower():
        print(f"     → Modello non trovato. Modelli disponibili:")
        try:
            for m in get_client().models.list().data:
                print(f"       • {m.id}")
        except Exception:
            pass
    elif "context" in err.lower() or "too long" in err.lower():
        print("     → Testo troppo lungo. Riduci CHUNK_SIZE nel .env")


# ── graph extraction ──────────────────────────────────────────────────────────

def llm_extract_graph(
    text_chunk: str,
    chunk_idx: int,
    total: int,
) -> dict:
    print(f"  🤖 Chunk {chunk_idx}/{total} ({len(text_chunk):,} chars)… ",
          end="", flush=True)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Analizza il seguente testo ed estrai il grafo di conoscenza.\n"
                "Includi un edge SOLO se hai una 'evidence' testuale diretta.\n\n"
                f"TESTO:\n{text_chunk}"
            ),
        },
    ]
    raw = _call_llm(messages, get_config().llm_max_tokens)
    if not raw:
        print("❌ Nessuna risposta — chunk saltato")
        return {"nodes": [], "edges": []}

    data = safe_parse_llm_json(raw)
    if data is None:
        print("❌ JSON non parsabile — chunk saltato")
        return {"nodes": [], "edges": []}

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    print(f"✅ {len(nodes)} nodi, {len(edges)} archi")
    return data


# ── enrichment ────────────────────────────────────────────────────────────────

def enrich_relations(graph: dict) -> dict:
    """Sostituisce edge con tipo generico con verbi precisi."""
    cfg = get_config()
    node_map = {n["id"]: n["label"] for n in graph["nodes"]}

    to_enrich = [
        i for i, e in enumerate(graph["edges"])
        if e.get("type", "").upper() in GENERIC_TYPES
        or not e.get("label", "").strip()
    ]

    if not to_enrich:
        print("  ✅ Nessuna relazione generica — arricchimento non necessario")
        return graph

    print(f"  🔧 {len(to_enrich)} relazioni da arricchire…")
    enriched = 0
    batch_size = cfg.enrich_batch_size

    for b_start in range(0, len(to_enrich), batch_size):
        batch_idx = to_enrich[b_start: b_start + batch_size]
        batch_edges = []
        for i in batch_idx:
            e = graph["edges"][i]
            batch_edges.append({
                "_idx": i,
                "source": node_map.get(e["source"], e["source"]),
                "target": node_map.get(e["target"], e["target"]),
                "type":   e.get("type", ""),
                "label":  e.get("label", ""),
                "properties": e.get("properties", {}),
                "evidence": e.get("evidence", ""),
            })

        payload = json.dumps({"edges": batch_edges}, ensure_ascii=False)
        try:
            raw = _call_llm(
                [
                    {"role": "system", "content": ENRICH_PROMPT},
                    {"role": "user", "content": payload},
                ],
                cfg.llm_max_tokens,
            )
            result = safe_parse_llm_json(raw) if raw else None
            if not result:
                continue

            improved: list[dict] = (
                result.get("edges", result)
                if isinstance(result, dict)
                else result
            )
            if not isinstance(improved, list):
                continue

            for pos, item in enumerate(improved):
                orig_idx = item.get("_idx")
                if orig_idx is None:
                    orig_idx = batch_idx[pos] if pos < len(batch_idx) else None
                if orig_idx is None:
                    continue

                e = graph["edges"][orig_idx]
                new_type = (
                    item.get("type", e.get("type", ""))
                    .strip().upper().replace(" ", "_")
                )
                new_label = item.get("label", e.get("label", "")).strip()
                new_props = item.get("properties", {})

                if new_type and new_type not in GENERIC_TYPES:
                    e["type"] = new_type
                    enriched += 1
                if new_label:
                    e["label"] = new_label
                if new_props:
                    e["properties"] = {**e.get("properties", {}), **new_props}

        except Exception as exc:
            print(f"\n  ⚠️  Errore batch arricchimento: {exc}")

    print(f"  ✅ Arricchimento completato: {enriched} relazioni migliorate")
    return graph


# ── verification ──────────────────────────────────────────────────────────────

def llm_verify_relations(graph: dict, batch_size: int = 20) -> dict:
    """
    Verifica la validità di TUTTI gli edge (a batch), non solo i primi N.
    """
    if not graph["edges"]:
        return graph

    node_map = {n["id"]: n["label"] for n in graph["nodes"]}
    all_invalid: set[int] = set()
    total = len(graph["edges"])
    cfg = get_config()

    print(f"  🔍 Verifica {total} relazioni (batch={batch_size})…")

    for b_start in range(0, total, batch_size):
        batch = graph["edges"][b_start: b_start + batch_size]
        edges_text = "\n".join(
            f'{j}. {node_map.get(e["source"], "?")} --[{e["type"]}]--> '
            f'{node_map.get(e["target"], "?")} | evidence: "{e.get("evidence", "")}"'
            for j, e in enumerate(batch)
        )
        prompt = f"Valuta le seguenti relazioni:\n\n{edges_text}"

        try:
            raw = _call_llm(
                [
                    {"role": "system", "content": VERIFY_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                1500,
                temperature=0.0,
            )
            verdicts = safe_parse_llm_json(raw) if raw else None
            if isinstance(verdicts, list):
                for v in verdicts:
                    if not v.get("valid", True):
                        global_idx = b_start + v["idx"]
                        all_invalid.add(global_idx)
        except Exception as exc:
            print(f"\n  ⚠️  Errore verifica batch {b_start}: {exc}")

    before = len(graph["edges"])
    graph["edges"] = [e for i, e in enumerate(graph["edges"]) if i not in all_invalid]
    removed = before - len(graph["edges"])
    if removed:
        print(f"  ✅ Verifica: rimossi {removed} archi non validi su {before}")
    else:
        print(f"  ✅ Verifica: tutti i {before} archi sono validi")
    return graph


# ── JSON parsing ──────────────────────────────────────────────────────────────

def safe_parse_llm_json(raw: str) -> dict | list | None:
    """4 strategie fallback per parsare JSON malformato dal LLM."""

    # Strategia 0: parsing diretto
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Strategia 1: strip markdown fences + cerca il primo {...}
    s1 = re.sub(r"^```[a-zA-Z]*\s*", "", raw.strip())
    s1 = re.sub(r"\s*```\s*$", "", s1).strip()
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", s1)
    if m:
        s1 = m.group(1)
    try:
        return json.loads(s1)
    except json.JSONDecodeError:
        pass

    # Strategia 2: repair_json
    try:
        return json.loads(repair_json(raw))
    except (json.JSONDecodeError, Exception):
        pass

    # Strategia 3: repair + cerca l'oggetto più grande
    try:
        repaired = repair_json(raw)
        m2 = re.search(r"(\{[\s\S]*\})", repaired)
        if m2:
            return json.loads(m2.group(1))
    except (json.JSONDecodeError, Exception):
        pass

    # Strategia 4: estrazione regex
    try:
        result = _extract_partial(raw)
        if result["nodes"] or result["edges"]:
            print(f"\n  [regex fallback] {len(result['nodes'])} nodi, "
                  f"{len(result['edges'])} archi")
            return result
    except Exception:
        pass

    print(f"\n  Raw (primi 400 chars): {repr(raw[:400])}")
    return None


def repair_json(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s).strip()
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", s)
    if m:
        s = m.group(1)
    s = _remove_comments(s)
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    s = re.sub(r"\bNone\b", "null", s)
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    if '"' not in s:
        s = s.replace("'", '"')
    s = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', s)
    s = _close_truncated(s)
    return s


def _remove_comments(s: str) -> str:
    result: list[str] = []
    i = 0
    in_string = False
    while i < len(s):
        c = s[i]
        if c == "\\" and in_string:
            result.append(c)
            result.append(s[i + 1] if i + 1 < len(s) else "")
            i += 2
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            i += 1
            continue
        if not in_string:
            if s[i: i + 2] == "//":
                while i < len(s) and s[i] != "\n":
                    i += 1
                continue
            if s[i: i + 2] == "/*":
                end = s.find("*/", i + 2)
                i = end + 2 if end != -1 else len(s)
                continue
        result.append(c)
        i += 1
    return "".join(result)


def _close_truncated(s: str) -> str:
    stack: list[str] = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}" and stack and stack[-1] == "}":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "]":
            stack.pop()
    if stack:
        s = re.sub(r",\s*$", "", s.rstrip())
        s += "".join(reversed(stack))
    return s


def _extract_partial(raw: str) -> dict:
    """Ultimo fallback: estrae nodi/archi con regex senza parsing JSON."""
    nodes, edges = [], []
    nid = 0
    q = r'["\']'
    label_re  = re.compile(q + r"label"  + q + r"\s*:\s*" + q + r"([^\"']+)" + q)
    type_re   = re.compile(q + r"type"   + q + r"\s*:\s*" + q + r"([^\"']+)" + q)
    source_re = re.compile(q + r"source" + q + r"\s*:\s*" + q + r"([^\"']+)" + q)
    target_re = re.compile(q + r"target" + q + r"\s*:\s*" + q + r"([^\"']+)" + q)

    for block in re.split(r"\},?\s*\{", raw):
        lm  = label_re.search(block)
        tm  = type_re.search(block)
        sm  = source_re.search(block)
        trm = target_re.search(block)
        if sm and trm:
            edges.append({
                "source": sm.group(1),
                "target": trm.group(1),
                "type":   tm.group(1) if tm else "RELAZIONATO_A",
                "properties": {},
                "evidence": "",
            })
        elif lm:
            nid += 1
            nodes.append({
                "id":    f"n{nid}",
                "label": lm.group(1),
                "type":  tm.group(1) if tm else "Nodo",
                "properties": {},
                "description": "",
            })
    return {"nodes": nodes, "edges": edges}
