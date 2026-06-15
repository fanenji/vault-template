import { FileSystemAdapter, Notice, Plugin, WorkspaceLeaf } from "obsidian";
import {
  DEFAULT_SETTINGS,
  LlmWikiSettings,
  LlmWikiSettingTab,
} from "./settings";
import { PiRunner, LintSummary } from "./runner/piRunner";
import { SessionStore } from "./sessions/sessionStore";
import { ControlView, VIEW_TYPE_LLM_WIKI } from "./view/ControlView";

export default class LlmWikiControlPlugin extends Plugin {
  settings!: LlmWikiSettings;
  runner!: PiRunner;
  sessionStore!: SessionStore;
  private lintIntervalId: number | null = null;
  private scheduledLintRunning = false;
  private graphIntervalId: number | null = null;
  private scheduledGraphRunning = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    const vaultRoot = this.getVaultRoot();
    this.runner = new PiRunner(vaultRoot, this.settings);
    this.sessionStore = new SessionStore(vaultRoot);

    this.setupLintSchedule();
    this.setupGraphSchedule();

    this.registerView(
      VIEW_TYPE_LLM_WIKI,
      (leaf) => new ControlView(leaf, this)
    );

    this.addRibbonIcon("brain-circuit", "Apri pannello LLM Wiki", () => {
      void this.activateView();
    });

    this.addCommand({
      id: "open-llm-wiki-panel",
      name: "Apri pannello LLM Wiki",
      callback: () => void this.activateView(),
    });

    this.addSettingTab(new LlmWikiSettingTab(this.app, this));
  }

  onunload(): void {
    // Termina eventuali processi pi ancora vivi (le leaf le ripulisce Obsidian).
    this.runner?.killAll();
  }

  private getVaultRoot(): string {
    const adapter = this.app.vault.adapter;
    if (adapter instanceof FileSystemAdapter) {
      return adapter.getBasePath();
    }
    // Plugin desktop-only: l'adapter e' sempre FileSystemAdapter, ma per
    // sicurezza tipata mostriamo un avviso.
    new Notice("LLM Wiki Control richiede un vault su filesystem (desktop).");
    return "";
  }

  async activateView(): Promise<void> {
    const { workspace } = this.app;
    let leaf: WorkspaceLeaf | null = null;
    const existing = workspace.getLeavesOfType(VIEW_TYPE_LLM_WIKI);
    if (existing.length > 0) {
      leaf = existing[0];
    } else {
      leaf = workspace.getRightLeaf(false);
      if (leaf) await leaf.setViewState({ type: VIEW_TYPE_LLM_WIKI, active: true });
    }
    if (leaf) workspace.revealLeaf(leaf);
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
    if (this.runner) this.runner.updateSettings(this.settings);
  }

  // (Ri)configura la schedulazione del lint in base ai settings. Chiamato a
  // onload e dai toggle/intervallo nel SettingTab.
  //
  // Implementata come check al minuto su `lintLastRunAt` persistito (non come
  // un setInterval lungo quanto l'intervallo): così un run scaduto parte anche
  // dopo un riavvio di Obsidian (con un solo timer di durata pari
  // all'intervallo, chi riavvia ogni giorno non vedrebbe mai un run con il
  // default giornaliero), e intervalli oltre ~24 giorni non overflowano il
  // limite a 32 bit di setInterval.
  setupLintSchedule(): void {
    if (this.lintIntervalId !== null) {
      window.clearInterval(this.lintIntervalId);
      this.lintIntervalId = null;
    }
    if (!this.settings.lintScheduleEnabled) return;
    this.lintIntervalId = window.setInterval(
      () => void this.maybeRunScheduledLint(),
      60_000
    );
    // Cleanup automatico allo unload del plugin.
    this.registerInterval(this.lintIntervalId);
    // Check all'avvio (dopo 30s, per lasciar caricare vault e indice): se il
    // run precedente è più vecchio dell'intervallo, parte subito.
    const startupTimer = window.setTimeout(
      () => void this.maybeRunScheduledLint(),
      30_000
    );
    this.register(() => window.clearTimeout(startupTimer));
  }

  // Esegue il lint schedulato solo se l'ultimo run è più vecchio dell'intervallo
  // configurato e nessun'altra skill è in corso (cede ai run manuali: il check
  // al minuto riproverà al termine).
  private async maybeRunScheduledLint(): Promise<void> {
    if (!this.settings.lintScheduleEnabled || !this.runner) return;
    if (this.scheduledLintRunning || this.runner.isBusy()) return;
    const minutes = Math.max(5, this.settings.lintIntervalMinutes || 1440);
    const elapsed = Date.now() - (this.settings.lintLastRunAt || 0);
    if (elapsed < minutes * 60_000) return;
    await this.runScheduledLint();
  }

  // Lint schedulato in due fasi:
  //   1. Lint deterministico via script (gratis, secondi, nessun LLM): scrive
  //      il report e ritorna il summary col diff vs run precedente.
  //   2. Solo se il diff segnala WARNING NUOVI, escalation alla skill completa
  //      via pi (check semantico + triage LLM). Il primo run (nessuno storico)
  //      è la baseline: niente escalation.
  // Prima la schedulazione lanciava una sessione LLM piena a ogni run, anche
  // quando non era cambiato nulla.
  private async runScheduledLint(): Promise<void> {
    if (this.scheduledLintRunning || !this.runner) return;
    this.scheduledLintRunning = true;
    this.settings.lintLastRunAt = Date.now();
    await this.saveSettings();

    try {
      // ── Fase 1: deterministico ──────────────────────────────────────────
      let summary: LintSummary | null;
      try {
        summary = await this.runner.runDeterministicLint();
      } catch (e) {
        new Notice(`LLM Wiki: lint schedulato fallito — ${String(e)}`);
        return;
      }

      if (!summary) {
        new Notice("LLM Wiki: lint completato (summary non disponibile) — vedi _notes/lint/lint-report.md.");
        return;
      }

      const diffPart =
        summary.new != null
          ? `${summary.new} nuove, ${summary.resolved} risolte — `
          : "";
      new Notice(
        `LLM Wiki lint: ${diffPart}${summary.warnings} warning, ${summary.info} info ` +
          `(_notes/lint/lint-report.md).`
      );

      // ── Fase 2: escalation LLM solo su warning nuovi ────────────────────
      if (!summary.new_warnings || summary.new_warnings <= 0) return;

      const ac = new AbortController();
      const timeout = window.setTimeout(() => ac.abort(), 30 * 60_000);
      new Notice(
        `LLM Wiki: ${summary.new_warnings} warning nuovi — avvio check semantico LLM…`
      );
      try {
        const code = await this.runner.runSkill({
          skill: "wiki-lint",
          prompt:
            "[llm-wiki:lint] Il lint deterministico ha appena trovato " +
            `${summary.new_warnings} warning nuovi (report in _notes/lint/lint-report.md). ` +
            "Esegui lo Step 2 della skill wiki-lint (check semantico: coppie simili + " +
            "campione a rotazione) in modalità non interattiva (senza --fix), e appendi " +
            "le issue semantiche al report.",
          signal: ac.signal,
          onEvent: () => {
            /* run in background: nessun rendering */
          },
        });
        if (ac.signal.aborted) {
          new Notice("LLM Wiki: check semantico interrotto per timeout (30 min).");
        } else if (code === 0 || code == null) {
          new Notice("LLM Wiki: check semantico completato (_notes/lint/lint-report.md).");
        } else {
          new Notice(`LLM Wiki: check semantico uscito con code ${code}.`);
        }
      } catch (e) {
        new Notice(`LLM Wiki: check semantico fallito — ${String(e)}`);
      } finally {
        window.clearTimeout(timeout);
      }
    } finally {
      this.scheduledLintRunning = false;
    }
  }

  // (Ri)configura la schedulazione di graph-analyze --deep. Stesso meccanismo
  // del lint (check al minuto su `graphLastRunAt` persistito): resiste ai
  // riavvii di Obsidian e a intervalli lunghi. Default settimanale.
  setupGraphSchedule(): void {
    if (this.graphIntervalId !== null) {
      window.clearInterval(this.graphIntervalId);
      this.graphIntervalId = null;
    }
    if (!this.settings.graphScheduleEnabled) return;
    this.graphIntervalId = window.setInterval(
      () => void this.maybeRunScheduledGraph(),
      60_000
    );
    this.registerInterval(this.graphIntervalId);
    // Check all'avvio (45s, dopo il check del lint per non contendere il mutex).
    const startupTimer = window.setTimeout(
      () => void this.maybeRunScheduledGraph(),
      45_000
    );
    this.register(() => window.clearTimeout(startupTimer));
  }

  private async maybeRunScheduledGraph(): Promise<void> {
    if (!this.settings.graphScheduleEnabled || !this.runner) return;
    // Cede a qualsiasi altra skill in corso (incluso il lint schedulato): il
    // check al minuto riproverà quando il mutex si libera.
    if (this.scheduledGraphRunning || this.runner.isBusy()) return;
    const minutes = Math.max(5, this.settings.graphIntervalMinutes || 10080);
    const elapsed = Date.now() - (this.settings.graphLastRunAt || 0);
    if (elapsed < minutes * 60_000) return;
    await this.runScheduledGraph();
  }

  // graph-analyze --deep --viz è puramente deterministico (nessun LLM): un'unica
  // fase. Scrive il report e le visualizzazioni (_notes/graph/graph.{json,html,canvas}).
  private async runScheduledGraph(): Promise<void> {
    if (this.scheduledGraphRunning || !this.runner) return;
    this.scheduledGraphRunning = true;
    this.settings.graphLastRunAt = Date.now();
    await this.saveSettings();
    try {
      await this.runner.runDeepGraphAnalyze();
      new Notice(
        "LLM Wiki: grafo aggiornato — report in _notes/graph-analysis-<data>.md, "
          + "viz in _notes/graph/ (graph.html · graph.canvas)."
      );
    } catch (e) {
      new Notice(`LLM Wiki: analisi grafo schedulata fallita — ${String(e)}`);
    } finally {
      this.scheduledGraphRunning = false;
    }
  }
}
