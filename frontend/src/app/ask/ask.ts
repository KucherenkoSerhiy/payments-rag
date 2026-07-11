import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, AskResponse, Citation } from '../api';

interface HistEntry { q: string; result: AskResponse; }

@Component({
  selector: 'app-ask',
  imports: [FormsModule, DecimalPipe],
  templateUrl: './ask.html',
})
export class Ask {
  private api = inject(Api);
  q = 'How fast does an SCT Inst payment settle?';
  result = signal<AskResponse | null>(null);
  loading = signal(false);
  error = signal('');
  history = signal<HistEntry[]>([]);
  examples = ['How are charges shared?', 'What is the maximum remittance length?', 'Is SCT Inst available 24/7?'];

  constructor() {
    const saved = localStorage.getItem('ask-history');
    if (saved) {
      try { this.history.set(JSON.parse(saved)); } catch { /* ignore corrupt history */ }
    }
  }

  ask() {
    const question = this.q.trim();
    if (!question) return;
    this.loading.set(true);
    this.error.set('');
    this.result.set(null);
    this.api.ask(question).subscribe({
      next: r => {
        this.result.set(r);
        this.loading.set(false);
        this.history.update(h => [{ q: question, result: r }, ...h.filter(x => x.q !== question)].slice(0, 20));
        localStorage.setItem('ask-history', JSON.stringify(this.history()));
      },
      error: e => { this.error.set(e?.message ?? 'Request failed'); this.loading.set(false); },
    });
  }

  pick(e: string) { this.q = e; this.ask(); }
  show(h: HistEntry) { this.q = h.q; this.error.set(''); this.result.set(h.result); }
  clearHistory() { this.history.set([]); localStorage.removeItem('ask-history'); }
  pdfUrl(c: Citation) { return this.api.pdfUrl(c.source, c.page); }
}
