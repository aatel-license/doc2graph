# doc2graph v2.0

> Estrae knowledge graph da qualsiasi documento via LLM e genera un visualizzatore HTML interattivo stile Neo4j.

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

---

## Caratteristiche v2.0

| Feature | v1 | v2 |
|---|---|---|
| Architettura | Monolitico (2000 righe) | Modulare (8 moduli) |
| Configurazione | Variabili globali | Pydantic Settings |
| Chunking | Solo caratteri | Caratteri + Token (tiktoken) |
| Deduplicazione nodi | Exact match | Fuzzy match (rapidfuzz) |
| Checkpoint | Per file | **Per chunk** (atomico) |
| Verifica archi | Solo primi 20 | **Tutti**, a batch |
| Processing | Sequenziale | Sequenziale + **Parallelo** |
| Progress bar | Print manual | **Rich** (opzionale) |
| Export | Solo HTML | HTML + JSON + GraphML + Neo4j CSV + RDF + Cypher |
| Template HTML | Inline hardcoded | Inline + **Jinja2** esterno |
| Dry-run | ❌ | ✅ |
| Installabile | ❌ | ✅ (`pip install .`) |

---

## Installazione

```bash
# Clone / copia la cartella
cd doc2graph

# Installa dipendenze base
pip install -r requirements.txt

# Oppure installa come pacchetto (consigliato)
pip install .

# Installazione completa (tutte le feature opzionali)
pip install ".[full]"
```

---

## Configurazione

```bash
cp .env.example .env
# Modifica .env con il tuo server LLM e modello
```

Variabili principali in `.env`:

| Variabile | Default | Descrizione |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | URL server LLM (LM-Studio, Ollama, OpenAI…) |
| `LLM_MODEL` | *(auto)* | Modello da usare |
| `LLM_MAX_TOKENS` | `4096` | Max token risposta |
| `CHUNK_SIZE` | `6000` | Dimensione chunk in caratteri |
| `CHUNK_OVERLAP` | `500` | Overlap tra chunk |
| `PARALLEL_WORKERS` | `1` | Worker paralleli |
| `FUZZY_MERGE_THRESHOLD` | `90` | Soglia fuzzy dedup nodi (0-100) |

---

## Utilizzo

### Base

```bash
# Singolo file
python -m doc2graph report.pdf

# Più file → grafo unificato
python -m doc2graph *.pdf *.docx -o output.html

# Con output personalizzato
python -m doc2graph documento.pdf -o grafo.html
```

### Opzioni avanzate

```bash
# Dry-run: stima chunk e token senza chiamare il LLM
python -m doc2graph --dry-run *.pdf

# Export aggiuntivi
python -m doc2graph file.pdf --export json graphml cypher neo4j rdf

# Processing parallelo (attenzione ai rate limit)
python -m doc2graph *.pdf --workers 3

# Salta arricchimento relazioni (più veloce)
python -m doc2graph file.pdf --no-enrich

# Abilita verifica LLM degli archi (più preciso, più lento)
python -m doc2graph file.pdf --verify

# Riprendi da checkpoint esistente
python -m doc2graph file.pdf  # riprende automaticamente

# Forza restart (ignora checkpoint)
python -m doc2graph file.pdf --no-resume

# Statistiche grafo
python -m doc2graph file.pdf --stats
```

### Merge JSON (zero LLM)

```bash
# Unisce grafi già estratti senza chiamare il LLM
python -m doc2graph --merge-jsons graph1.json graph2.json -o merged.html
```

### Override LLM da CLI

```bash
python -m doc2graph file.pdf \
  --model gpt-4o-mini \
  --url https://api.openai.com/v1 \
  --tokens 8192 \
  --chunk-size 8000
```

---

## Formati supportati

| Formato | Metodo |
|---|---|
| `.txt` `.md` `.py` `.js` `.ts` `.java` `.go` … | Nativo |
| `.pdf` | pypdf + pdftotext (fallback) |
| `.docx` | python-docx + pandoc (fallback) |
| `.csv` `.tsv` | csv stdlib |
| `.json` `.jsonl` | json stdlib |
| `.epub` `.odt` `.rtf` `.doc` `.pptx` | pandoc |

---

## Struttura progetto

```
doc2graph/
├── doc2graph/
│   ├── __init__.py       # API pubblica
│   ├── __main__.py       # python -m doc2graph
│   ├── cli.py            # Argparse + entry point
│   ├── config.py         # Pydantic Settings
│   ├── extractors.py     # Estrazione testo multi-formato
│   ├── chunker.py        # Chunking char + token
│   ├── llm.py            # Chiamate LLM, prompts, parsing JSON
│   ├── graph.py          # Merge, prune, fuzzy dedup
│   ├── checkpoint.py     # Checkpoint per-chunk
│   ├── pipeline.py       # Orchestrazione
│   ├── renderer.py       # Generazione HTML
│   └── exporter.py       # Export GraphML/CSV/RDF/Cypher
├── templates/
│   └── graph.html.jinja2 # Template HTML (Jinja2)
├── .env.example
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Uso come libreria Python

```python
from doc2graph import process_file, process_files, build_html, export_all
from doc2graph.config import Config, set_config
from pathlib import Path

# Configura
cfg = Config(llm_model="gpt-4o-mini", chunk_size=8000)
set_config(cfg)

# Processa un file
graph = process_file(Path("documento.pdf"))

# Genera HTML
build_html(graph, "documento", Path("output.html"))

# Export aggiuntivi
export_all(graph, Path("output"), ["json", "graphml", "cypher"])

# Accedi al grafo
for node in graph["nodes"]:
    print(node["label"], node["type"])

for edge in graph["edges"]:
    print(edge["source"], "→", edge["type"], "→", edge["target"])
```

---

## Dipendenze opzionali

```bash
# Fuzzy dedup nodi (consigliato)
pip install rapidfuzz

# Chunking preciso in token
pip install tiktoken

# Progress bar colorata
pip install rich

# Template HTML esterno
pip install jinja2
```

---

## Note tecniche

- **Checkpoint atomici**: usa `tempfile + os.replace` per evitare corruzione
- **Retry con backoff esponenziale**: gestisce `RateLimitError` separatamente
- **Fuzzy merge**: `rapidfuzz.fuzz.ratio ≥ 90` (configurabile)
- **Verifica archi**: processa tutti gli archi a batch, non solo i primi N
- **Parallel workers**: usa `ThreadPoolExecutor` (I/O-bound per le chiamate LLM)
