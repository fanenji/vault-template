import { ItemView, WorkspaceLeaf } from "obsidian";
import type LlmWikiControlPlugin from "../main";
import { IngestPanel } from "./IngestPanel";
import { QueryPanel } from "./QueryPanel";

export const VIEW_TYPE_LLM_WIKI = "llm-wiki-control";

type TabId = "ingest" | "query";

export class ControlView extends ItemView {
  private plugin: LlmWikiControlPlugin;
  private tabButtons: Map<TabId, HTMLButtonElement> = new Map();
  private panes: Map<TabId, HTMLElement> = new Map();
  private active: TabId = "query";

  constructor(leaf: WorkspaceLeaf, plugin: LlmWikiControlPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_LLM_WIKI;
  }

  getDisplayText(): string {
    return "LLM Wiki";
  }

  getIcon(): string {
    return "brain-circuit";
  }

  async onOpen(): Promise<void> {
    const container = this.contentEl;
    container.empty();
    container.addClass("llm-wiki-control-view");

    const tabBar = container.createDiv({ cls: "llm-wiki-tabs" });
    const body = container.createDiv({ cls: "llm-wiki-tab-body" });

    const makeTab = (id: TabId, label: string) => {
      const btn = tabBar.createEl("button", { text: label, cls: "llm-wiki-tab" });
      btn.onclick = () => this.selectTab(id);
      this.tabButtons.set(id, btn);
      const pane = body.createDiv({ cls: "llm-wiki-pane" });
      this.panes.set(id, pane);
      return pane;
    };

    const queryPane = makeTab("query", "Query");
    const ingestPane = makeTab("ingest", "Ingest");

    // Istanzia i panel (Query include il proprio storico).
    new QueryPanel(
      queryPane,
      this.app,
      this.plugin.runner,
      this.plugin.sessionStore,
      () => this.plugin.settings
    );
    new IngestPanel(ingestPane, this.app, this.plugin.runner, () => this.plugin.settings);

    this.selectTab(this.active);
  }

  private selectTab(id: TabId): void {
    this.active = id;
    for (const [tid, btn] of this.tabButtons) {
      btn.toggleClass("is-active", tid === id);
    }
    for (const [tid, pane] of this.panes) {
      pane.toggleClass("is-hidden", tid !== id);
    }
  }

  async onClose(): Promise<void> {
    this.contentEl.empty();
  }
}
