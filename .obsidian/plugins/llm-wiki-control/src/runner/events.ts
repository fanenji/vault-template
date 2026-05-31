// Eventi normalizzati emessi dal runner verso la UI.
//
// Schema verificato su pi v0.78 (`pi --mode json`). Esistono DUE formati di riga
// che convergono qui (lo stesso normalizer serve sia lo stream live del runner
// sia il re-render dello storico da `sessionStore.loadSession`):
//
//  1. STREAM LIVE (stdout di `pi -p --mode json`):
//     - { type: "session", id, cwd, ... }                      → inizio sessione
//     - { type: "message_update", assistantMessageEvent: {     → delta incrementali
//         type: "text_delta",    delta: "..."                  → testo token-by-token
//         type: "thinking_delta",delta: "..."                  → reasoning token-by-token
//         type: "thinking_end",  content: "..."                → reasoning completo
//         ... (text_start/end, thinking_start, toolcall_* ignorati)
//       } }
//     - { type: "tool_execution_start", toolName, args }       → esecuzione tool
//     - message_start / message_end / turn_* / agent_* / tool_execution_update|end
//       → ignorati di proposito (message_start/end portano content[] e
//         causerebbero echo del prompt + duplicazione del testo gia' streammato)
//
//  2. FILE DI SESSIONE (~/.pi/agent/sessions/*.jsonl, righe `type: "message"`):
//     - { type: "message", message: { role, content: [
//         { type: "text", text },
//         { type: "thinking", thinking },
//         { type: "toolCall", name, arguments } ] } }
//
// I due formati sono separati dal valore di `type` (lo stream usa
// message_update/message_start/...; i file di sessione usano il `message` puro),
// quindi un singolo switch li discrimina senza ambiguita'.

export type StreamEvent =
  | { kind: "session"; id: string }
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string }
  | { kind: "toolCall"; name: string; detail?: string }
  | { kind: "result"; text?: string }
  | { kind: "error"; message: string }
  | { kind: "exit"; code: number | null };

// Parte di contenuto dentro un messaggio completo (formato file di sessione).
interface ContentPart {
  type?: string;
  text?: string;
  thinking?: string;
  name?: string;
  arguments?: unknown;
  input?: unknown;
}

// Forma delle righe di pi --mode json rilevanti per la UI. Tutti i campi sono
// opzionali: il parser ignora silenziosamente le righe/varianti non gestite.
interface RawPiEvent {
  type?: string;
  id?: string;
  error?: string;
  // type === "message" (file di sessione)
  message?: { role?: string; content?: ContentPart[] };
  // type === "message_update" (stream live)
  assistantMessageEvent?: { type?: string; delta?: string; content?: string };
  // type === "tool_execution_start" (stream live)
  toolName?: string;
  args?: unknown;
}

function stringifyDetail(value: unknown): string | undefined {
  if (value == null) return undefined;
  if (typeof value === "string") return value;
  try {
    const s = JSON.stringify(value);
    return s.length > 200 ? s.slice(0, 197) + "…" : s;
  } catch {
    return undefined;
  }
}

// Estrae gli StreamEvent dalle parti di un messaggio completo (file di sessione).
function partsToEvents(content: ContentPart[]): StreamEvent[] {
  const out: StreamEvent[] = [];
  for (const part of content) {
    const ptype = part?.type;
    if (ptype === "text" && typeof part.text === "string") {
      out.push({ kind: "text", text: part.text });
    } else if (ptype === "thinking" && typeof part.thinking === "string") {
      // NB: nelle parti "thinking" il testo sta nel campo `thinking`, non `text`.
      out.push({ kind: "thinking", text: part.thinking });
    } else if (ptype === "toolCall" || ptype === "tool_use" || ptype === "tool_call") {
      out.push({
        kind: "toolCall",
        name: part.name ?? "tool",
        detail: stringifyDetail(part.arguments ?? part.input),
      });
    }
  }
  return out;
}

// Converte una riga JSON grezza in zero o piu' StreamEvent normalizzati.
export function normalizeRawEvent(raw: unknown): StreamEvent[] {
  if (raw == null || typeof raw !== "object") return [];
  const e = raw as RawPiEvent;
  const out: StreamEvent[] = [];

  // Errori top-level (qualsiasi tipo di evento puo' portarli).
  if (typeof e.error === "string" && e.error.length > 0) {
    out.push({ kind: "error", message: e.error });
  }

  switch (e.type) {
    case "session": {
      // Cattura l'id della sessione appena creata: serve al QueryPanel per i
      // follow-up immediati (--session <id>) senza dover passare dallo storico.
      if (typeof e.id === "string" && e.id.length > 0) {
        out.push({ kind: "session", id: e.id });
      }
      break;
    }

    case "message": {
      // Formato file di sessione: messaggio completo con content[].
      const content = e.message?.content;
      if (Array.isArray(content)) out.push(...partsToEvents(content));
      break;
    }

    case "message_update": {
      // Stream live: delta incrementali dentro assistantMessageEvent.
      const ame = e.assistantMessageEvent;
      if (ame?.type === "text_delta" && typeof ame.delta === "string") {
        out.push({ kind: "text", text: ame.delta });
      } else if (ame?.type === "thinking_end" && typeof ame.content === "string") {
        // Il reasoning lo emettiamo come blocco unico a fine thinking (un solo
        // <details>), non per-delta, per non frammentare la UI.
        out.push({ kind: "thinking", text: ame.content });
      }
      break;
    }

    case "tool_execution_start": {
      if (typeof e.toolName === "string") {
        out.push({ kind: "toolCall", name: e.toolName, detail: stringifyDetail(e.args) });
      }
      break;
    }

    // Tutti gli altri tipi (message_start/end, turn_*, agent_*,
    // tool_execution_update|end, text_start/end, thinking_start, toolcall_*)
    // sono volutamente ignorati: il testo arriva gia' completo dai delta.
  }

  return out;
}
