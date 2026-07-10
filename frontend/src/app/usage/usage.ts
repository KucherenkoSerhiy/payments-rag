import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { Api, UsageStats } from '../api';

@Component({
  selector: 'app-usage',
  imports: [DecimalPipe],
  templateUrl: './usage.html',
})
export class Usage {
  private api = inject(Api);
  data = signal<UsageStats | null>(null);
  constructor() { this.api.usage().subscribe(d => this.data.set(d)); }
}
