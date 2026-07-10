import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

const BASE = 'http://127.0.0.1:8000';

export interface Citation { chunk_id: number; source: string; page: number | null; text: string; }
export interface AskResponse {
  answer: string;
  citations: Citation[];
  timing: { retrieval_s: number; generation_s: number };
  cost_usd: number;
  tokens: { input: number; output: number };
}
export interface HealthCheck { name: string; kind: string; ok: boolean; latency_ms: number; detail: string; at: string; }
export interface PerQ { id: string; hit: boolean | null; }
export interface RetrievalEval {
  mode: string; k: number; recall: number; answered: number; total: number; duration_s: number; per_question: PerQ[];
}
export interface AnswerEval {
  at?: string; mean?: number; pass_rate?: number; threshold?: number; duration_s?: number;
  per_question?: { id: string; score: number; critique: string }[]; empty?: boolean;
}
export interface UsageStats { count: number; avg_latency_s: number; total_cost_usd: number; recent: any[]; }

@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  ask(question: string, k = 5) { return this.http.post<AskResponse>(`${BASE}/ask`, { question, k }); }
  health() { return this.http.get<{ checks: HealthCheck[] }>(`${BASE}/health`); }
  checkOne(name: string) { return this.http.post<HealthCheck>(`${BASE}/health/${name}`, {}); }
  retrievalEval(mode: string, k: number) { return this.http.post<RetrievalEval>(`${BASE}/evals/retrieval?mode=${mode}&k=${k}`, {}); }
  answerEval() { return this.http.get<AnswerEval>(`${BASE}/evals/answer`); }
  usage() { return this.http.get<UsageStats>(`${BASE}/usage`); }
}
