---
name: transcript
description: Transcribe audio/video files (mp4/mov/mp3/m4a/wav/…) using local mlx_whisper. Output is a _TRANSCRIPTS.txt file next to each source. Optional structured summary generation via LLM after transcription. Use when the user asks to transcribe a recording, meeting, or audio/video file.
---

# transcript

Trascrizione locale di file audio/video via [mlx_whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper). Output: `<source-stem>_TRANSCRIPTS.txt` accanto al file originale. Opzionalmente, summary strutturato generato dall'agente (LLM) dopo la trascrizione.

## Quando usarla

- L'utente chiede di trascrivere file in `_inbox/transcription/`
- Generico: "trascrivi <file>" o "trascrivi questa cartella"

## Prerequisiti

- macOS Apple Silicon (mlx_whisper richiede Metal)
- `ffmpeg` installato (`brew install ffmpeg`)
- `mlx_whisper` installato (`pip install mlx-whisper`)

Lo script verifica i prerequisiti e termina con exit code 2 se mancano.

## Procedura

### Step 1 — Run trascrizione

```bash
python .claude/skills/transcript/scripts/transcript.py <file_or_dir> [--lang it|en] [--force]
```

Comportamento:
- Se `<path>` è un file → trascrive solo quel file
- Se `<path>` è una directory → trascrive tutti i file supportati al primo livello, sequenziale (no GPU contention)
- File con `<stem>_TRANSCRIPTS.txt` già esistente vengono **skippati** (usa `--force` per ri-trascrivere)
- Formati supportati: `.mp4 .mov .mkv .webm .avi` (video), `.mp3 .m4a .wav .ogg .aac .flac` (audio)

Output: `<source-stem>_TRANSCRIPTS.txt` accanto al file originale.

Riporta all'utente: N trascritti, N errori, N skippati.

### Step 2 — (Opzionale) Summary strutturato

Se l'utente passa `--summary` (o lo chiede a parole), per ogni trascrizione appena fatta:

1. Leggi il file `_TRANSCRIPTS.txt`
2. Detect content type:
   - Filename contiene "meeting" / "riunione" / "call" / "incontro" → **meeting**
   - Trascrizione menziona partecipanti, decisioni, action items → **meeting**
   - Altrimenti → **general**
3. Chiedi all'LLM (nella tua sessione di agente) di sintetizzare secondo la struttura giusta (vedi sotto)
4. Salva in `<source-stem>_SUMMARY.txt` accanto al transcript

**Meeting structure** (lingua matcha `--lang`, default italiano):

```markdown
## Riepilogo
3-5 frasi riassuntive di cosa è stato discusso

## Punti chiave
- 5-8 topic più importanti

## Decisioni prese
- Decisioni esplicite (se nessuna: "Nessuna decisione esplicita presa.")

## Azioni da svolgere
- [ ] Azione — *Assignee* (omitti assignee se non specificato)

## Temi aperti
- Domande irrisolte o argomenti rimandati
```

**General content structure** (sempre in inglese):

```markdown
## Abstract
3-5 sentence summary

## Key points
- 5-8 most important takeaways

## Entities
- Technologies, concepts, tools, people mentioned

## Notable quotes
- "Verbatim quote" (timestamp if inferable)
```

### Step 3 — Report

Output finale conciso:

```
transcript complete — YYYY-MM-DD
  Transcribed : N
  Skipped     : N (already had _TRANSCRIPTS.txt)
  Errors      : N
  Summaries   : N (if --summary)
```

## Esempio

**Utente**: "Trascrivi tutto in `_inbox/transcription/` con summary in italiano"

**Skill flow**:
1. `python .claude/skills/transcript/scripts/transcript.py _inbox/transcription/ --lang it`
   → 3 file trascritti, 1 skippato (già fatto)
2. Per ognuno dei 3 nuovi `_TRANSCRIPTS.txt`:
   - Leggo, decido `meeting` vs `general`
   - Chiamata LLM con il template corretto
   - Salvo `_SUMMARY.txt`
3. Report finale.

## Note

- **No upload remoto**: mlx_whisper gira interamente in locale, niente dati su servizi cloud.
- **Modello**: `mlx-community/whisper-large-v3-turbo` (hardcoded). Per cambiarlo, modifica `transcribe_one()` in `scripts/transcript.py`.
- **Lingua mista**: lascia `--lang` non specificato → auto-detect per file. Forzala se l'auto-detect sbaglia (es. file con accenti forti).
- **WAV temporaneo**: `/tmp/<stem>_transcript.wav` viene creato e poi cancellato. Su crash potrebbe restare orfano (innocuo).
- **Integrazione con wiki-ingest**: dopo `/transcript --summary`, l'utente può passare `_TRANSCRIPTS.txt` e `_SUMMARY.txt` a `/wiki-ingest` per generare wiki pages.
