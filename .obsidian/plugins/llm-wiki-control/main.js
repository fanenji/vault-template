"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/main.ts
var main_exports = {};
__export(main_exports, {
  default: () => LlmWikiControlPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian7 = require("obsidian");

// src/settings.ts
var import_obsidian = require("obsidian");
var DEFAULT_SETTINGS = {
  piPath: "pi",
  provider: "",
  model: "",
  defaultIngestDir: "_inbox/clippings",
  showThinking: false,
  showToolCalls: false,
  lintScheduleEnabled: false,
  lintIntervalMinutes: 1440
};
var _LlmWikiSettingTab = class _LlmWikiSettingTab extends import_obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.models = [];
    this.plugin = plugin;
  }
  async readTavilyKey() {
    try {
      const adapter = this.app.vault.adapter;
      if (!await adapter.exists(_LlmWikiSettingTab.SECRETS_PATH))
        return "";
      const data = JSON.parse(await adapter.read(_LlmWikiSettingTab.SECRETS_PATH));
      const k = data?.TAVILY_API_KEY;
      return typeof k === "string" ? k : "";
    } catch {
      return "";
    }
  }
  async writeTavilyKey(value) {
    const adapter = this.app.vault.adapter;
    let data = {};
    try {
      if (await adapter.exists(_LlmWikiSettingTab.SECRETS_PATH)) {
        const parsed = JSON.parse(await adapter.read(_LlmWikiSettingTab.SECRETS_PATH));
        if (parsed && typeof parsed === "object")
          data = parsed;
      }
    } catch {
      data = {};
    }
    if (value)
      data.TAVILY_API_KEY = value;
    else
      delete data.TAVILY_API_KEY;
    if (!await adapter.exists(_LlmWikiSettingTab.SECRETS_DIR)) {
      await adapter.mkdir(_LlmWikiSettingTab.SECRETS_DIR);
    }
    await adapter.write(_LlmWikiSettingTab.SECRETS_PATH, JSON.stringify(data, null, 2) + "\n");
  }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "LLM Wiki Control" });
    new import_obsidian.Setting(containerEl).setName("Percorso di pi").setDesc("Comando o path assoluto del binario pi (es. /opt/homebrew/bin/pi).").addText(
      (t) => t.setPlaceholder("pi").setValue(this.plugin.settings.piPath).onChange(async (v) => {
        this.plugin.settings.piPath = v.trim();
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("Cartella ingest predefinita").setDesc("Percorso relativo nella vault usato dal pannello Ingest.").addText(
      (t) => t.setPlaceholder("_inbox/clippings").setValue(this.plugin.settings.defaultIngestDir).onChange(async (v) => {
        this.plugin.settings.defaultIngestDir = v.trim();
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("Mostra il thinking").setDesc("Visualizza i blocchi di ragionamento dell'agente nello stream.").addToggle(
      (t) => t.setValue(this.plugin.settings.showThinking).onChange(async (v) => {
        this.plugin.settings.showThinking = v;
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("Mostra i comandi eseguiti").setDesc("Visualizza le righe dei tool eseguiti dall'agente (bash, read, \u2026) nello stream. Off = log pi\xF9 pulito.").addToggle(
      (t) => t.setValue(this.plugin.settings.showToolCalls).onChange(async (v) => {
        this.plugin.settings.showToolCalls = v;
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("Tavily API key").setDesc(
      "Per deep-research (fallback automatico a DuckDuckGo se vuota). Salvata in .llm-wiki/secrets.json (non committato). La env var TAVILY_API_KEY, se presente, ha la precedenza."
    ).addText((t) => {
      t.setPlaceholder("tvly-\u2026");
      t.inputEl.type = "password";
      void (async () => {
        t.setValue(await this.readTavilyKey());
      })();
      t.inputEl.addEventListener("blur", () => {
        void (async () => {
          await this.writeTavilyKey(t.getValue().trim());
          new import_obsidian.Notice("Tavily API key salvata in .llm-wiki/secrets.json");
        })();
      });
      return t;
    });
    const providerSetting = new import_obsidian.Setting(containerEl).setName("Provider").setDesc("Lasciare vuoto per il default di pi.").addText(
      (t) => t.setValue(this.plugin.settings.provider).onChange(async (v) => {
        this.plugin.settings.provider = v.trim();
        await this.plugin.saveSettings();
      })
    );
    const modelSetting = new import_obsidian.Setting(containerEl).setName("Model").setDesc("Lasciare vuoto per il default di pi.");
    const renderModelControl = () => {
      modelSetting.controlEl.empty();
      if (this.models.length > 0) {
        modelSetting.addDropdown((d) => {
          d.addOption("", "(default)");
          for (const m of this.models)
            d.addOption(m, m);
          d.setValue(this.plugin.settings.model);
          d.onChange(async (v) => {
            this.plugin.settings.model = v;
            await this.plugin.saveSettings();
          });
        });
      } else {
        modelSetting.addText(
          (t) => t.setValue(this.plugin.settings.model).onChange(async (v) => {
            this.plugin.settings.model = v.trim();
            await this.plugin.saveSettings();
          })
        );
      }
    };
    renderModelControl();
    new import_obsidian.Setting(containerEl).setName("Modelli disponibili").setDesc("Popola il menu Model eseguendo `pi --list-models`.").addButton(
      (b) => b.setButtonText("Ricarica modelli").onClick(async () => {
        b.setDisabled(true).setButtonText("Carico\u2026");
        try {
          this.models = await this.plugin.runner.listModels();
          new import_obsidian.Notice(`Trovati ${this.models.length} modelli`);
          renderModelControl();
        } catch (e) {
          new import_obsidian.Notice(`Errore list-models: ${String(e)}`);
        } finally {
          b.setDisabled(false).setButtonText("Ricarica modelli");
        }
      })
    );
    new import_obsidian.Setting(containerEl).setName("Schedulazione lint").setHeading();
    new import_obsidian.Setting(containerEl).setName("Lint automatico").setDesc(
      "Esegui periodicamente wiki-lint in background (senza --fix) e salva il report in wiki/lint-report.md."
    ).addToggle(
      (t) => t.setValue(this.plugin.settings.lintScheduleEnabled).onChange(async (v) => {
        this.plugin.settings.lintScheduleEnabled = v;
        await this.plugin.saveSettings();
        this.plugin.setupLintSchedule();
      })
    );
    new import_obsidian.Setting(containerEl).setName("Intervallo (minuti)").setDesc("Minimo 5. Default 1440 (giornaliero).").addText(
      (t) => t.setValue(String(this.plugin.settings.lintIntervalMinutes)).onChange(async (v) => {
        const n = parseInt(v, 10);
        if (!Number.isNaN(n) && n > 0) {
          this.plugin.settings.lintIntervalMinutes = n;
          await this.plugin.saveSettings();
          this.plugin.setupLintSchedule();
        }
      })
    );
  }
};
// ── TAVILY_API_KEY: proxy verso .llm-wiki/secrets.json ──────────────────────
// La source of truth è il file (letto da deep-research/web_search.py): NON
// salviamo il segreto nei dati del plugin. Accesso via vault adapter (path
// relativi alla vault root, dotfolder inclusi).
_LlmWikiSettingTab.SECRETS_DIR = ".llm-wiki";
_LlmWikiSettingTab.SECRETS_PATH = ".llm-wiki/secrets.json";
var LlmWikiSettingTab = _LlmWikiSettingTab;

// src/runner/piRunner.ts
var import_child_process = require("child_process");
var readline = __toESM(require("readline"));
var path = __toESM(require("path"));

// src/runner/events.ts
function stringifyDetail(value) {
  if (value == null)
    return void 0;
  if (typeof value === "string")
    return value;
  try {
    const s = JSON.stringify(value);
    return s.length > 200 ? s.slice(0, 197) + "\u2026" : s;
  } catch {
    return void 0;
  }
}
function partsToEvents(content) {
  const out = [];
  for (const part of content) {
    const ptype = part?.type;
    if (ptype === "text" && typeof part.text === "string") {
      out.push({ kind: "text", text: part.text });
    } else if (ptype === "thinking" && typeof part.thinking === "string") {
      out.push({ kind: "thinking", text: part.thinking });
    } else if (ptype === "toolCall" || ptype === "tool_use" || ptype === "tool_call") {
      out.push({
        kind: "toolCall",
        name: part.name ?? "tool",
        detail: stringifyDetail(part.arguments ?? part.input)
      });
    }
  }
  return out;
}
function normalizeRawEvent(raw) {
  if (raw == null || typeof raw !== "object")
    return [];
  const e = raw;
  const out = [];
  if (typeof e.error === "string" && e.error.length > 0) {
    out.push({ kind: "error", message: e.error });
  }
  switch (e.type) {
    case "session": {
      if (typeof e.id === "string" && e.id.length > 0) {
        out.push({ kind: "session", id: e.id });
      }
      break;
    }
    case "message": {
      const content = e.message?.content;
      if (Array.isArray(content))
        out.push(...partsToEvents(content));
      break;
    }
    case "message_update": {
      const ame = e.assistantMessageEvent;
      if (ame?.type === "text_delta" && typeof ame.delta === "string") {
        out.push({ kind: "text", text: ame.delta });
      } else if (ame?.type === "thinking_end" && typeof ame.content === "string") {
        out.push({ kind: "thinking", text: ame.content });
      }
      break;
    }
    case "tool_execution_start": {
      if (typeof e.toolName === "string") {
        out.push({ kind: "toolCall", name: e.toolName, detail: stringifyDetail(e.args) });
      }
      break;
    }
  }
  return out;
}

// src/runner/piRunner.ts
function buildEnv() {
  const extra = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"];
  const current = process.env.PATH ?? "";
  const merged = [current, ...extra].filter(Boolean).join(path.delimiter);
  return { ...process.env, PATH: merged };
}
var PiRunner = class {
  constructor(vaultRoot, settings) {
    this.vaultRoot = vaultRoot;
    this.settings = settings;
  }
  updateSettings(settings) {
    this.settings = settings;
  }
  skillPath(skill) {
    return path.join(this.vaultRoot, ".claude", "skills", skill);
  }
  buildArgs(opts) {
    const args = ["-p", "--mode", "json"];
    if (opts.sessionId) {
      args.push("--session", opts.sessionId);
    } else if (opts.continueLast) {
      args.push("--continue");
    }
    if (this.settings.provider)
      args.push("--provider", this.settings.provider);
    if (this.settings.model)
      args.push("--model", this.settings.model);
    args.push("--skill", this.skillPath(opts.skill));
    args.push(opts.prompt);
    return args;
  }
  // Lancia una skill in headless e inoltra gli eventi normalizzati via onEvent.
  // Risolve quando il processo termina (qualsiasi exit code).
  runSkill(opts) {
    const args = this.buildArgs(opts);
    const piPath = this.settings.piPath || "pi";
    return new Promise((resolve) => {
      let child;
      try {
        child = (0, import_child_process.spawn)(piPath, args, {
          cwd: this.vaultRoot,
          env: buildEnv()
        });
      } catch (err) {
        opts.onEvent({
          kind: "error",
          message: `Impossibile lanciare "${piPath}": ${String(err)}`
        });
        opts.onEvent({ kind: "exit", code: 1 });
        resolve(1);
        return;
      }
      child.stdin.end();
      const onAbort = () => child.kill("SIGTERM");
      if (opts.signal) {
        if (opts.signal.aborted)
          onAbort();
        else
          opts.signal.addEventListener("abort", onAbort, { once: true });
      }
      const rl = readline.createInterface({ input: child.stdout });
      rl.on("line", (line) => {
        const trimmed = line.trim();
        if (!trimmed)
          return;
        let parsed;
        try {
          parsed = JSON.parse(trimmed);
        } catch {
          opts.onEvent({ kind: "text", text: trimmed });
          return;
        }
        for (const ev of normalizeRawEvent(parsed))
          opts.onEvent(ev);
      });
      let stderrBuf = "";
      child.stderr.on("data", (d) => {
        stderrBuf += d.toString();
      });
      child.on("error", (err) => {
        opts.onEvent({
          kind: "error",
          message: `Errore di processo: ${err.message}`
        });
      });
      child.on("close", (code) => {
        rl.close();
        if (opts.signal)
          opts.signal.removeEventListener("abort", onAbort);
        if (code !== 0 && stderrBuf.trim()) {
          opts.onEvent({ kind: "error", message: stderrBuf.trim() });
        }
        opts.onEvent({ kind: "exit", code });
        resolve(code);
      });
    });
  }
  // Esegue `pi --list-models` una tantum e ritorna le righe non vuote.
  listModels() {
    const piPath = this.settings.piPath || "pi";
    return new Promise((resolve, reject) => {
      let out = "";
      let err = "";
      let child;
      try {
        child = (0, import_child_process.spawn)(piPath, ["--list-models"], { env: buildEnv() });
      } catch (e) {
        reject(e);
        return;
      }
      child.stdin.end();
      child.stdout.on("data", (d) => out += d.toString());
      child.stderr.on("data", (d) => err += d.toString());
      child.on("error", reject);
      child.on("close", (code) => {
        if (code !== 0) {
          reject(new Error(err.trim() || `pi --list-models exit ${code}`));
          return;
        }
        const lines = out.split("\n").map((l) => l.trim()).filter((l) => l.length > 0);
        resolve(lines);
      });
    });
  }
};

// src/sessions/sessionStore.ts
var fs = __toESM(require("fs"));
var path2 = __toESM(require("path"));
var os = __toESM(require("os"));
var readline2 = __toESM(require("readline"));
var MARKER_RE = /\[llm-wiki:([a-z-]+)\]/i;
function extractSkillHint(text) {
  const m = text.match(MARKER_RE);
  return m ? m[1].toLowerCase() : null;
}
function stripMarker(text) {
  return text.replace(MARKER_RE, "").trim();
}
var SessionStore = class {
  constructor(vaultRoot) {
    this.vaultRoot = vaultRoot;
    this.baseDir = path2.join(os.homedir(), ".pi", "agent", "sessions");
  }
  // Legge solo la prima riga di un file (riga "session" con cwd/id/timestamp).
  readFirstLine(file) {
    try {
      const fd = fs.openSync(file, "r");
      try {
        const buf = Buffer.alloc(8192);
        const bytes = fs.readSync(fd, buf, 0, buf.length, 0);
        const chunk = buf.toString("utf8", 0, bytes);
        const nl = chunk.indexOf("\n");
        return nl === -1 ? chunk : chunk.slice(0, nl);
      } finally {
        fs.closeSync(fd);
      }
    } catch {
      return null;
    }
  }
  // Trova tutti i .jsonl la cui prima riga ha cwd === vaultRoot, in QUALSIASI
  // sottocartella. Cosi' evitiamo di reverse-engineerare la sanitizzazione del
  // path che fa pi: ci basiamo sul campo `cwd` reale dentro il file.
  collectSessionFiles() {
    const result = [];
    let dirs;
    try {
      dirs = fs.readdirSync(this.baseDir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => path2.join(this.baseDir, d.name));
    } catch {
      return result;
    }
    for (const dir of dirs) {
      let files;
      try {
        files = fs.readdirSync(dir).filter((f) => f.endsWith(".jsonl"));
      } catch {
        continue;
      }
      for (const f of files) {
        const full = path2.join(dir, f);
        const first = this.readFirstLine(full);
        if (!first)
          continue;
        try {
          const obj = JSON.parse(first);
          if (obj && obj.cwd === this.vaultRoot)
            result.push(full);
        } catch {
        }
      }
    }
    return result;
  }
  // Ricava il primo messaggio user (content[0].text) leggendo il file riga per
  // riga finche' non lo trova.
  async firstUserText(file) {
    return new Promise((resolve) => {
      let found = "";
      const stream = fs.createReadStream(file, { encoding: "utf8" });
      const rl = readline2.createInterface({ input: stream });
      rl.on("line", (line) => {
        if (found)
          return;
        const t = line.trim();
        if (!t)
          return;
        try {
          const obj = JSON.parse(t);
          if (obj?.type === "message" && obj?.message?.role === "user") {
            const c = obj.message?.content;
            if (Array.isArray(c) && typeof c[0]?.text === "string") {
              found = c[0].text;
              rl.close();
            }
          }
        } catch {
        }
      });
      rl.on("close", () => resolve(found));
      rl.on("error", () => resolve(found));
    });
  }
  // Estrae id e timestamp dalla prima riga / dal nome file.
  parseHeader(file) {
    const first = this.readFirstLine(file);
    let id = "";
    let createdAt = 0;
    if (first) {
      try {
        const obj = JSON.parse(first);
        if (typeof obj?.id === "string")
          id = obj.id;
        if (typeof obj?.timestamp === "string") {
          const t = Date.parse(obj.timestamp);
          if (!Number.isNaN(t))
            createdAt = t;
        }
      } catch {
      }
    }
    if (!createdAt) {
      try {
        createdAt = fs.statSync(file).mtimeMs;
      } catch {
        createdAt = Date.now();
      }
    }
    if (!id)
      id = path2.basename(file, ".jsonl");
    return { id, createdAt };
  }
  // Elenca le sessioni della vault corrente, piu' recenti per prime.
  // skillFilter: se passato, tiene solo le sessioni col marker skill corrispondente.
  async listSessions(skillFilter) {
    const files = this.collectSessionFiles();
    const metas = [];
    for (const file of files) {
      const { id, createdAt } = this.parseHeader(file);
      const firstUserText = await this.firstUserText(file);
      const skillHint = extractSkillHint(firstUserText);
      if (skillFilter && skillHint !== skillFilter)
        continue;
      metas.push({ id, file, createdAt, firstUserText, skillHint });
    }
    metas.sort((a, b) => b.createdAt - a.createdAt);
    return metas;
  }
  // Ricarica gli eventi di una sessione per il re-render nello StreamLog.
  async loadSession(file) {
    return new Promise((resolve) => {
      const events = [];
      const stream = fs.createReadStream(file, { encoding: "utf8" });
      const rl = readline2.createInterface({ input: stream });
      rl.on("line", (line) => {
        const t = line.trim();
        if (!t)
          return;
        try {
          const obj = JSON.parse(t);
          if (obj?.type === "message") {
            for (const ev of normalizeRawEvent(obj))
              events.push(ev);
          }
        } catch {
        }
      });
      rl.on("close", () => resolve(events));
      rl.on("error", () => resolve(events));
    });
  }
};

// src/view/ControlView.ts
var import_obsidian6 = require("obsidian");

// src/view/IngestPanel.ts
var import_obsidian2 = require("obsidian");

// src/view/StreamLog.ts
var StreamLog = class {
  constructor(parent, showThinking, showToolCalls = false) {
    this.abortController = null;
    this.currentTextEl = null;
    this.showThinking = showThinking;
    this.showToolCalls = showToolCalls;
    this.container = parent.createDiv({ cls: "llm-wiki-stream" });
    const header = this.container.createDiv({ cls: "llm-wiki-stream-header" });
    this.statusEl = header.createSpan({ cls: "llm-wiki-stream-status", text: "Pronto" });
    this.stopBtn = header.createEl("button", { text: "Stop", cls: "mod-warning" });
    this.stopBtn.disabled = true;
    this.stopBtn.onclick = () => this.abort();
    this.logEl = this.container.createDiv({ cls: "llm-wiki-stream-log" });
  }
  setShowThinking(value) {
    this.showThinking = value;
  }
  setShowToolCalls(value) {
    this.showToolCalls = value;
  }
  // Crea un nuovo AbortController per il run corrente e abilita lo Stop.
  beginRun() {
    this.abortController = new AbortController();
    this.stopBtn.disabled = false;
    this.statusEl.setText("In esecuzione\u2026");
    this.currentTextEl = null;
    return this.abortController.signal;
  }
  endRun(code) {
    this.stopBtn.disabled = true;
    this.abortController = null;
    this.currentTextEl = null;
    this.statusEl.setText(code === 0 || code == null ? "Completato" : `Uscito (code ${code})`);
  }
  abort() {
    if (this.abortController) {
      this.abortController.abort();
      this.statusEl.setText("Interrotto");
    }
  }
  clear() {
    this.logEl.empty();
    this.currentTextEl = null;
    this.statusEl.setText("Pronto");
  }
  // Render di un singolo evento in arrivo.
  append(ev) {
    switch (ev.kind) {
      case "text": {
        if (!this.currentTextEl) {
          this.currentTextEl = this.logEl.createDiv({ cls: "llm-wiki-ev-text" });
        }
        this.currentTextEl.appendText(ev.text);
        break;
      }
      case "thinking": {
        this.currentTextEl = null;
        if (!this.showThinking)
          break;
        const d = this.logEl.createEl("details", { cls: "llm-wiki-ev-thinking" });
        d.createEl("summary", { text: "thinking" });
        d.createDiv({ text: ev.text });
        break;
      }
      case "toolCall": {
        this.currentTextEl = null;
        if (!this.showToolCalls)
          break;
        const row = this.logEl.createDiv({ cls: "llm-wiki-ev-tool" });
        row.createSpan({ cls: "llm-wiki-tool-name", text: `\u2699 ${ev.name}` });
        if (ev.detail)
          row.createSpan({ cls: "llm-wiki-tool-detail", text: ev.detail });
        break;
      }
      case "result": {
        this.currentTextEl = null;
        if (ev.text) {
          this.logEl.createDiv({ cls: "llm-wiki-ev-result", text: ev.text });
        }
        break;
      }
      case "error": {
        this.currentTextEl = null;
        this.logEl.createDiv({ cls: "llm-wiki-ev-error", text: ev.message });
        break;
      }
      case "exit": {
        break;
      }
      case "session": {
        break;
      }
    }
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }
  // Render statico di eventi storici (resume di una sessione).
  renderHistory(events) {
    this.clear();
    for (const ev of events)
      this.append(ev);
    this.statusEl.setText("Sessione caricata");
  }
};

// src/view/IngestPanel.ts
var BATCH_WARN_THRESHOLD = 5;
var IngestPanel = class {
  constructor(parent, app, runner, getSettings) {
    this.running = false;
    this.app = app;
    this.runner = runner;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }
  // Elenca i file della cartella ingest configurata (default _inbox/clippings).
  listIngestFiles() {
    const dir = this.getSettings().defaultIngestDir.replace(/\/+$/, "");
    return this.app.vault.getFiles().filter((f) => f.path === dir || f.path.startsWith(dir + "/")).sort((a, b) => a.path.localeCompare(b.path));
  }
  build() {
    this.root.createEl("p", {
      cls: "llm-wiki-hint",
      text: "Seleziona un file o l'intera cartella da ingerire nella wiki."
    });
    const controls = this.root.createDiv({ cls: "llm-wiki-controls" });
    this.select = controls.createEl("select", { cls: "dropdown" });
    this.refreshFileList();
    const refreshBtn = controls.createEl("button", { text: "\u21BB" });
    refreshBtn.onclick = () => this.refreshFileList();
    const runBtn = controls.createEl("button", { text: "Ingerisci", cls: "mod-cta" });
    runBtn.onclick = () => this.run();
    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);
  }
  refreshFileList() {
    const files = this.listIngestFiles();
    this.select.empty();
    const dir = this.getSettings().defaultIngestDir;
    const allOpt = this.select.createEl("option", {
      text: `\u25B8 Tutta la cartella (${files.length} file)`,
      value: "__all__"
    });
    for (const f of files) {
      this.select.createEl("option", { text: f.path, value: f.path });
    }
  }
  async run() {
    if (this.running) {
      new import_obsidian2.Notice("Ingest gia' in corso");
      return;
    }
    const dir = this.getSettings().defaultIngestDir;
    const value = this.select.value;
    const files = this.listIngestFiles();
    let target;
    let count;
    if (value === "__all__") {
      if (files.length === 0) {
        new import_obsidian2.Notice(`Nessun file in ${dir}`);
        return;
      }
      target = dir;
      count = files.length;
    } else {
      target = value;
      count = 1;
    }
    if (count > BATCH_WARN_THRESHOLD) {
      const ok = window.confirm(
        `Stai per ingerire ${count} file. L'operazione consuma token in modo proporzionale al numero/dimensione dei documenti. Procedere?`
      );
      if (!ok)
        return;
    }
    const prompt = `[llm-wiki:ingest] Ingerisci ${target} nella wiki.`;
    this.running = true;
    this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);
    const code = await this.runner.runSkill({
      skill: "wiki-ingest",
      prompt,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit")
          this.log.endRun(ev.code);
        else
          this.log.append(ev);
      }
    });
    this.log.endRun(code);
    this.running = false;
  }
};

// src/view/QueryPanel.ts
var import_obsidian3 = require("obsidian");
var QueryPanel = class {
  constructor(parent, app, runner, store, getSettings) {
    this.running = false;
    // Sessione corrente per i follow-up (resume via --session).
    this.activeSessionId = null;
    this.app = app;
    this.runner = runner;
    this.store = store;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }
  build() {
    this.textarea = this.root.createEl("textarea", {
      cls: "llm-wiki-query-input",
      attr: { rows: "3", placeholder: "Cosa vuoi cercare nella wiki?" }
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
      new import_obsidian3.Notice("Nuova conversazione");
    };
    const saveRow = this.root.createDiv({ cls: "llm-wiki-save-row" });
    const saveLabel = saveRow.createEl("label", { cls: "llm-wiki-save-label" });
    this.saveCheckbox = saveLabel.createEl("input", { attr: { type: "checkbox" } });
    saveLabel.createSpan({ text: " Salva la risposta in wiki/queries/" });
    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);
    this.root.createEl("h4", { text: "Storico query" });
    this.historyEl = this.root.createDiv({ cls: "llm-wiki-history" });
    void this.refreshHistory();
  }
  async refreshHistory() {
    this.historyEl.empty();
    let sessions = [];
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
  async resume(s) {
    this.activeSessionId = s.id;
    try {
      const events = await this.store.loadSession(s.file);
      this.log.setShowThinking(this.getSettings().showThinking);
      this.log.setShowToolCalls(this.getSettings().showToolCalls);
      this.log.renderHistory(events);
      new import_obsidian3.Notice("Sessione caricata \u2014 usa Follow-up per continuare");
    } catch (e) {
      new import_obsidian3.Notice(`Errore caricamento sessione: ${String(e)}`);
    }
  }
  async run(asFollowUp) {
    if (this.running) {
      new import_obsidian3.Notice("Query gia' in corso");
      return;
    }
    const text = this.textarea.value.trim();
    if (!text) {
      new import_obsidian3.Notice("Scrivi una domanda");
      return;
    }
    const useSession = asFollowUp ? this.activeSessionId ?? void 0 : void 0;
    if (asFollowUp && !useSession) {
      new import_obsidian3.Notice("Nessuna sessione attiva: usa 'Cerca' per iniziarne una");
      return;
    }
    const saveSuffix = this.saveCheckbox.checked ? " Salva la risposta come pagina in wiki/queries/ (step 4 della skill) e aggiorna l'indice QMD." : "";
    const prompt = `[llm-wiki:query] ${text}${saveSuffix}`;
    this.running = true;
    if (!asFollowUp)
      this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);
    const code = await this.runner.runSkill({
      skill: "wiki-query",
      prompt,
      sessionId: useSession,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit")
          this.log.endRun(ev.code);
        else if (ev.kind === "session")
          this.activeSessionId = ev.id;
        else
          this.log.append(ev);
      }
    });
    this.log.endRun(code);
    this.running = false;
    this.textarea.value = "";
    setTimeout(() => void this.refreshHistory(), 500);
  }
};

// src/view/ResearchPanel.ts
var import_obsidian4 = require("obsidian");
var ResearchPanel = class {
  constructor(parent, app, runner, store, getSettings) {
    this.running = false;
    // Sessione corrente per i follow-up (resume via --session).
    this.activeSessionId = null;
    this.app = app;
    this.runner = runner;
    this.store = store;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }
  build() {
    this.textarea = this.root.createEl("textarea", {
      cls: "llm-wiki-query-input",
      attr: { rows: "3", placeholder: "Argomento da ricercare sul web\u2026" }
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
      new import_obsidian4.Notice("Nuova ricerca");
    };
    const aiRow = this.root.createDiv({ cls: "llm-wiki-save-row" });
    const aiLabel = aiRow.createEl("label", { cls: "llm-wiki-save-label" });
    this.autoIngestCheckbox = aiLabel.createEl("input", { attr: { type: "checkbox" } });
    aiLabel.createSpan({ text: " Auto-ingest (scomponi in pagine entity/concept)" });
    this.log = new StreamLog(this.root, this.getSettings().showThinking, this.getSettings().showToolCalls);
    this.root.createEl("h4", { text: "Storico ricerche" });
    this.historyEl = this.root.createDiv({ cls: "llm-wiki-history" });
    void this.refreshHistory();
  }
  async refreshHistory() {
    this.historyEl.empty();
    let sessions = [];
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
  async resume(s) {
    this.activeSessionId = s.id;
    try {
      const events = await this.store.loadSession(s.file);
      this.log.setShowThinking(this.getSettings().showThinking);
      this.log.setShowToolCalls(this.getSettings().showToolCalls);
      this.log.renderHistory(events);
      new import_obsidian4.Notice("Ricerca caricata \u2014 usa Follow-up per continuare");
    } catch (e) {
      new import_obsidian4.Notice(`Errore caricamento sessione: ${String(e)}`);
    }
  }
  async run(asFollowUp) {
    if (this.running) {
      new import_obsidian4.Notice("Ricerca gia' in corso");
      return;
    }
    const text = this.textarea.value.trim();
    if (!text) {
      new import_obsidian4.Notice("Scrivi un argomento");
      return;
    }
    const useSession = asFollowUp ? this.activeSessionId ?? void 0 : void 0;
    if (asFollowUp && !useSession) {
      new import_obsidian4.Notice("Nessuna sessione attiva: usa 'Ricerca' per iniziarne una");
      return;
    }
    const ingestSuffix = this.autoIngestCheckbox.checked ? " Esegui anche lo Step 8 (auto-ingest): invoca wiki-ingest sulla pagina di ricerca salvata per scomporla in pagine entity/concept collegate." : " Non eseguire l'auto-ingest (Step 8): salva solo la pagina di ricerca.";
    const prompt = `[llm-wiki:research] ${text}${ingestSuffix}`;
    this.running = true;
    if (!asFollowUp)
      this.log.clear();
    const signal = this.log.beginRun();
    this.log.setShowThinking(this.getSettings().showThinking);
    this.log.setShowToolCalls(this.getSettings().showToolCalls);
    const code = await this.runner.runSkill({
      skill: "deep-research",
      prompt,
      sessionId: useSession,
      signal,
      onEvent: (ev) => {
        if (ev.kind === "exit")
          this.log.endRun(ev.code);
        else if (ev.kind === "session")
          this.activeSessionId = ev.id;
        else
          this.log.append(ev);
      }
    });
    this.log.endRun(code);
    this.running = false;
    this.textarea.value = "";
    setTimeout(() => void this.refreshHistory(), 500);
  }
};

// src/view/LintPanel.ts
var import_obsidian5 = require("obsidian");
var LintPanel = class {
  constructor(parent, runner, getSettings) {
    this.running = false;
    this.runner = runner;
    this.getSettings = getSettings;
    this.root = parent.createDiv({ cls: "llm-wiki-panel" });
    this.build();
  }
  build() {
    this.root.createEl("p", {
      cls: "llm-wiki-hint",
      text: "Audit della wiki: link rotti, pagine orfane, frontmatter, e problemi semantici (contraddizioni, stale, missing-page)."
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
  async run() {
    if (this.running) {
      new import_obsidian5.Notice("Audit gia' in corso");
      return;
    }
    const fix = this.fixCheckbox.checked;
    const prompt = "[llm-wiki:lint] Esegui un audit completo della wiki con la skill wiki-lint" + (fix ? " e applica le correzioni automatiche (--fix: frontmatter mancanti, stub missing-page)." : " (sola analisi, senza --fix).") + " Salva il report in wiki/lint-report.md.";
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
        if (ev.kind === "exit")
          this.log.endRun(ev.code);
        else if (ev.kind !== "session")
          this.log.append(ev);
      }
    });
    this.log.endRun(code);
    this.running = false;
  }
};

// src/view/ControlView.ts
var VIEW_TYPE_LLM_WIKI = "llm-wiki-control";
var ControlView = class extends import_obsidian6.ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.tabButtons = /* @__PURE__ */ new Map();
    this.panes = /* @__PURE__ */ new Map();
    this.active = "query";
    this.plugin = plugin;
  }
  getViewType() {
    return VIEW_TYPE_LLM_WIKI;
  }
  getDisplayText() {
    return "LLM Wiki";
  }
  getIcon() {
    return "brain-circuit";
  }
  async onOpen() {
    const container = this.contentEl;
    container.empty();
    container.addClass("llm-wiki-control-view");
    const tabBar = container.createDiv({ cls: "llm-wiki-tabs" });
    const body = container.createDiv({ cls: "llm-wiki-tab-body" });
    const makeTab = (id, label) => {
      const btn = tabBar.createEl("button", { text: label, cls: "llm-wiki-tab" });
      btn.onclick = () => this.selectTab(id);
      this.tabButtons.set(id, btn);
      const pane = body.createDiv({ cls: "llm-wiki-pane" });
      this.panes.set(id, pane);
      return pane;
    };
    const queryPane = makeTab("query", "Query");
    const researchPane = makeTab("research", "DeepResearch");
    const ingestPane = makeTab("ingest", "Ingest");
    const lintPane = makeTab("lint", "Lint");
    new QueryPanel(
      queryPane,
      this.app,
      this.plugin.runner,
      this.plugin.sessionStore,
      () => this.plugin.settings
    );
    new ResearchPanel(
      researchPane,
      this.app,
      this.plugin.runner,
      this.plugin.sessionStore,
      () => this.plugin.settings
    );
    new IngestPanel(ingestPane, this.app, this.plugin.runner, () => this.plugin.settings);
    new LintPanel(lintPane, this.plugin.runner, () => this.plugin.settings);
    this.selectTab(this.active);
  }
  selectTab(id) {
    this.active = id;
    for (const [tid, btn] of this.tabButtons) {
      btn.toggleClass("is-active", tid === id);
    }
    for (const [tid, pane] of this.panes) {
      pane.toggleClass("is-hidden", tid !== id);
    }
  }
  async onClose() {
    this.contentEl.empty();
  }
};

// src/main.ts
var LlmWikiControlPlugin = class extends import_obsidian7.Plugin {
  constructor() {
    super(...arguments);
    this.lintIntervalId = null;
    this.scheduledLintRunning = false;
  }
  async onload() {
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
      callback: () => void this.activateView()
    });
    this.addSettingTab(new LlmWikiSettingTab(this.app, this));
  }
  onunload() {
  }
  getVaultRoot() {
    const adapter = this.app.vault.adapter;
    if (adapter instanceof import_obsidian7.FileSystemAdapter) {
      return adapter.getBasePath();
    }
    new import_obsidian7.Notice("LLM Wiki Control richiede un vault su filesystem (desktop).");
    return "";
  }
  async activateView() {
    const { workspace } = this.app;
    let leaf = null;
    const existing = workspace.getLeavesOfType(VIEW_TYPE_LLM_WIKI);
    if (existing.length > 0) {
      leaf = existing[0];
    } else {
      leaf = workspace.getRightLeaf(false);
      if (leaf)
        await leaf.setViewState({ type: VIEW_TYPE_LLM_WIKI, active: true });
    }
    if (leaf)
      workspace.revealLeaf(leaf);
  }
  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }
  async saveSettings() {
    await this.saveData(this.settings);
    if (this.runner)
      this.runner.updateSettings(this.settings);
  }
  // (Ri)configura la schedulazione del lint in base ai settings. Chiamato a
  // onload e dai toggle/intervallo nel SettingTab.
  setupLintSchedule() {
    if (this.lintIntervalId !== null) {
      window.clearInterval(this.lintIntervalId);
      this.lintIntervalId = null;
    }
    if (!this.settings.lintScheduleEnabled)
      return;
    const minutes = Math.max(5, this.settings.lintIntervalMinutes || 1440);
    this.lintIntervalId = window.setInterval(
      () => void this.runScheduledLint(),
      minutes * 6e4
    );
    this.registerInterval(this.lintIntervalId);
  }
  // Esegue wiki-lint in background (no --fix), salva il report e notifica.
  async runScheduledLint() {
    if (this.scheduledLintRunning || !this.runner)
      return;
    this.scheduledLintRunning = true;
    new import_obsidian7.Notice("LLM Wiki: avvio lint schedulato\u2026");
    try {
      await this.runner.runSkill({
        skill: "wiki-lint",
        prompt: "[llm-wiki:lint] Esegui un audit della wiki con wiki-lint in modalit\xE0 non interattiva (senza --fix). Salva il report in wiki/lint-report.md.",
        onEvent: () => {
        }
      });
      new import_obsidian7.Notice("LLM Wiki: lint schedulato completato (wiki/lint-report.md).");
    } catch (e) {
      new import_obsidian7.Notice(`LLM Wiki: lint schedulato fallito \u2014 ${String(e)}`);
    } finally {
      this.scheduledLintRunning = false;
    }
  }
};
