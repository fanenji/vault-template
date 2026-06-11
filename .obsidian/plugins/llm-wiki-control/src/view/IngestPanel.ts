import { App, Modal, Notice, TFile } from "obsidian";
import { StreamLog } from "./StreamLog";
import { PiRunner } from "../runner/piRunner";
import type { LlmWikiSettings } from "../settings";

const BATCH_WARN_THRESHOLD = 5; // da AGENTS.md: batch >5 file → avviso costo token

// Modal di conferma (sostituisce window.confirm: coerente con la UI Obsidian).
class ConfirmModal extends Modal {
  private message: string;
  private resolve: (ok: boolean) => void;
  private settled = false;

  constructor(app: App, message: string, resolve: (ok: boolean) => void) {
    super(app);
    this.message = message;
    this.resolve = resolve;
  }

  onOpen(): void {
    this.contentEl.createEl("p", { text: this.message });
    const row = this.contentEl.createDiv({ cls: "modal-button-container" });
    const okBtn = row.createEl("button", { text: "Procedi", cls: "mod-cta" });
    okBtn.onclick = () => {
      this.settled = true;
      this.resolve(true);
      this.close();
    };
    const cancelBtn = row.createEl("button", { text: "Annulla" });
    cancelBtn.onclick = () => this.close();
  }

  onClose(): void {
    this.contentEl.empty();
    if (!this.settled) this.resolve(false); // chiusura con X/Esc = annulla
  }
}

function confirmModal(app: App, message: string): Promise<boolean> {
  return new Promise((resolve) => new ConfirmModal(app, message, resolve).open());
}

export class IngestPanel {
  private app: App;
  private runner: PiRunner;
  private getSettings: () => LlmWikiSettings;
  private root: HTMLElement;
  private select!: HTMLSelectElement;
  private log!: StreamLog;
  private running = false;

  constructor(
    parent: HTMLElement,
    app: App,
    runner: PiRunner,
    getSettings: () => LlmWikiSettings
  ) {
    this.app = app;
    this.runner = runner;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }

  // Elenca i file della cartella ingest configurata (default _inbox/clippings).
  private listIngestFiles(): TFile[] {
    const dir = this.getSettings().defaultIngestDir.replace(/\/+$/, "");
    return this.app.vault
      .getFiles()
      .filter((f) => f.path === dir || f.path.startsWith(dir + "/"))
      .sort((a, b) => a.path.localeCompare(b.path));
  }

  private build(): void {
    this.root.createEl("p", {
      cls: "llm-wiki-hint",
      text: "Seleziona un file o l'intera cartella da ingerire nella wiki.",
    });

    const controls = this.root.createDiv({ cls: "llm-wiki-controls" });
    this.select = controls.createEl("select", { cls: "dropdown" });
    this.refreshFileList();

    const refreshBtn = controls.createEl("button", { text: "↻" });
    refreshBtn.onclick = () => this.refreshFileList();

    const runBtn = controls.createEl("button", { text: "Ingerisci", cls: "mod-cta" });
    runBtn.onclick = () => this.run();

    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);
  }

  private refreshFileList(): void {
    const files = this.listIngestFiles();
    this.select.empty();
    const dir = this.getSettings().defaultIngestDir;
    const allOpt = this.select.createEl("option", {
      text: `▸ Tutta la cartella (${files.length} file)`,
      value: "__all__",
    });
    void allOpt;
    for (const f of files) {
      this.select.createEl("option", { text: f.path, value: f.path });
    }
  }

  private async run(): Promise<void> {
    if (this.running) {
      new Notice("Ingest gia' in corso");
      return;
    }
    const dir = this.getSettings().defaultIngestDir;
    const value = this.select.value;
    const files = this.listIngestFiles();

    let target: string;
    let count: number;
    if (value === "__all__") {
      if (files.length === 0) {
        new Notice(`Nessun file in ${dir}`);
        return;
      }
      target = dir;
      count = files.length;
    } else {
      target = value;
      count = 1;
    }

    // Avviso costo token per batch grossi (regola AGENTS.md).
    if (count > BATCH_WARN_THRESHOLD) {
      const ok = await confirmModal(
        this.app,
        `Stai per ingerire ${count} file. L'operazione consuma token in modo ` +
          `proporzionale al numero/dimensione dei documenti. Procedere?`
      );
      if (!ok) return;
    }

    const prompt = `[llm-wiki:ingest] Ingerisci ${target} nella wiki.`;
    this.running = true;
    this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);

    const code = await this.runner.runSkill({
      skill: "wiki-ingest",
      prompt,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit") this.log.endRun(ev.code);
        else this.log.append(ev);
      },
    });
    this.log.endRun(code);
    this.running = false;
  }
}
