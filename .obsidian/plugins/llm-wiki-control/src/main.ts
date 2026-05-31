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

  async onload(): Promise<void> {
    await this.loadSettings();

    const vaultRoot = this.getVaultRoot();
    this.runner = new PiRunner(vaultRoot, this.settings);
    this.sessionStore = new SessionStore(vaultRoot);

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
    // Le leaf vengono ripulite da Obsidian; nessuna risorsa persistente.
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
}
