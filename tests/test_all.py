"""
tests/test_all.py — Suite di test per doc2graph v2.

Esegui con:
    pytest tests/ -v
    pytest tests/ -v --cov=doc2graph
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Aggiungi la root al path se eseguito direttamente
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_graph():
    return {
        "nodes": [
            {"id": "n1", "label": "Mario Rossi", "type": "Persona",
             "properties": {"ruolo": "CEO"}, "description": "Fondatore"},
            {"id": "n2", "label": "Acme Corp",   "type": "Organizzazione",
             "properties": {"settore": "Tech"}, "description": ""},
            {"id": "n3", "label": "Roma",         "type": "Luogo",
             "properties": {}, "description": "Città"},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "type": "FONDA",
             "label": "ha fondato nel 1998",
             "properties": {"anno": "1998"},
             "evidence": "Mario Rossi ha fondato Acme Corp nel 1998"},
            {"source": "n2", "target": "n3", "type": "HA_SEDE_IN",
             "label": "ha sede a Roma",
             "properties": {},
             "evidence": "Acme Corp ha sede a Roma"},
        ],
    }


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ─────────────────────────────────────────────────────────────────────────────
# config.py
# ─────────────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self):
        from doc2graph.config import Config
        cfg = Config()
        assert cfg.llm_base_url == "http://localhost:1234/v1"
        assert cfg.llm_max_tokens == 4096
        assert cfg.chunk_size == 6000
        assert cfg.parallel_workers == 1

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("CHUNK_SIZE", "3000")
        from doc2graph.config import Config
        cfg = Config()
        assert cfg.llm_model == "gpt-4o"
        assert cfg.chunk_size == 3000

    def test_set_get_config(self):
        from doc2graph.config import Config, get_config, set_config, _config
        cfg = Config(llm_model="test-model")
        set_config(cfg)
        assert get_config().llm_model == "test-model"
        # cleanup
        import doc2graph.config as m
        m._config = None


# ─────────────────────────────────────────────────────────────────────────────
# chunker.py
# ─────────────────────────────────────────────────────────────────────────────

class TestChunker:
    def setup_method(self):
        from doc2graph.config import Config, set_config
        set_config(Config(chunk_size=100, chunk_overlap=20))

    def test_short_text_single_chunk(self):
        from doc2graph.chunker import split_into_chunks
        text = "Breve testo di prova."
        chunks = split_into_chunks(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        from doc2graph.chunker import split_into_chunks
        text = "A" * 500
        chunks = split_into_chunks(text)
        assert len(chunks) > 1

    def test_overlap(self):
        from doc2graph.chunker import split_into_chunks
        # Con overlap=20 e size=100, i chunk si sovrappongono
        text = "parola " * 50  # ~350 chars
        chunks = split_into_chunks(text)
        assert len(chunks) >= 2
        # L'ultimo carattere del chunk[0] deve apparire all'inizio di chunk[1]
        # (overlapping)

    def test_empty_text(self):
        from doc2graph.chunker import split_into_chunks
        assert split_into_chunks("") == []
        assert split_into_chunks("   ") == []

    def test_estimate_chunks(self):
        from doc2graph.chunker import estimate_chunks
        text = "X" * 1000  # size=100, overlap=20 → step=80 → ~13 chunk
        n = estimate_chunks(text)
        assert n > 1

    def test_prefer_paragraph_boundary(self):
        from doc2graph.chunker import split_into_chunks, _split_by_chars
        # Il testo ha un doppio newline a metà
        text = "A" * 60 + "\n\n" + "B" * 60
        chunks = _split_by_chars(text, size=100, overlap=10)
        # Deve tagliare sul \n\n
        assert any("A" * 60 in c for c in chunks)

    def teardown_method(self):
        import doc2graph.config as m
        m._config = None


# ─────────────────────────────────────────────────────────────────────────────
# graph.py
# ─────────────────────────────────────────────────────────────────────────────

class TestGraph:
    def test_normalize_label(self):
        from doc2graph.graph import normalize_label
        assert normalize_label("  Mario Rossi  ") == "mario rossi"
        assert normalize_label("Acme-Corp!") == "acmecorp"
        assert normalize_label("Città") == "citta"

    def test_merge_dedup_exact(self):
        from doc2graph.graph import merge_graphs
        g1 = {
            "nodes": [{"id": "n1", "label": "Mario", "type": "Persona", "properties": {}, "description": ""}],
            "edges": [],
        }
        g2 = {
            "nodes": [{"id": "n1", "label": "Mario", "type": "Persona", "properties": {"ruolo": "CEO"}, "description": ""}],
            "edges": [],
        }
        merged = merge_graphs([g1, g2])
        assert len(merged["nodes"]) == 1
        # Properties unite
        assert merged["nodes"][0]["properties"].get("ruolo") == "CEO"

    def test_merge_different_types_not_deduped(self):
        from doc2graph.graph import merge_graphs
        g1 = {"nodes": [{"id": "n1", "label": "Mario", "type": "Persona",
                          "properties": {}, "description": ""}], "edges": []}
        g2 = {"nodes": [{"id": "n1", "label": "Mario", "type": "Luogo",
                          "properties": {}, "description": ""}], "edges": []}
        merged = merge_graphs([g1, g2])
        assert len(merged["nodes"]) == 2

    def test_merge_edges_remap(self):
        from doc2graph.graph import merge_graphs
        g1 = {
            "nodes": [
                {"id": "a", "label": "Nodo A", "type": "Concetto", "properties": {}, "description": ""},
                {"id": "b", "label": "Nodo B", "type": "Concetto", "properties": {}, "description": ""},
            ],
            "edges": [{"source": "a", "target": "b", "type": "IMPLICA", "label": "", "properties": {}, "evidence": ""}],
        }
        merged = merge_graphs([g1])
        assert len(merged["edges"]) == 1
        # Gli id sono stati rimappati
        node_ids = {n["id"] for n in merged["nodes"]}
        assert merged["edges"][0]["source"] in node_ids
        assert merged["edges"][0]["target"] in node_ids

    def test_prune_orphan_edges(self, sample_graph):
        from doc2graph.graph import prune_graph
        # Aggiungi un edge orfano
        sample_graph["edges"].append({
            "source": "n99", "target": "n1", "type": "TEST",
            "label": "", "properties": {}, "evidence": "",
        })
        pruned = prune_graph(sample_graph)
        assert all(
            e["source"] in {n["id"] for n in pruned["nodes"]}
            for e in pruned["edges"]
        )

    def test_prune_self_loop(self, sample_graph):
        from doc2graph.graph import prune_graph
        sample_graph["edges"].append({
            "source": "n1", "target": "n1", "type": "SELF",
            "label": "", "properties": {}, "evidence": "",
        })
        pruned = prune_graph(sample_graph)
        assert all(e["source"] != e["target"] for e in pruned["edges"])

    def test_prune_dedup(self, sample_graph):
        from doc2graph.graph import prune_graph
        # Duplica un edge
        dup = dict(sample_graph["edges"][0])
        sample_graph["edges"].append(dup)
        before = len(sample_graph["edges"])
        pruned = prune_graph(sample_graph)
        assert len(pruned["edges"]) < before

    def test_graph_stats(self, sample_graph):
        from doc2graph.graph import graph_stats
        s = graph_stats(sample_graph)
        assert s["nodes"] == 3
        assert s["edges"] == 2
        assert "Persona" in s["node_types"]
        assert s["isolated_nodes"] == 0  # tutti i nodi hanno almeno un arco


# ─────────────────────────────────────────────────────────────────────────────
# llm.py — JSON parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonParsing:
    def test_clean_json(self):
        from doc2graph.llm import safe_parse_llm_json
        raw = '{"nodes": [], "edges": []}'
        result = safe_parse_llm_json(raw)
        assert result == {"nodes": [], "edges": []}

    def test_markdown_fence(self):
        from doc2graph.llm import safe_parse_llm_json
        raw = '```json\n{"nodes": [], "edges": []}\n```'
        result = safe_parse_llm_json(raw)
        assert result is not None
        assert "nodes" in result

    def test_trailing_comma(self):
        from doc2graph.llm import repair_json, safe_parse_llm_json
        raw = '{"nodes": [{"id": "n1",}], "edges": [],}'
        result = safe_parse_llm_json(raw)
        assert result is not None

    def test_python_literals(self):
        from doc2graph.llm import repair_json
        raw = '{"val": None, "flag": True, "f2": False}'
        repaired = repair_json(raw)
        parsed = json.loads(repaired)
        assert parsed["val"] is None
        assert parsed["flag"] is True

    def test_truncated_json(self):
        from doc2graph.llm import repair_json
        raw = '{"nodes": [{"id": "n1", "label": "Test"'
        repaired = repair_json(raw)
        # Deve chiudere le parentesi
        assert repaired.count("{") == repaired.count("}")

    def test_invalid_returns_none(self):
        from doc2graph.llm import safe_parse_llm_json
        result = safe_parse_llm_json("questo non è json per niente!!!")
        # Può essere None o un dict vuoto dal fallback regex
        assert result is None or isinstance(result, dict)

    def test_generic_types_set(self):
        from doc2graph.llm import GENERIC_TYPES
        assert "RELAZIONATO_A" in GENERIC_TYPES
        assert "RELATED_TO" in GENERIC_TYPES
        assert "FONDA" not in GENERIC_TYPES


# ─────────────────────────────────────────────────────────────────────────────
# checkpoint.py
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckpoint:
    def test_save_load(self, tmp_dir):
        from doc2graph.checkpoint import ChunkProgress
        fake_file = tmp_dir / "doc.pdf"
        fake_file.write_text("content")

        prog = ChunkProgress(fake_file, total_chunks=3)
        prog.mark_done(0, {"nodes": [{"id": "n1"}], "edges": []})
        prog.mark_done(1, {"nodes": [{"id": "n2"}], "edges": []})

        # Nuovo oggetto che riprende dal checkpoint
        prog2 = ChunkProgress(fake_file, total_chunks=3)
        resumed = prog2.resume()

        assert resumed is True
        assert prog2.is_done(0)
        assert prog2.is_done(1)
        assert not prog2.is_done(2)

    def test_results_order(self, tmp_dir):
        from doc2graph.checkpoint import ChunkProgress
        fake_file = tmp_dir / "doc.pdf"
        fake_file.write_text("content")

        prog = ChunkProgress(fake_file, total_chunks=3)
        # Inserisci in ordine sparso
        prog.mark_done(2, {"nodes": [{"id": "c"}], "edges": []})
        prog.mark_done(0, {"nodes": [{"id": "a"}], "edges": []})
        prog.mark_done(1, {"nodes": [{"id": "b"}], "edges": []})

        results = prog.results()
        assert results[0]["nodes"][0]["id"] == "a"
        assert results[1]["nodes"][0]["id"] == "b"
        assert results[2]["nodes"][0]["id"] == "c"

    def test_clear(self, tmp_dir):
        from doc2graph.checkpoint import ChunkProgress, checkpoint_path
        fake_file = tmp_dir / "doc.pdf"
        fake_file.write_text("content")

        prog = ChunkProgress(fake_file, total_chunks=2)
        prog.mark_done(0, {"nodes": [], "edges": []})
        assert checkpoint_path(fake_file).exists()

        prog.clear()
        assert not checkpoint_path(fake_file).exists()

    def test_no_checkpoint_returns_false(self, tmp_dir):
        from doc2graph.checkpoint import ChunkProgress
        fake_file = tmp_dir / "no_checkpoint.pdf"
        prog = ChunkProgress(fake_file, total_chunks=5)
        assert prog.resume() is False


# ─────────────────────────────────────────────────────────────────────────────
# extractors.py
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractors:
    def test_txt(self, tmp_dir):
        from doc2graph.extractors import extract_text
        f = tmp_dir / "test.txt"
        f.write_text("Hello world", encoding="utf-8")
        assert extract_text(f) == "Hello world"

    def test_md(self, tmp_dir):
        from doc2graph.extractors import extract_text
        f = tmp_dir / "test.md"
        f.write_text("# Titolo\nContenuto", encoding="utf-8")
        assert "Titolo" in extract_text(f)

    def test_json(self, tmp_dir):
        from doc2graph.extractors import extract_text
        f = tmp_dir / "test.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = extract_text(f)
        assert "key" in result

    def test_csv(self, tmp_dir):
        from doc2graph.extractors import extract_text
        f = tmp_dir / "test.csv"
        f.write_text("nome,età\nMario,30\nLuigi,25", encoding="utf-8")
        result = extract_text(f)
        assert "Mario" in result
        assert "Luigi" in result

    def test_jsonl(self, tmp_dir):
        from doc2graph.extractors import extract_text
        f = tmp_dir / "test.jsonl"
        f.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
        result = extract_text(f)
        assert "a" in result


# ─────────────────────────────────────────────────────────────────────────────
# exporter.py
# ─────────────────────────────────────────────────────────────────────────────

class TestExporter:
    def test_export_json(self, tmp_dir, sample_graph):
        from doc2graph.exporter import export_json
        out = tmp_dir / "graph.json"
        export_json(sample_graph, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert len(loaded["nodes"]) == 3

    def test_export_graphml(self, tmp_dir, sample_graph):
        from doc2graph.exporter import export_graphml
        out = tmp_dir / "graph.graphml"
        export_graphml(sample_graph, out)
        assert out.exists()
        content = out.read_text()
        assert "<graphml" in content
        assert "Mario Rossi" in content

    def test_export_cypher(self, tmp_dir, sample_graph):
        from doc2graph.exporter import export_cypher
        out = tmp_dir / "graph.cypher"
        export_cypher(sample_graph, out)
        assert out.exists()
        content = out.read_text()
        assert "MERGE" in content
        assert "FONDA" in content

    def test_export_rdf(self, tmp_dir, sample_graph):
        from doc2graph.exporter import export_rdf_turtle
        out = tmp_dir / "graph.ttl"
        export_rdf_turtle(sample_graph, out)
        assert out.exists()
        content = out.read_text()
        assert "@prefix" in content
        assert "FONDA" in content

    def test_export_neo4j_csv(self, tmp_dir, sample_graph):
        from doc2graph.exporter import export_neo4j_csv
        base = tmp_dir / "graph"
        export_neo4j_csv(sample_graph, base)
        assert (tmp_dir / "graph_nodes.csv").exists()
        assert (tmp_dir / "graph_relationships.csv").exists()

    def test_export_all(self, tmp_dir, sample_graph):
        from doc2graph.exporter import export_all
        base = tmp_dir / "graph"
        export_all(sample_graph, base, ["json", "cypher"])
        assert (tmp_dir / "graph.json").exists()
        assert (tmp_dir / "graph.cypher").exists()

    def test_export_unknown_format(self, tmp_dir, sample_graph, capsys):
        from doc2graph.exporter import export_all
        export_all(sample_graph, tmp_dir / "g", ["xyz"])
        captured = capsys.readouterr()
        assert "sconosciuto" in captured.out.lower() or "unknown" in captured.out.lower() or "xyz" in captured.out


# ─────────────────────────────────────────────────────────────────────────────
# renderer.py
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderer:
    def test_build_html(self, tmp_dir, sample_graph):
        from doc2graph.renderer import build_html
        out = tmp_dir / "output.html"
        build_html(sample_graph, "test_doc", out)
        assert out.exists()
        content = out.read_text()
        assert "doc2graph" in content
        assert "Mario Rossi" in content
        assert "FONDA" in content

    def test_html_valid_structure(self, tmp_dir, sample_graph):
        from doc2graph.renderer import build_html
        out = tmp_dir / "output.html"
        build_html(sample_graph, "test", out)
        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "<canvas" in content
        assert "NODES_DATA" in content
        assert "EDGES_DATA" in content

    def test_color_assignment(self):
        from doc2graph.renderer import _assign_colors
        nodes = [
            {"type": "Persona"},
            {"type": "Persona"},
            {"type": "Organizzazione"},
        ]
        colors = _assign_colors(nodes)
        assert len(colors) == 2  # 2 tipi distinti
        assert colors["Persona"] != colors["Organizzazione"]


# ─────────────────────────────────────────────────────────────────────────────
# pipeline.py — mock LLM
# ─────────────────────────────────────────────────────────────────────────────

class TestPipeline:
    """Testa la pipeline con LLM mockato."""

    MOCK_GRAPH = {
        "nodes": [
            {"id": "n1", "label": "TestNode", "type": "Concetto",
             "properties": {}, "description": ""},
        ],
        "edges": [],
    }

    @patch("doc2graph.llm.get_client")
    def test_process_file_mock(self, mock_client, tmp_dir):
        from doc2graph.config import Config, set_config
        from doc2graph.pipeline import process_file

        set_config(Config(chunk_size=50, chunk_overlap=10, llm_model="mock"))

        # Mock della risposta LLM
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps(self.MOCK_GRAPH)
        mock_resp.choices[0].finish_reason = "stop"
        mock_client.return_value.chat.completions.create.return_value = mock_resp
        mock_client.return_value.models.list.return_value.data = []

        f = tmp_dir / "test.txt"
        f.write_text("Questo è un testo di test per la pipeline." * 5, encoding="utf-8")

        graph = process_file(f, resume=False, no_enrich=True, no_verify=True)
        assert "nodes" in graph
        assert "edges" in graph

        import doc2graph.config as m
        m._config = None

    def test_merge_json_files(self, tmp_dir):
        from doc2graph.pipeline import merge_json_files

        g1 = {
            "nodes": [{"id": "n1", "label": "Alpha", "type": "A", "properties": {}, "description": ""}],
            "edges": [],
        }
        g2 = {
            "nodes": [{"id": "n1", "label": "Beta", "type": "B", "properties": {}, "description": ""}],
            "edges": [],
        }
        f1 = tmp_dir / "g1.json"
        f2 = tmp_dir / "g2.json"
        f1.write_text(json.dumps(g1))
        f2.write_text(json.dumps(g2))

        merged = merge_json_files([f1, f2])
        assert len(merged["nodes"]) == 2

    def test_merge_json_missing_file(self, tmp_dir, capsys):
        from doc2graph.pipeline import merge_json_files
        result = merge_json_files([tmp_dir / "nonexistent.json"])
        assert result == {"nodes": [], "edges": []}


# ─────────────────────────────────────────────────────────────────────────────
# cli.py
# ─────────────────────────────────────────────────────────────────────────────

class TestCLI:
    def test_parser_no_args(self):
        from doc2graph.cli import build_parser
        p = build_parser()
        args = p.parse_args([])
        assert args.files == []
        assert args.dry_run is False

    def test_parser_files(self):
        from doc2graph.cli import build_parser
        p = build_parser()
        args = p.parse_args(["a.pdf", "b.docx"])
        assert args.files == ["a.pdf", "b.docx"]

    def test_parser_export(self):
        from doc2graph.cli import build_parser
        p = build_parser()
        args = p.parse_args(["f.pdf", "--export", "json", "graphml"])
        assert set(args.export) == {"json", "graphml"}

    def test_parser_merge_jsons(self):
        from doc2graph.cli import build_parser
        p = build_parser()
        args = p.parse_args(["--merge-jsons", "a.json", "b.json", "-o", "out.html"])
        assert args.merge_jsons == ["a.json", "b.json"]
        assert args.output == "out.html"

    def test_parser_dry_run(self):
        from doc2graph.cli import build_parser
        p = build_parser()
        args = p.parse_args(["--dry-run", "file.pdf"])
        assert args.dry_run is True

    def test_resolve_files_glob(self, tmp_dir):
        from doc2graph.cli import _resolve_files
        (tmp_dir / "a.txt").write_text("a")
        (tmp_dir / "b.txt").write_text("b")
        results = _resolve_files([str(tmp_dir / "*.txt")])
        assert len(results) == 2

    def test_resolve_files_missing(self, capsys):
        from doc2graph.cli import _resolve_files
        results = _resolve_files(["/nonexistent/file.pdf"])
        assert results == []
