import { FileSystemAdapter, Notice, Plugin, WorkspaceLeaf } from "obsidian";
import {
  DEFAULT_SETTINGS,
  LlmWikiSettings,
  LlmWikiSettingTab,
} from "./settings";
import { PiRunner } from "./runner/piRunner";
import { SessionStore } from "./sessions/sessionStore";
import { ControlView, VIEW_TYPE_LLM_WIKI } from "./view/ControlView";

export default class LlmWikiControlPlugin extends Plugin {
  settings!: LlmWikiSettings;
  runner!: PiRunner;
  sessionStore!: SessionStore;
  private lintIntervalId: number | null = null;
  private scheduledLintRunning = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    const vaultRoot = this.getVaultRoot();
    this.runner = new PiRunner(vaultRoot, this.settings);
    this.sessionStore = new SessionStore(vaultRoot);

    this.setupLintSchedule();

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

  // Esegue wiki-lint in background (no --fix), salva il report e notifica.
  // Timeout di sicurezza a 30 minuti: un processo pi bloccato non deve tenere
  // occupato il flag (e quindi saltare tutti i run successivi) per sempre.
  private async runScheduledLint(): Promise<void> {
    if (this.scheduledLintRunning || !this.runner) return;
    this.scheduledLintRunning = true;
    this.settings.lintLastRunAt = Date.now();
    await this.saveSettings();

    const ac = new AbortController();
    const timeoutMs = 30 * 60_000;
    const timeout = window.setTimeout(() => ac.abort(), timeoutMs);

    new Notice("LLM Wiki: avvio lint schedulato…");
    try {
      const code = await this.runner.runSkill({
        skill: "wiki-lint",
        prompt:
          "[llm-wiki:lint] Esegui un audit della wiki con wiki-lint in modalità " +
          "non interattiva (senza --fix). Salva il report in _notes/lint/lint-report.md.",
        signal: ac.signal,
        onEvent: () => {
          /* run in background: nessun rendering */
        },
      });
      if (ac.signal.aborted) {
        new Notice("LLM Wiki: lint schedulato interrotto per timeout (30 min).");
      } else if (code === 0 || code == null) {
        new Notice("LLM Wiki: lint schedulato completato (_notes/lint/lint-report.md).");
      } else {
        new Notice(`LLM Wiki: lint schedulato uscito con code ${code}.`);
      }
    } catch (e) {
      new Notice(`LLM Wiki: lint schedulato fallito — ${String(e)}`);
    } finally {
      window.clearTimeout(timeout);
      this.scheduledLintRunning = false;
    }
  }
}
