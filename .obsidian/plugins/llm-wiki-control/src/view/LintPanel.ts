import { Notice } from "obsidian";
import { StreamLog } from "./StreamLog";
import { PiRunner } from "../runner/piRunner";
import type { LlmWikiSettings } from "../settings";

// Pannello Lint: esegue la skill `wiki-lint` (audit della wiki). Niente input
// testuale; checkbox opzionale per il flag --fix (applica le correzioni).
export class LintPanel {
  private runner: PiRunner;
  private getSettings: () => LlmWikiSettings;
  private root: HTMLElement;
  private log!: StreamLog;
  private fixCheckbox!: HTMLInputElement;
  private running = false;

  constructor(parent: HTMLElement, runner: PiRunner, getSettings: () => LlmWikiSettings) {
    this.runner = runner;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }

  private build(): void {
    this.root.createEl("p", {
      cls: "llm-wiki-hint",
      text: "Audit della wiki: link rotti, pagine orfane, frontmatter, e problemi semantici (contraddizioni, stale, missing-page).",
    });

    const fixRow = this.root.createDiv({ cls: "llm-wiki-save-row" });
    const fixLabel = fixRow.createEl("label", { cls: "llm-wiki-save-label" });
    this.fixCheckbox = fixLabel.createEl("input", { attr: { type: "checkbox" } });
    fixLabel.createSpan({ text: " --fix (applica correzioni: frontmatter mancanti, stub missing-page)" });

    const controls = this.root.createDiv({ cls: "llm-wiki-controls" });
    const runBtn = controls.createEl("button", { text: "Esegui audit", cls: "mod-cta" });
    runBtn.onclick = () => this.run();

    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);
  }

  private async run(): Promise<void> {
    if (this.running) {
      new Notice("Audit gia' in corso");
      return;
    }
    const fix = this.fixCheckbox.checked;
    const prompt =
      "[llm-wiki:lint] Esegui un audit completo della wiki con la skill wiki-lint" +
      (fix
        ? " e applica le correzioni automatiche (--fix: frontmatter mancanti, stub missing-page)."
        : " (sola analisi, senza --fix).") +
      " Salva il report in wiki/lint-report.md.";

    this.running = true;
    this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);

    const code = await this.runner.runSkill({
      skill: "wiki-lint",
      prompt,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit") this.log.endRun(ev.code);
        else if (ev.kind !== "session") this.log.append(ev);
      },
    });
    this.log.endRun(code);
    this.running = false;
  }
}
