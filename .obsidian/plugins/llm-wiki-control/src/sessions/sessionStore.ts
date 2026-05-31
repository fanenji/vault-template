import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import * as readline from "readline";
import { StreamEvent, normalizeRawEvent } from "../runner/events";

export interface SessionMeta {
  id: string;
  file: string;
  createdAt: number; // epoch ms
  firstUserText: string;
  skillHint: string | null; // ricavato dal marker [llm-wiki:<skill>]
}

const MARKER_RE = /\[llm-wiki:([a-z-]+)\]/i;

// Estrae lo skillHint da un prompt marcato dal plugin.
export function extractSkillHint(text: string): string | null {
  const m = text.match(MARKER_RE);
  return m ? m[1].toLowerCase() : null;
}

// Rimuove il marker dalla visualizzazione del titolo storico.
export function stripMarker(text: string): string {
  return text.replace(MARKER_RE, "").trim();
}

export class SessionStore {
  private vaultRoot: string;
  private baseDir: string;

  constructor(vaultRoot: string) {
    this.vaultRoot = vaultRoot;
    this.baseDir = path.join(os.homedir(), ".pi", "agent", "sessions");
  }

  // Legge solo la prima riga di un file (riga "session" con cwd/id/timestamp).
  private readFirstLine(file: string): string | null {
    try {
      const fd = fs.openSync(file, "r");
      try {
        const buf = Buffer.alloc(8192);
        const bytes = fs.readSync(fd, buf, 0, buf.length, 0);
        const chunk = buf.toString("utf8", 0, bytes);
        const nl = chunk.indexOf("\n");
        return nl === -1 ? chunk : chunk.slice(0, nl);
      } finally {
        fs.closeSync(fd);
      }
    } catch {
      return null;
    }
  }

  // Trova tutti i .jsonl la cui prima riga ha cwd === vaultRoot, in QUALSIASI
  // sottocartella. Cosi' evitiamo di reverse-engineerare la sanitizzazione del
  // path che fa pi: ci basiamo sul campo `cwd` reale dentro il file.
  private collectSessionFiles(): string[] {
    const result: string[] = [];
    let dirs: string[];
    try {
      dirs = fs.readdirSync(this.baseDir, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => path.join(this.baseDir, d.name));
    } catch {
      return result;
    }
    for (const dir of dirs) {
      let files: string[];
      try {
        files = fs.readdirSync(dir).filter((f) => f.endsWith(".jsonl"));
      } catch {
        continue;
      }
      for (const f of files) {
        const full = path.join(dir, f);
        const first = this.readFirstLine(full);
        if (!first) continue;
        try {
          const obj = JSON.parse(first);
          if (obj && obj.cwd === this.vaultRoot) result.push(full);
        } catch {
          // ignora prime righe non parse-abili
        }
      }
    }
    return result;
  }

  // Ricava il primo messaggio user (content[0].text) leggendo il file riga per
  // riga finche' non lo trova.
  private async firstUserText(file: string): Promise<string> {
    return new Promise((resolve) => {
      let found = "";
      const stream = fs.createReadStream(file, { encoding: "utf8" });
      const rl = readline.createInterface({ input: stream });
      rl.on("line", (line) => {
        if (found) return;
        const t = line.trim();
        if (!t) return;
        try {
          const obj = JSON.parse(t);
          if (obj?.type === "message" && obj?.message?.role === "user") {
            const c = obj.message?.content;
            if (Array.isArray(c) && typeof c[0]?.text === "string") {
              found = c[0].text;
              rl.close();
            }
          }
        } catch {
          /* ignora */
        }
      });
      rl.on("close", () => resolve(found));
      rl.on("error", () => resolve(found));
    });
  }

  // Estrae id e timestamp dalla prima riga / dal nome file.
  private parseHeader(file: string): { id: string; createdAt: number } {
    const first = this.readFirstLine(file);
    let id = "";
    let createdAt = 0;
    if (first) {
      try {
        const obj = JSON.parse(first);
        if (typeof obj?.id === "string") id = obj.id;
        if (typeof obj?.timestamp === "string") {
          const t = Date.parse(obj.timestamp);
          if (!Number.isNaN(t)) createdAt = t;
        }
      } catch {
        /* ignora */
      }
    }
    if (!createdAt) {
      try {
        createdAt = fs.statSync(file).mtimeMs;
      } catch {
        createdAt = Date.now();
      }
    }
    if (!id) id = path.basename(file, ".jsonl");
    return { id, createdAt };
  }

  // Elenca le sessioni della vault corrente, piu' recenti per prime.
  // skillFilter: se passato, tiene solo le sessioni col marker skill corrispondente.
  async listSessions(skillFilter?: string): Promise<SessionMeta[]> {
    const files = this.collectSessionFiles();
    const metas: SessionMeta[] = [];
    for (const file of files) {
      const { id, createdAt } = this.parseHeader(file);
      const firstUserText = await this.firstUserText(file);
      const skillHint = extractSkillHint(firstUserText);
      if (skillFilter && skillHint !== skillFilter) continue;
      metas.push({ id, file, createdAt, firstUserText, skillHint });
    }
    metas.sort((a, b) => b.createdAt - a.createdAt);
    return metas;
  }

  // Ricarica gli eventi di una sessione per il re-render nello StreamLog.
  async loadSession(file: string): Promise<StreamEvent[]> {
    return new Promise((resolve) => {
      const events: StreamEvent[] = [];
      const stream = fs.createReadStream(file, { encoding: "utf8" });
      const rl = readline.createInterface({ input: stream });
      rl.on("line", (line) => {
        const t = line.trim();
        if (!t) return;
        try {
          const obj = JSON.parse(t);
          if (obj?.type === "message") {
            for (const ev of normalizeRawEvent(obj)) events.push(ev);
          }
        } catch {
          /* ignora */
        }
      });
      rl.on("close", () => resolve(events));
      rl.on("error", () => resolve(events));
    });
  }
}
