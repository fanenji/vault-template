import { App, Notice } from "obsidian";
import { StreamLog } from "./StreamLog";
import { PiRunner } from "../runner/piRunner";
import { SessionStore, SessionMeta, stripMarker } from "../sessions/sessionStore";
import type { LlmWikiSettings } from "../settings";

export class QueryPanel {
  private app: App;
  private runner: PiRunner;
  private store: SessionStore;
  private getSettings: () => LlmWikiSettings;
  private root: HTMLElement;
  private textarea!: HTMLTextAreaElement;
  private historyEl!: HTMLElement;
  private log!: StreamLog;
  private running = false;
  // Sessione corrente per i follow-up (resume via --session).
  private activeSessionId: string | null = null;

  constructor(
    parent: HTMLElement,
    app: App,
    runner: PiRunner,
    store: SessionStore,
    getSettings: () => LlmWikiSettings
  ) {
    this.app = app;
    this.runner = runner;
    this.store = store;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }

  private build(): void {
    this.textarea = this.root.createEl("textarea", {
      cls: "llm-wiki-query-input",
      attr: { rows: "3", placeholder: "Cosa vuoi cercare nella wiki?" },
    });

    const controls = this.root.createDiv({ cls: "llm-wiki-controls" });
    const searchBtn = controls.createEl("button", { text: "Cerca", cls: "mod-cta" });
    searchBtn.onclick = () => this.run(false);

    const followBtn = controls.createEl("button", { text: "Follow-up" });
    followBtn.onclick = () => this.run(true);

    const newBtn = controls.createEl("button", { text: "Nuova" });
    newBtn.onclick = () => {
      this.activeSessionId = null;
      this.log.clear();
      new Notice("Nuova conversazione");
    };

    this.log = new StreamLog(this.root, this.getSettings().showThinking);

    this.root.createEl("h4", { text: "Storico query" });
    this.historyEl = this.root.createDiv({ cls: "llm-wiki-history" });
    void this.refreshHistory();
  }

  async refreshHistory(): Promise<void> {
    this.historyEl.empty();
    let sessions: SessionMeta[] = [];
    try {
      sessions = await this.store.listSessions("query");
    } catch (e) {
      this.historyEl.createDiv({ cls: "llm-wiki-ev-error", text: String(e) });
      return;
    }
    if (sessions.length === 0) {
      this.historyEl.createEl("p", { cls: "llm-wiki-hint", text: "Nessuna query salvata." });
      return;
    }
    for (const s of sessions) {
      const row = this.historyEl.createDiv({ cls: "llm-wiki-history-row" });
      const date = new Date(s.createdAt).toLocaleString();
      row.createSpan({ cls: "llm-wiki-history-date", text: date });
      const title = stripMarker(s.firstUserText) || "(senza testo)";
      row.createSpan({ cls: "llm-wiki-history-title", text: title });
      row.onclick = () => this.resume(s);
    }
  }

  private async resume(s: SessionMeta): Promise<void> {
    this.activeSessionId = s.id;
    try {
      const events = await this.store.loadSession(s.file);
      this.log.setShowThinking(this.getSettings().showThinking);
      this.log.renderHistory(events);
      new Notice("Sessione caricata — usa Follow-up per continuare");
    } catch (e) {
      new Notice(`Errore caricamento sessione: ${String(e)}`);
    }
  }

  private async run(asFollowUp: boolean): Promise<void> {
    if (this.running) {
      new Notice("Query gia' in corso");
      return;
    }
    const text = this.textarea.value.trim();
    if (!text) {
      new Notice("Scrivi una domanda");
      return;
    }

    const useSession = asFollowUp ? this.activeSessionId ?? undefined : undefined;
    if (asFollowUp && !useSession) {
      new Notice("Nessuna sessione attiva: usa 'Cerca' per iniziarne una");
      return;
    }

    const prompt = `[llm-wiki:query] ${text}`;
    this.running = true;
    if (!asFollowUp) this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);

    const code = await this.runner.runSkill({
      skill: "wiki-query",
      prompt,
      sessionId: useSession,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit") this.log.endRun(ev.code);
        else if (ev.kind === "session") this.activeSessionId = ev.id;
        else this.log.append(ev);
      },
    });
    this.log.endRun(code);
    this.running = false;
    this.textarea.value = "";
    // Aggiorna lo storico (nuova sessione creata da pi).
    setTimeout(() => void this.refreshHistory(), 500);
  }
}
