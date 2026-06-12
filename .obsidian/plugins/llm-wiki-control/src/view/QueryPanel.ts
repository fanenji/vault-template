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
  private saveBtn!: HTMLButtonElement;
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

    // Salvataggio a posteriori: si abilita quando esiste una risposta nella
    // sessione attiva (ricerca completata o sessione ripresa dallo storico) e
    // manda un follow-up alla skill che esegue lo step 4 (save in wiki/queries/).
    this.saveBtn = controls.createEl("button", { text: "Salva la risposta in wiki/queries/" });
    this.saveBtn.disabled = true;
    this.saveBtn.onclick = () => this.saveAnswer();

    const newBtn = controls.createEl("button", { text: "Nuova" });
    newBtn.onclick = () => {
      this.activeSessionId = null;
      this.saveBtn.disabled = true;
      this.log.clear();
      new Notice("Nuova conversazione");
    };

    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);

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
      this.log.setShowToolCalls(this.getSettings().showToolCalls);
      this.log.renderHistory(events);
      // La sessione ripresa contiene una risposta: è salvabile.
      this.saveBtn.disabled = false;
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
    this.saveBtn.disabled = true;
    if (!asFollowUp) this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);

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
    // La risposta è salvabile solo se la run è andata a buon fine e c'è una
    // sessione da riprendere col follow-up di salvataggio.
    this.saveBtn.disabled = !(code === 0 && this.activeSessionId);
    // Aggiorna lo storico (nuova sessione creata da pi): subito, con un
    // retry dopo 2s nel caso il file di sessione non sia ancora flushato.
    await this.refreshHistory();
    setTimeout(() => void this.refreshHistory(), 2000);
  }

  // Follow-up sulla sessione attiva che chiede alla skill di eseguire lo
  // step 4 (save in wiki/queries/ + aggiornamento indice QMD) sulla risposta
  // già prodotta. Il bottone resta disabilitato dopo un save riuscito (la
  // stessa risposta non va salvata due volte) e si riabilita su errore.
  private async saveAnswer(): Promise<void> {
    if (this.running) {
      new Notice("Operazione gia' in corso");
      return;
    }
    if (!this.activeSessionId) {
      new Notice("Nessuna risposta da salvare: esegui prima una ricerca");
      return;
    }
    const prompt =
      "[llm-wiki:query] Salva la risposta precedente come pagina in wiki/queries/ " +
      "(step 4 della skill) e aggiorna l'indice QMD.";
    this.running = true;
    this.saveBtn.disabled = true;
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);

    const code = await this.runner.runSkill({
      skill: "wiki-query",
      prompt,
      sessionId: this.activeSessionId,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit") this.log.endRun(ev.code);
        else if (ev.kind === "session") this.activeSessionId = ev.id;
        else this.log.append(ev);
      },
    });
    this.log.endRun(code);
    this.running = false;
    if (code === 0) {
      new Notice("Risposta salvata in wiki/queries/");
    } else {
      new Notice("Salvataggio non riuscito — riprova");
      this.saveBtn.disabled = false;
    }
  }
}
