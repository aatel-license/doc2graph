"""conftest.py — Configurazione globale pytest."""
import sys
from pathlib import Path

# Assicura che il pacchetto sia importabile anche senza installazione
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
