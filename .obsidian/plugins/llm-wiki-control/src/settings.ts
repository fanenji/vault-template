import { App, PluginSettingTab, Setting, Notice } from "obsidian";
import type LlmWikiControlPlugin from "./main";

export interface LlmWikiSettings {
  piPath: string;
  provider: string;
  model: string;
  defaultIngestDir: string;
  showThinking: boolean;
  showToolCalls: boolean;
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
  showToolCalls: false,
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

  // ── TAVILY_API_KEY: proxy verso .llm-wiki/secrets.json ──────────────────────
  // La source of truth è il file (letto da deep-research/web_search.py): NON
  // salviamo il segreto nei dati del plugin. Accesso via vault adapter (path
  // relativi alla vault root, dotfolder inclusi).
  private static readonly SECRETS_DIR = ".llm-wiki";
  private static readonly SECRETS_PATH = ".llm-wiki/secrets.json";

  private async readTavilyKey(): Promise<string> {
    try {
      const adapter = this.app.vault.adapter;
      if (!(await adapter.exists(LlmWikiSettingTab.SECRETS_PATH))) return "";
      const data = JSON.parse(await adapter.read(LlmWikiSettingTab.SECRETS_PATH));
      const k = data?.TAVILY_API_KEY;
      return typeof k === "string" ? k : "";
    } catch {
      return "";
    }
  }

  private async writeTavilyKey(value: string): Promise<void> {
    const adapter = this.app.vault.adapter;
    let data: Record<string, unknown> = {};
    try {
      if (await adapter.exists(LlmWikiSettingTab.SECRETS_PATH)) {
        const parsed = JSON.parse(await adapter.read(LlmWikiSettingTab.SECRETS_PATH));
        if (parsed && typeof parsed === "object") data = parsed as Record<string, unknown>;
      }
    } catch {
      data = {}; // JSON corrotto: riparte da oggetto vuoto (sovrascrive)
    }
    if (value) data.TAVILY_API_KEY = value;
    else delete data.TAVILY_API_KEY; // campo svuotato → rimuove la chiave
    if (!(await adapter.exists(LlmWikiSettingTab.SECRETS_DIR))) {
      await adapter.mkdir(LlmWikiSettingTab.SECRETS_DIR);
    }
    await adapter.write(LlmWikiSettingTab.SECRETS_PATH, JSON.stringify(data, null, 2) + "\n");
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

    new Setting(containerEl)
      .setName("Mostra i comandi eseguiti")
      .setDesc("Visualizza le righe dei tool eseguiti dall'agente (bash, read, …) nello stream. Off = log più pulito.")
      .addToggle((t) =>
        t.setValue(this.plugin.settings.showToolCalls).onChange(async (v) => {
          this.plugin.settings.showToolCalls = v;
          await this.plugin.saveSettings();
        })
      );

    // Tavily API key — proxy verso .llm-wiki/secrets.json (vedi helper sopra).
    // Persistita su `blur` per evitare scritture/JSON corrotti per-keystroke.
    new Setting(containerEl)
      .setName("Tavily API key")
      .setDesc(
        "Per deep-research (fallback automatico a DuckDuckGo se vuota). Salvata in " +
          ".llm-wiki/secrets.json (non committato). La env var TAVILY_API_KEY, se presente, ha la precedenza."
      )
      .addText((t) => {
        t.setPlaceholder("tvly-…");
        t.inputEl.type = "password";
        void (async () => {
          t.setValue(await this.readTavilyKey());
        })();
        t.inputEl.addEventListener("blur", () => {
          void (async () => {
            await this.writeTavilyKey(t.getValue().trim());
            new Notice("Tavily API key salvata in .llm-wiki/secrets.json");
          })();
        });
        return t;
      });

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

    // ── Schedulazione lint ──────────────────────────────────────────────────
    new Setting(containerEl).setName("Schedulazione lint").setHeading();

    new Setting(containerEl)
      .setName("Lint automatico")
      .setDesc(
        "Esegui periodicamente wiki-lint in background (senza --fix) e salva il " +
          "report in wiki/lint-report.md."
      )
      .addToggle((t) =>
        t.setValue(this.plugin.settings.lintScheduleEnabled).onChange(async (v) => {
          this.plugin.settings.lintScheduleEnabled = v;
          await this.plugin.saveSettings();
          this.plugin.setupLintSchedule();
        })
      );

    new Setting(containerEl)
      .setName("Intervallo (minuti)")
      .setDesc("Minimo 5. Default 1440 (giornaliero).")
      .addText((t) =>
        t
          .setValue(String(this.plugin.settings.lintIntervalMinutes))
          .onChange(async (v) => {
            const n = parseInt(v, 10);
            if (!Number.isNaN(n) && n > 0) {
              this.plugin.settings.lintIntervalMinutes = n;
              await this.plugin.saveSettings();
              this.plugin.setupLintSchedule();
            }
          })
      );
  }
}
