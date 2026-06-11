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

// Metadati per-file cacheati fra una listSessions e l'altra. La directory
// ~/.pi/agent/sessions contiene le sessioni di TUTTI i progetti: senza cache
// ogni apertura del pannello rileggeva la prima riga di ogni file, in modo
// sincrono sul main thread (freeze UI su directory grandi). La cache è
// invalidata per-file su (mtimeMs, size).
interface CacheEntry {
  mtimeMs: number;
  size: number;
  cwd: string | null;
  id: string;
  createdAt: number;
  firstUserText: string;
}

export class SessionStore {
  private vaultRoot: string;
  private vaultRootReal: string;
  private baseDir: string;
  private cache = new Map<string, CacheEntry>();

  constructor(vaultRoot: string) {
    this.vaultRoot = vaultRoot;
    // Confronto anche col realpath: pi registra il cwd risolto, e una vault
    // raggiunta via symlink (es. vault-test) non deve perdere lo storico.
    let real = vaultRoot;
    try {
      real = fs.realpathSync(vaultRoot);
    } catch {
      /* path non risolvibile: si usa il raw */
    }
    this.vaultRootReal = real;
    this.baseDir = path.join(os.homedir(), ".pi", "agent", "sessions");
  }

  private matchesVault(cwd: string | null): boolean {
    return cwd === this.vaultRoot || cwd === this.vaultRootReal;
  }

  // Legge solo la prima riga di un file (riga "session" con cwd/id/timestamp).
  private async readFirstLine(file: string): Promise<string | null> {
    let fh: fs.promises.FileHandle | null = null;
    try {
      fh = await fs.promises.open(file, "r");
      const buf = Buffer.alloc(8192);
      const { bytesRead } = await fh.read(buf, 0, buf.length, 0);
      const chunk = buf.toString("utf8", 0, bytesRead);
      const nl = chunk.indexOf("\n");
      return nl === -1 ? chunk : chunk.slice(0, nl);
    } catch {
      return null;
    } finally {
      await fh?.close().catch(() => undefined);
    }
  }

  // Parse completo di un file di sessione: header (cwd/id/timestamp) + primo
  // messaggio user. Usato solo su cache miss.
  private async parseFile(file: string): Promise<Omit<CacheEntry, "mtimeMs" | "size">> {
    const first = await this.readFirstLine(file);
    let cwd: string | null = null;
    let id = "";
    let createdAt = 0;
    if (first) {
      try {
        const obj = JSON.parse(first);
        if (typeof obj?.cwd === "string") cwd = obj.cwd;
        if (typeof obj?.id === "string") id = obj.id;
        if (typeof obj?.timestamp === "string") {
          const t = Date.parse(obj.timestamp);
          if (!Number.isNaN(t)) createdAt = t;
        }
      } catch {
        /* prima riga non parse-abile */
      }
    }
    if (!id) id = path.basename(file, ".jsonl");
    // firstUserText solo per i file della vault corrente (gli altri non
    // compariranno mai nello storico: inutile leggerli per intero).
    const firstUserText = this.matchesVault(cwd) ? await this.firstUserText(file) : "";
    return { cwd, id, createdAt, firstUserText };
  }

  // Entry di cache per un file, riparsata solo se (mtime, size) sono cambiati.
  private async getEntry(file: string): Promise<CacheEntry | null> {
    let stat: fs.Stats;
    try {
      stat = await fs.promises.stat(file);
    } catch {
      this.cache.delete(file);
      return null;
    }
    const cached = this.cache.get(file);
    if (cached && cached.mtimeMs === stat.mtimeMs && cached.size === stat.size) {
      return cached;
    }
    const parsed = await this.parseFile(file);
    const entry: CacheEntry = {
      mtimeMs: stat.mtimeMs,
      size: stat.size,
      createdAt: parsed.createdAt || stat.mtimeMs,
      cwd: parsed.cwd,
      id: parsed.id,
      firstUserText: parsed.firstUserText,
    };
    this.cache.set(file, entry);
    return entry;
  }

  // Tutti i .jsonl sotto baseDir (qualsiasi sottocartella): il filtro per
  // vault avviene sul campo `cwd` reale dentro il file, così evitiamo di
  // reverse-engineerare la sanitizzazione del path che fa pi.
  private async collectSessionFiles(): Promise<string[]> {
    const result: string[] = [];
    let dirs: string[];
    try {
      const entries = await fs.promises.readdir(this.baseDir, { withFileTypes: true });
      dirs = entries.filter((d) => d.isDirectory()).map((d) => path.join(this.baseDir, d.name));
    } catch {
      return result;
    }
    for (const dir of dirs) {
      try {
        const files = await fs.promises.readdir(dir);
        for (const f of files) {
          if (f.endsWith(".jsonl")) result.push(path.join(dir, f));
        }
      } catch {
        continue;
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

  // Elenca le sessioni della vault corrente, piu' recenti per prime.
  // skillFilter: se passato, tiene solo le sessioni col marker skill corrispondente.
  async listSessions(skillFilter?: string): Promise<SessionMeta[]> {
    const files = await this.collectSessionFiles();
    const metas: SessionMeta[] = [];
    for (const file of files) {
      const entry = await this.getEntry(file);
      if (!entry || !this.matchesVault(entry.cwd)) continue;
      const skillHint = extractSkillHint(entry.firstUserText);
      if (skillFilter && skillHint !== skillFilter) continue;
      metas.push({
        id: entry.id,
        file,
        createdAt: entry.createdAt,
        firstUserText: entry.firstUserText,
        skillHint,
      });
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
