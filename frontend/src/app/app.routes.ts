import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./ask/ask').then(m => m.Ask) },
  { path: 'evals', loadComponent: () => import('./evals/evals').then(m => m.Evals) },
  { path: 'usage', loadComponent: () => import('./usage/usage').then(m => m.Usage) },
  { path: 'health', loadComponent: () => import('./health/health').then(m => m.Health) },
];
