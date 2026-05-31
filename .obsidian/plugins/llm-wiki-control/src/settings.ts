import { App, PluginSettingTab, Setting, Notice } from "obsidian";
import type LlmWikiControlPlugin from "./main";

export interface LlmWikiSettings {
  piPath: string;
  provider: string;
  model: string;
  defaultIngestDir: string;
  showThinking: boolean;
  // Predisposti per l'iterazione 2 (schedulazione lint) — non usati in v1.
  lintScheduleEnabled: boolean;
  lintIntervalMinutes: number;
}

export const DEFAULT_SETTINGS: LlmWikiSettings = {
  piPath: "pi",
  provider: "",
  model: "",
  defaultIngestDir: "_inbox/clippings",
  showThinking: false,
  lintScheduleEnabled: false,
  lintIntervalMinutes: 1440,
};

export class LlmWikiSettingTab extends PluginSettingTab {
  plugin: LlmWikiControlPlugin;
  private models: string[] = [];

  constructor(app: App, plugin: LlmWikiControlPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "LLM Wiki Control" });

    new Setting(containerEl)
      .setName("Percorso di pi")
      .setDesc("Comando o path assoluto del binario pi (es. /opt/homebrew/bin/pi).")
      .addText((t) =>
        t
          .setPlaceholder("pi")
          .setValue(this.plugin.settings.piPath)
          .onChange(async (v) => {
            this.plugin.settings.piPath = v.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Cartella ingest predefinita")
      .setDesc("Percorso relativo nella vault usato dal pannello Ingest.")
      .addText((t) =>
        t
          .setPlaceholder("_inbox/clippings")
          .setValue(this.plugin.settings.defaultIngestDir)
          .onChange(async (v) => {
            this.plugin.settings.defaultIngestDir = v.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Mostra il thinking")
      .setDesc("Visualizza i blocchi di ragionamento dell'agente nello stream.")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.showThinking).onChange(async (v) => {
          this.plugin.settings.showThinking = v;
          await this.plugin.saveSettings();
        })
      );

    // Provider / Model con dropdown popolato da `pi --list-models`.
    const providerSetting = new Setting(containerEl)
      .setName("Provider")
      .setDesc("Lasciare vuoto per il default di pi.")
      .addText((t) =>
        t
          .setValue(this.plugin.settings.provider)
          .onChange(async (v) => {
            this.plugin.settings.provider = v.trim();
            await this.plugin.saveSettings();
          })
      );
    void providerSetting;

    const modelSetting = new Setting(containerEl)
      .setName("Model")
      .setDesc("Lasciare vuoto per il default di pi.");

    const renderModelControl = () => {
      modelSetting.controlEl.empty();
      if (this.models.length > 0) {
        modelSetting.addDropdown((d) => {
          d.addOption("", "(default)");
          for (const m of this.models) d.addOption(m, m);
          d.setValue(this.plugin.settings.model);
          d.onChange(async (v) => {
            this.plugin.settings.model = v;
            await this.plugin.saveSettings();
          });
        });
      } else {
        modelSetting.addText((t) =>
          t
            .setValue(this.plugin.settings.model)
            .onChange(async (v) => {
              this.plugin.settings.model = v.trim();
              await this.plugin.saveSettings();
            })
        );
      }
    };
    renderModelControl();

    new Setting(containerEl)
      .setName("Modelli disponibili")
      .setDesc("Popola il menu Model eseguendo `pi --list-models`.")
      .addButton((b) =>
        b.setButtonText("Ricarica modelli").onClick(async () => {
          b.setDisabled(true).setButtonText("Carico…");
          try {
            this.models = await this.plugin.runner.listModels();
            new Notice(`Trovati ${this.models.length} modelli`);
            renderModelControl();
          } catch (e) {
            new Notice(`Errore list-models: ${String(e)}`);
          } finally {
            b.setDisabled(false).setButtonText("Ricarica modelli");
          }
        })
      );
  }
}
