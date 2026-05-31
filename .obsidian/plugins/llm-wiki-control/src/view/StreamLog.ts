import { StreamEvent } from "../runner/events";

// Componente riusabile: render incrementale degli eventi del runner + bottone Stop.
export class StreamLog {
  private container: HTMLElement;
  private logEl: HTMLElement;
  private statusEl: HTMLElement;
  private stopBtn: HTMLButtonElement;
  private showThinking: boolean;
  private abortController: AbortController | null = null;
  private currentTextEl: HTMLElement | null = null;

  constructor(parent: HTMLElement, showThinking: boolean) {
    this.showThinking = showThinking;
    this.container = parent.createDiv({ cls: "llm-wiki-stream" });

    const header = this.container.createDiv({ cls: "llm-wiki-stream-header" });
    this.statusEl = header.createSpan({ cls: "llm-wiki-stream-status", text: "Pronto" });
    this.stopBtn = header.createEl("button", { text: "Stop", cls: "mod-warning" });
    this.stopBtn.disabled = true;
    this.stopBtn.onclick = () => this.abort();

    this.logEl = this.container.createDiv({ cls: "llm-wiki-stream-log" });
  }

  setShowThinking(value: boolean): void {
    this.showThinking = value;
  }

  // Crea un nuovo AbortController per il run corrente e abilita lo Stop.
  beginRun(): AbortSignal {
    this.abortController = new AbortController();
    this.stopBtn.disabled = false;
    this.statusEl.setText("In esecuzione…");
    this.currentTextEl = null;
    return this.abortController.signal;
  }

  endRun(code: number | null): void {
    this.stopBtn.disabled = true;
    this.abortController = null;
    this.currentTextEl = null;
    this.statusEl.setText(code === 0 || code == null ? "Completato" : `Uscito (code ${code})`);
  }

  abort(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.statusEl.setText("Interrotto");
    }
  }

  clear(): void {
    this.logEl.empty();
    this.currentTextEl = null;
    this.statusEl.setText("Pronto");
  }

  // Render di un singolo evento in arrivo.
  append(ev: StreamEvent): void {
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
        if (!this.showThinking) break;
        const d = this.logEl.createEl("details", { cls: "llm-wiki-ev-thinking" });
        d.createEl("summary", { text: "thinking" });
        d.createDiv({ text: ev.text });
        break;
      }
      case "toolCall": {
        this.currentTextEl = null;
        const row = this.logEl.createDiv({ cls: "llm-wiki-ev-tool" });
        row.createSpan({ cls: "llm-wiki-tool-name", text: `⚙ ${ev.name}` });
        if (ev.detail) row.createSpan({ cls: "llm-wiki-tool-detail", text: ev.detail });
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
        // gestito da endRun()
        break;
      }
      case "session": {
        // id catturato dal QueryPanel; nessun render.
        break;
      }
    }
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  // Render statico di eventi storici (resume di una sessione).
  renderHistory(events: StreamEvent[]): void {
    this.clear();
    for (const ev of events) this.append(ev);
    this.statusEl.setText("Sessione caricata");
  }
}
