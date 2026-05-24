#!/usr/bin/env bash
# Inizializza una vault llm-wiki: installa dipendenze, crea l'indice QMD,
# genera config locale a partire dal template.
#
# Idempotente: rilanciabile senza danni.

set -euo pipefail

VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$VAULT_ROOT"

echo "→ Vault root: $VAULT_ROOT"

# ── Check prerequisiti ────────────────────────────────────────────────────────
require() {
  command -v "$1" >/dev/null 2>&1 || { echo "✗ Manca: $1 — $2"; exit 1; }
}
require python3 "installa Python 3.10+"
require node    "installa Node.js 18+ (https://nodejs.org)"
require npm     "installa npm (incluso in Node.js)"

# ── Python: markitdown ────────────────────────────────────────────────────────
if ! python3 -c "import markitdown" 2>/dev/null; then
  echo "→ Installazione markitdown[all]..."
  python3 -m pip install --user "markitdown[all]"
else
  echo "✓ markitdown già presente"
fi

# ── Python: duckduckgo-search (fallback deep-research) ────────────────────────
if ! python3 -c "import duckduckgo_search" 2>/dev/null && ! python3 -c "import ddgs" 2>/dev/null; then
  echo "→ Installazione duckduckgo-search (fallback web-search)..."
  python3 -m pip install --user duckduckgo-search
else
  echo "✓ duckduckgo-search già presente"
fi

# ── Node: qmd ─────────────────────────────────────────────────────────────────
if ! command -v qmd >/dev/null 2>&1; then
  echo "→ Installazione @tobilu/qmd (global)..."
  npm install -g @tobilu/qmd
else
  echo "✓ qmd già presente ($(qmd --version 2>/dev/null || echo 'unknown'))"
fi

# ── Config locale ─────────────────────────────────────────────────────────────
if [ ! -f .llm-wiki/config.json ]; then
  cp .llm-wiki/config.example.json .llm-wiki/config.json
  echo "✓ Creato .llm-wiki/config.json (modifica se necessario)"
fi

# ── Collection QMD ────────────────────────────────────────────────────────────
# QMD usa un suo store; lo configuriamo per puntare a wiki/ con DB locale.
mkdir -p .llm-wiki
QMD_DB=".llm-wiki/qmd-index.sqlite"

if [ ! -f "$QMD_DB" ]; then
  echo "→ Configurazione collection QMD su wiki/..."
  qmd collection add "$VAULT_ROOT/wiki" --name wiki --db "$QMD_DB" || true
  qmd context add qmd://wiki "Wiki pages — entities, concepts, sources, queries, synthesis" --db "$QMD_DB" || true
fi

# ── Primo embed ───────────────────────────────────────────────────────────────
echo "→ Generazione embeddings iniziali..."
echo "  (Il primo run scarica il modello GGUF ~400 MB — richiede connessione, può"
echo "   impiegare qualche minuto. Se va in timeout, rilancia: qmd embed --db $QMD_DB)"
echo ""

EMBED_OK=0
for attempt in 1 2; do
  if qmd embed --db "$QMD_DB"; then
    EMBED_OK=1
    break
  fi
  if [ $attempt -lt 2 ]; then
    echo "⚠ embed fallito (tentativo $attempt) — attendo 5s e riprovo..."
    sleep 5
  fi
done

if [ $EMBED_OK -eq 0 ]; then
  echo ""
  echo "⚠ qmd embed non completato. Il modello potrebbe non essere stato scaricato."
  echo "  Riprova manualmente quando hai connessione stabile:"
  echo "    qmd embed --db $QMD_DB"
  echo "  Finché l'embed non completa, wiki-query usa solo ricerca BM25 (--no-rerank)."
fi

# ── Secrets template ──────────────────────────────────────────────────────────
if [ ! -f .llm-wiki/secrets.json ]; then
  cat > .llm-wiki/secrets.json <<'EOF'
{
  "TAVILY_API_KEY": ""
}
EOF
  echo "✓ Creato .llm-wiki/secrets.json"
fi

echo ""
echo "✓ Vault inizializzata."
echo ""
echo "Prossimi passi:"
echo "  1. Modifica purpose.md con lo scope della tua wiki"
echo "  2. Personalizza schema.md se necessario"
echo "  3. Aggiungi documenti in raw/sources/"
echo "  4. [Opzionale] Configura Tavily per deep-research con qualità migliore:"
echo "       Apri .llm-wiki/secrets.json e inserisci la tua chiave:"
echo "         { \"TAVILY_API_KEY\": \"tvly-xxxxxxxxxxxxxxxx\" }"
echo "       Oppure: export TAVILY_API_KEY=\"tvly-...\" nel tuo shell profile."
echo "       Senza Tavily il fallback DuckDuckGo è attivo automaticamente."
echo "  5. Apri la cartella in Obsidian (opzionale) o usa direttamente le skill"
echo ""
