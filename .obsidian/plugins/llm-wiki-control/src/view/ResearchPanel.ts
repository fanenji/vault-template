import { App, Notice } from "obsidian";
import { StreamLog } from "./StreamLog";
import { PiRunner } from "../runner/piRunner";
import { SessionStore, SessionMeta, stripMarker } from "../sessions/sessionStore";
import type { LlmWikiSettings } from "../settings";

// Pannello DeepResearch: come QueryPanel ma esegue la skill `deep-research`.
// Marca i prompt con [llm-wiki:research] per lo storico per-tab e offre un
// toggle "auto-ingest" (Step 8 della skill: scompone la pagina di ricerca in
// pagine entity/concept collegate).
export class ResearchPanel {
  private app: App;
  private runner: PiRunner;
  private store: SessionStore;
  private getSettings: () => LlmWikiSettings;
  private root: HTMLElement;
  private textarea!: HTMLTextAreaElement;
  private historyEl!: HTMLElement;
  private log!: StreamLog;
  private autoIngestCheckbox!: HTMLInputElement;
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
      attr: { rows: "3", placeholder: "Argomento da ricercare sul web…" },
    });

    const controls = this.root.createDiv({ cls: "llm-wiki-controls" });
    const searchBtn = controls.createEl("button", { text: "Ricerca", cls: "mod-cta" });
    searchBtn.onclick = () => this.run(false);

    const followBtn = controls.createEl("button", { text: "Follow-up" });
    followBtn.onclick = () => this.run(true);

    const newBtn = controls.createEl("button", { text: "Nuova" });
    newBtn.onclick = () => {
      this.activeSessionId = null;
      this.log.clear();
      new Notice("Nuova ricerca");
    };

    // Toggle auto-ingest (default off): istruisce la skill a eseguire lo Step 8,
    // scomponendo la ricerca in pagine entity/concept collegate alla wiki.
    const aiRow = this.root.createDiv({ cls: "llm-wiki-save-row" });
    const aiLabel = aiRow.createEl("label", { cls: "llm-wiki-save-label" });
    this.autoIngestCheckbox = aiLabel.createEl("input", { attr: { type: "checkbox" } });
    aiLabel.createSpan({ text: " Auto-ingest (scomponi in pagine entity/concept)" });

    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);

    this.root.createEl("h4", { text: "Storico ricerche" });
    this.historyEl = this.root.createDiv({ cls: "llm-wiki-history" });
    void this.refreshHistory();
  }

  async refreshHistory(): Promise<void> {
    this.historyEl.empty();
    let sessions: SessionMeta[] = [];
    try {
      sessions = await this.store.listSessions("research");
    } catch (e) {
      this.historyEl.createDiv({ cls: "llm-wiki-ev-error", text: String(e) });
      return;
    }
    if (sessions.length === 0) {
      this.historyEl.createEl("p", { cls: "llm-wiki-hint", text: "Nessuna ricerca salvata." });
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
      this.log.setShowToolCalls(this.getSettings().showToolCalls);
      this.log.renderHistory(events);
      new Notice("Ricerca caricata — usa Follow-up per continuare");
    } catch (e) {
      new Notice(`Errore caricamento sessione: ${String(e)}`);
    }
  }

  private async run(asFollowUp: boolean): Promise<void> {
    if (this.running) {
      new Notice("Ricerca gia' in corso");
      return;
    }
    const text = this.textarea.value.trim();
    if (!text) {
      new Notice("Scrivi un argomento");
      return;
    }

    const useSession = asFollowUp ? this.activeSessionId ?? undefined : undefined;
    if (asFollowUp && !useSession) {
      new Notice("Nessuna sessione attiva: usa 'Ricerca' per iniziarne una");
      return;
    }

    // Controllo esplicito dello Step 8 (auto-ingest) in base al toggle.
    const ingestSuffix = this.autoIngestCheckbox.checked
      ? " Esegui anche lo Step 8 (auto-ingest): invoca wiki-ingest sulla pagina di ricerca salvata per scomporla in pagine entity/concept collegate."
      : " Non eseguire l'auto-ingest (Step 8): salva solo la pagina di ricerca.";
    const prompt = `[llm-wiki:research] ${text}${ingestSuffix}`;

    this.running = true;
    if (!asFollowUp) this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);

    const code = await this.runner.runSkill({
      skill: "deep-research",
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
