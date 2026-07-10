import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, AskResponse } from '../api';

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
  examples = ['How are charges shared?', 'What is the maximum remittance length?', 'Is SCT Inst available 24/7?'];

  ask() {
    const question = this.q.trim();
    if (!question) return;
    this.loading.set(true);
    this.error.set('');
    this.result.set(null);
    this.api.ask(question).subscribe({
      next: r => { this.result.set(r); this.loading.set(false); },
      error: e => { this.error.set(e?.message ?? 'Request failed'); this.loading.set(false); },
    });
  }

  pick(e: string) { this.q = e; this.ask(); }
}
