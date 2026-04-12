"""
doc2graph — Estrazione di knowledge graph da documenti via LLM.

Versione 2.0.0 — architettura modulare.
"""

__version__ = "2.0.0"
__author__  = "doc2graph contributors"

from .config   import get_config, set_config, Config
from .pipeline import process_file, process_files, merge_json_files
from .renderer import build_html
from .exporter import export_all

__all__ = [
    "get_config", "set_config", "Config",
    "process_file", "process_files", "merge_json_files",
    "build_html", "export_all",
]
