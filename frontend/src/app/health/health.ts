import { Component, OnDestroy, inject, signal } from '@angular/core';
import { Api, HealthCheck } from '../api';

@Component({
  selector: 'app-health',
  templateUrl: './health.html',
})
export class Health implements OnDestroy {
  private api = inject(Api);
  checks = signal<HealthCheck[]>([]);
  checking = signal<Set<string>>(new Set());
  lastFull = signal('');
  order = ['database', 'responder', 'judge', 'embeddings', 'service'];
  labels: Record<string, string> = { database: 'Database', responder: 'Responder', judge: 'Judge', embeddings: 'Embeddings', service: 'Service' };
  kinds: Record<string, string> = { database: 'Postgres · pgvector', responder: 'Claude · Haiku', judge: 'GPT-4 · cross-model eval', embeddings: 'OpenAI · 3-small', service: 'this app' };
  icons: Record<string, string> = { database: 'ti-database', responder: 'ti-message-2', judge: 'ti-gavel', embeddings: 'ti-vector', service: 'ti-server-2' };
  private timer: ReturnType<typeof setInterval> | undefined;

  constructor() {
    this.checkAll();
    this.timer = setInterval(() => this.checkAll(), 10 * 60 * 1000); // auto every 10 min
  }
  ngOnDestroy() { clearInterval(this.timer); }

  checkAll() {
    this.order.forEach(n => this.mark(n, true));
    this.api.health().subscribe({
      next: r => { this.checks.set(r.checks); this.order.forEach(n => this.mark(n, false)); this.lastFull.set(new Date().toLocaleTimeString()); },
      error: () => this.order.forEach(n => this.mark(n, false)),
    });
  }
  checkOne(name: string) {
    this.mark(name, true);
    this.api.checkOne(name).subscribe({
      next: c => { this.checks.update(list => [...list.filter(x => x.name !== name), c]); this.mark(name, false); },
      error: () => this.mark(name, false),
    });
  }
  mark(name: string, on: boolean) {
    this.checking.update(s => { const n = new Set(s); if (on) { n.add(name); } else { n.delete(name); } return n; });
  }
  get(name: string) { return this.checks().find(c => c.name === name); }
  isChecking(name: string) { return this.checking().has(name); }
}
