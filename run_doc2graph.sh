#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_doc2graph.sh — processa i PDF uno alla volta, poi mergia in un HTML
# Uso: ./run_doc2graph.sh [output-*.pdf]
#      oppure senza argomenti: prende tutti i PDF nella cartella corrente
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT="doc2graph_multi_files.py"
OUTPUT="brancalonia.html"
CHUNK_SIZE=3000
OPTS="--chunk-size $CHUNK_SIZE --no-enrich"

# ── colori ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── lista file ───────────────────────────────────────────────────────────────
if [ "$#" -gt 0 ]; then
    FILES=("$@")
else
    FILES=(output-*.pdf)
fi

TOTAL=${#FILES[@]}
if [ "$TOTAL" -eq 0 ]; then
    echo -e "${RED}❌  Nessun PDF trovato.${NC}"
    exit 1
fi

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  doc2graph batch runner — $TOTAL file da processare${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

FAILED=()
DONE=0

for i in "${!FILES[@]}"; do
    f="${FILES[$i]}"
    NUM=$((i + 1))

    # Controlla se il JSON finale esiste già (file già completato)
    STEM="${f%.pdf}"
    JSON_OUT="${STEM}_graph.json"
    if [ -f "$JSON_OUT" ]; then
        echo -e "${GREEN}⏭  [$NUM/$TOTAL] $f — già completato (${JSON_OUT} esiste), skip${NC}"
        ((DONE++))
        continue
    fi

    echo -e "${YELLOW}▶  [$NUM/$TOTAL] $f${NC}"
    START_T=$(date +%s)

    python "$SCRIPT" "$f" $OPTS

    EXIT_CODE=$?
    END_T=$(date +%s)
    ELAPSED=$((END_T - START_T))

    if [ $EXIT_CODE -eq 0 ] && [ -f "$JSON_OUT" ]; then
        echo -e "${GREEN}   ✅  Completato in ${ELAPSED}s → ${JSON_OUT}${NC}"
        ((DONE++))
    else
        echo -e "${RED}   ❌  Fallito (exit $EXIT_CODE) dopo ${ELAPSED}s — verrà riprovato dopo${NC}"
        FAILED+=("$f")
    fi
    echo ""
done

# ── Riprova i file falliti una volta ─────────────────────────────────────────
if [ ${#FAILED[@]} -gt 0 ]; then
    echo -e "${YELLOW}════ Riprovo ${#FAILED[@]} file falliti ════${NC}"
    for f in "${FAILED[@]}"; do
        STEM="${f%.pdf}"
        JSON_OUT="${STEM}_graph.json"
        echo -e "${YELLOW}▶  (retry) $f${NC}"
        python "$SCRIPT" "$f" $OPTS
        if [ $? -eq 0 ] && [ -f "$JSON_OUT" ]; then
            echo -e "${GREEN}   ✅  OK al secondo tentativo${NC}"
            ((DONE++))
            FAILED=("${FAILED[@]/$f}")
        else
            echo -e "${RED}   ❌  Ancora fallito — saltato${NC}"
        fi
        echo ""
    done
fi

# ── Merge finale ─────────────────────────────────────────────────────────────
JSONS=(output-*_graph.json)
if [ ${#JSONS[@]} -eq 0 ]; then
    echo -e "${RED}❌  Nessun JSON trovato per il merge.${NC}"
    exit 1
fi

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Merge di ${#JSONS[@]} JSON → $OUTPUT${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"

python "$SCRIPT" --merge-jsons "${JSONS[@]}" -o "$OUTPUT"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}🎉  Fatto! $DONE/$TOTAL file processati.${NC}"
    if [ ${#FAILED[@]} -gt 0 ]; then
        echo -e "${RED}   File non processati: ${FAILED[*]}${NC}"
    fi
    echo -e "${GREEN}   Apri: $OUTPUT${NC}"
else
    echo -e "${RED}❌  Merge fallito.${NC}"
    exit 1
fi
