// Eventi normalizzati emessi dal runner verso la UI.
//
// TODO confermare schema: i nomi-campo di `pi --mode json` non sono stati
// verificabili nel container di sviluppo (pi gira solo sul Mac dell'utente).
// La normalizzazione qui sotto e' tollerante: parse di ogni riga JSON e switch
// su `type` / `message.role`, ignorando i campi sconosciuti. Se lo schema reale
// differisce, adattare `normalizeRawEvent`.

export type StreamEvent =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string }
  | { kind: "toolCall"; name: string; detail?: string }
  | { kind: "result"; text?: string }
  | { kind: "error"; message: string }
  | { kind: "exit"; code: number | null };

// Forma "best effort" delle righe emesse da pi --mode json. Speculativa: tutti i
// campi sono opzionali, cosi' il parser non si rompe su varianti di schema.
interface RawPiEvent {
  type?: string;
  message?: {
    role?: string;
    content?: Array<{
      type?: string;
      text?: string;
      name?: string;
      // toolCall puo' avere nomi diversi (name / tool / toolName)
      tool?: string;
      toolName?: string;
      input?: unknown;
      arguments?: unknown;
    }>;
  };
  // varianti top-level possibili
  text?: string;
  error?: string;
  result?: unknown;
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

// Converte una riga JSON grezza in zero o piu' StreamEvent normalizzati.
export function normalizeRawEvent(raw: unknown): StreamEvent[] {
  if (raw == null || typeof raw !== "object") return [];
  const e = raw as RawPiEvent;
  const out: StreamEvent[] = [];

  // Errori top-level
  if (typeof e.error === "string" && e.error.length > 0) {
    out.push({ kind: "error", message: e.error });
  }

  // Messaggi con content[] (formato analogo alle righe JSONL di sessione)
  const content = e.message?.content;
  if (Array.isArray(content)) {
    for (const part of content) {
      const ptype = part?.type;
      if (ptype === "text" && typeof part.text === "string") {
        out.push({ kind: "text", text: part.text });
      } else if (ptype === "thinking" && typeof part.text === "string") {
        out.push({ kind: "thinking", text: part.text });
      } else if (ptype === "toolCall" || ptype === "tool_use" || ptype === "tool_call") {
        const name = part.name ?? part.tool ?? part.toolName ?? "tool";
        out.push({
          kind: "toolCall",
          name,
          detail: stringifyDetail(part.input ?? part.arguments),
        });
      } else if (typeof part?.text === "string") {
        // fallback: parte testuale di tipo sconosciuto
        out.push({ kind: "text", text: part.text });
      }
    }
  } else if (typeof e.text === "string") {
    // variante top-level con campo text diretto
    out.push({ kind: "text", text: e.text });
  }

  // Evento di risultato finale
  if (e.type === "result" || e.result != null) {
    const t = typeof e.result === "string" ? e.result : undefined;
    out.push({ kind: "result", text: t });
  }

  return out;
}
