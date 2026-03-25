# 📊 doc2graph

**doc2graph** automatically extracts a structured **knowledge graph** from any document and generates an interactive **HTML/CSS/JS visualizer inspired by Neo4j**.

It supports multiple formats and works with any **OpenAI-compatible LLM** (LM Studio, Ollama, OpenAI, etc.) via `.env`.

---

## ✨ Features

- 📄 Multi-format document ingestion  
- 🧠 Knowledge graph extraction via LLM  
- 🔗 Evidence-based relationships (with source text)  
- 🧩 Chunking with overlap for large documents  
- 🧹 Automatic graph merging & deduplication  

### 🔧 Post-processing
- Relation enrichment (removes generic edges)  
- Optional LLM-based validation  

### 🌐 Interactive HTML graph explorer
- Zoom / pan / drag  
- Node search  
- Filter by type  
- Tooltips with evidence  
- Export to PNG  

- 🟦 Cypher export for Neo4j  

---

## 📦 Supported Formats

- `.txt`, `.md`, `.log`  
- `.pdf`  
- `.docx`, `.doc`  
- `.csv`, `.tsv`  
- `.json`, `.jsonl`  
- `.epub`, `.odt`, `.rtf`, `.pptx`  
- Source code (`.py`, `.js`, `.ts`, etc.)

👉 Automatic fallback using **pandoc** for unsupported formats.

---

## ⚙️ Installation

```bash
git clone https://github.com/your-username/doc2graph.git
cd doc2graph
pip install -r requirements.txt
Main dependencies
openai
python-dotenv
pypdf
python-docx
🔐 Configuration

Create a .env file:

LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=lm-studio
LLM_MODEL=your_model_name

LLM_MAX_TOKENS=4096
CHUNK_SIZE=6000
CHUNK_OVERLAP=500
LLM_RETRY=3
Compatible with:
LM Studio
Ollama
OpenAI API
Any OpenAI-compatible endpoint

👉 If LLM_MODEL is empty → automatic model discovery.
```
## 🚀 Usage
```python doc2graph.py document.pdf
CLI Options
python doc2graph.py input.pdf \
  -o output.html \
  --chunk-size 6000 \
  --overlap 500 \
  --verify \
  --no-enrich
Flags
Flag	Description
-o, --output	Output HTML file
--chunk-size	Chunk size
--overlap	Chunk overlap
--verify	Validate relations via LLM
--no-enrich	Disable relation enrichment
```
## 📊 Output
```
After execution:
 
*_graph.html → interactive visualizer
*.json → structured graph
Cypher export (inside viewer)
🌐 Visualizer

Open:

output_graph.html
Features
Drag & drop nodes
Physics engine (toggle on/off)
Type-based filtering
Full-text search
Tooltips with:
properties
evidence
PNG export
Cypher export
🧠 How It Works
Extract text from document
Split into chunks with overlap
Process each chunk with LLM
Extract:
entities (nodes)
relationships with evidence
Merge & deduplicate graphs
Post-process:
pruning
enrichment
(optional) LLM validation
Generate interactive HTML```

## 🔗 Graph Structure
```Node
{
  "id": "n1",
  "label": "John Doe",
  "type": "Person",
  "properties": {
    "role": "CEO"
  }
}
Edge
{
  "source": "n1",
  "target": "n2",
  "type": "FOUNDED",
  "label": "founded in 2020",
  "evidence": "John Doe founded Acme in 2020"
}
```

## 🧹 Post-Processing
✔ Pruning
Removes self-loops
Removes orphan edges
Deduplicates edges
🔧 Enrichment (LLM)
Replaces generic relations with precise verbs
Adds human-readable labels
Extracts properties from evidence
🔍 Validation (optional)
LLM verifies relation correctness
## 🟦 Neo4j Export

In the viewer:

## 👉 Click Cypher → Copy / Download

Or import manually:

:source graph.cypher
## ⚠️ Optional System Dependencies
```
For full format support:

pandoc → document conversion
pdftotext → PDF fallback
🛠️ Troubleshooting
❌ No LLM output
Ensure LM Studio is running
Check LLM_BASE_URL
Verify LLM_MODEL
❌ Invalid JSON
Built-in robust parsing + auto-repair handles most cases
❌ Context too long
Reduce CHUNK_SIZE
```

## 🧩 Roadmap
 Real-time graph streaming
 Graph editing UI
 API server mode
 Plugin system
 Embeddings + clustering
## 🤝 Contributing

Pull requests are welcome!

For major changes:

Open an issue
Discuss your proposal
Then implement

## 📄 License AATEL

## ⭐ Support

If you like this project:

## 👉 consider giving it a star ⭐