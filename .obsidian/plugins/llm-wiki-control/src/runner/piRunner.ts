import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import * as readline from "readline";
import * as path from "path";
import { normalizeRawEvent, StreamEvent } from "./events";
import type { LlmWikiSettings } from "../settings";

export interface RunSkillOptions {
  // Nome cartella skill sotto .claude/skills/ (es. "wiki-query")
  skill: string;
  prompt: string;
  // Riprende una sessione pi esistente (--session <id>)
  sessionId?: string;
  // Riprende l'ultima sessione (--continue)
  continueLast?: boolean;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

// Estende il PATH ereditato: Obsidian su macOS lancia con un PATH ridotto che
// spesso non include Homebrew, dove vive `pi`.
function buildEnv(): NodeJS.ProcessEnv {
  const extra = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"];
  const current = process.env.PATH ?? "";
  const merged = [current, ...extra].filter(Boolean).join(path.delimiter);
  return { ...process.env, PATH: merged };
}

// Termina il child e tutti i suoi discendenti (python, qmd, …). Su POSIX i
// child vengono spawnati detached → nuovo process group → kill(-pid) raggiunge
// l'intero albero. Su Windows fallback al kill del solo processo.
function killTree(child: ChildProcessWithoutNullStreams): void {
  if (process.platform !== "win32" && child.pid) {
    try {
      process.kill(-child.pid, "SIGTERM");
      return;
    } catch {
      /* process group già terminato o non disponibile: fallback sotto */
    }
  }
  try {
    child.kill("SIGTERM");
  } catch {
    /* già terminato */
  }
}

export class PiRunner {
  private vaultRoot: string;
  private settings: LlmWikiSettings;
  // Tutti i child vivi (skill + list-models): permette killAll() all'unload.
  private children = new Set<ChildProcessWithoutNullStreams>();
  // Mutex globale: una sola skill alla volta. Le skill mutano wiki/, lo stato
  // .llm-wiki/ e l'indice QMD: run concorrenti (anche da pannelli diversi o
  // dal lint schedulato) si corromperebbero a vicenda.
  private skillRunning = false;

  constructor(vaultRoot: string, settings: LlmWikiSettings) {
    this.vaultRoot = vaultRoot;
    this.settings = settings;
  }

  updateSettings(settings: LlmWikiSettings): void {
    this.settings = settings;
  }

  // True se una skill è in esecuzione (usato dai pannelli e dal lint schedulato).
  isBusy(): boolean {
    return this.skillRunning;
  }

  // Termina tutti i processi vivi (chiamato all'unload del plugin).
  killAll(): void {
    for (const child of this.children) killTree(child);
    this.children.clear();
  }

  private skillPath(skill: string): string {
    return path.join(this.vaultRoot, ".claude", "skills", skill);
  }

  private buildArgs(opts: RunSkillOptions): string[] {
    const args = ["-p", "--mode", "json"];
    if (opts.sessionId) {
      args.push("--session", opts.sessionId);
    } else if (opts.continueLast) {
      args.push("--continue");
    }
    if (this.settings.provider) args.push("--provider", this.settings.provider);
    if (this.settings.model) args.push("--model", this.settings.model);
    args.push("--skill", this.skillPath(opts.skill));
    args.push(opts.prompt);
    return args;
  }

  // Lancia una skill in headless e inoltra gli eventi normalizzati via onEvent.
  // Risolve quando il processo termina (qualsiasi exit code).
  runSkill(opts: RunSkillOptions): Promise<number | null> {
    // Mutex: rifiuta subito se un'altra skill è in corso (vedi commento sul campo).
    if (this.skillRunning) {
      opts.onEvent({
        kind: "error",
        message:
          "Un'altra operazione LLM è già in corso in questa vault — attendi che finisca.",
      });
      opts.onEvent({ kind: "exit", code: 1 });
      return Promise.resolve(1);
    }

    const args = this.buildArgs(opts);
    const piPath = this.settings.piPath || "pi";

    return new Promise((resolve) => {
      let child: ChildProcessWithoutNullStreams;
      try {
        child = spawn(piPath, args, {
          cwd: this.vaultRoot,
          env: buildEnv(),
          // POSIX: nuovo process group, così lo Stop termina anche i processi
          // figli della skill (python, qmd) e non solo pi. Vedi killTree().
          detached: process.platform !== "win32",
        });
      } catch (err) {
        opts.onEvent({
          kind: "error",
          message: `Impossibile lanciare "${piPath}": ${String(err)}`,
        });
        opts.onEvent({ kind: "exit", code: 1 });
        resolve(1);
        return;
      }
      this.skillRunning = true;
      this.children.add(child);

      // Chiudi subito stdin: con `pi -p` non passiamo input, ma se lo stdin del
      // child resta una pipe aperta pi resta in attesa di EOF e non emette nulla
      // (sintomo: "In esecuzione…" infinito, nessun processo che produce output
      // sotto Electron). end() invia EOF immediato e pi parte.
      child.stdin.end();

      const onAbort = () => killTree(child);
      if (opts.signal) {
        if (opts.signal.aborted) onAbort();
        else opts.signal.addEventListener("abort", onAbort, { once: true });
      }

      const rl = readline.createInterface({ input: child.stdout });
      rl.on("line", (line: string) => {
        const trimmed = line.trim();
        if (!trimmed) return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(trimmed);
        } catch {
          // riga non-JSON (log umano di pi): la mostriamo come testo grezzo
          opts.onEvent({ kind: "text", text: trimmed });
          return;
        }
        for (const ev of normalizeRawEvent(parsed)) opts.onEvent(ev);
      });

      let stderrBuf = "";
      child.stderr.on("data", (d: Buffer) => {
        stderrBuf += d.toString();
      });

      child.on("error", (err) => {
        opts.onEvent({
          kind: "error",
          message: `Errore di processo: ${err.message}`,
        });
      });

      child.on("close", (code) => {
        rl.close();
        this.children.delete(child);
        this.skillRunning = false;
        if (opts.signal) opts.signal.removeEventListener("abort", onAbort);
        if (code !== 0 && stderrBuf.trim()) {
          opts.onEvent({ kind: "error", message: stderrBuf.trim() });
        }
        opts.onEvent({ kind: "exit", code });
        resolve(code);
      });
    });
  }

  // Esegue `pi --list-models` una tantum e ritorna le righe non vuote.
  listModels(): Promise<string[]> {
    const piPath = this.settings.piPath || "pi";
    return new Promise((resolve, reject) => {
      let out = "";
      let err = "";
      let child: ChildProcessWithoutNullStreams;
      try {
        child = spawn(piPath, ["--list-models"], { env: buildEnv() });
      } catch (e) {
        reject(e);
        return;
      }
      this.children.add(child);
      child.stdin.end(); // EOF immediato: evita che pi resti in attesa di stdin
      child.stdout.on("data", (d: Buffer) => (out += d.toString()));
      child.stderr.on("data", (d: Buffer) => (err += d.toString()));
      child.on("error", reject);
      child.on("close", (code) => {
        this.children.delete(child);
        if (code !== 0) {
          reject(new Error(err.trim() || `pi --list-models exit ${code}`));
          return;
        }
        const lines = out
          .split("\n")
          .map((l) => l.trim())
          .filter((l) => l.length > 0);
        resolve(lines);
      });
    });
  }
}
