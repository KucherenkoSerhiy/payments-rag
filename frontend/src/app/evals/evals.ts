import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, AnswerEval, RetrievalEval } from '../api';

@Component({
  selector: 'app-evals',
  imports: [FormsModule, DecimalPipe],
  templateUrl: './evals.html',
})
export class Evals {
  private api = inject(Api);
  mode = 'vector';
  k = 5;
  retr = signal<RetrievalEval | null>(null);
  running = signal(false);
  answer = signal<AnswerEval | null>(null);

  constructor() {
    this.api.answerEval().subscribe(a => this.answer.set(a));
  }

  run() {
    this.running.set(true);
    this.retr.set(null);
    this.api.retrievalEval(this.mode, this.k).subscribe({
      next: r => { this.retr.set(r); this.running.set(false); },
      error: () => this.running.set(false),
    });
  }
}
