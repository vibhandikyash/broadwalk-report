import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { ApiService } from './core/api.service';
import { Health } from './core/models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink],
  template: `
    <header class="topbar">
      <a routerLink="/projects" class="brand">Investor Report Generator</a>
      <span class="spacer"></span>
      @if (health(); as h) {
        <span class="muted small">PDF {{ h.pdf_renderer ? 'ready' : 'unavailable' }} · AI {{ h.llm_enabled ? 'on' : 'off' }}</span>
      } @else if (offline()) {
        <span class="err small">Backend not reachable on /api. Start it with: uvicorn app.main:app --port 8000</span>
      }
    </header>
    <main class="container"><router-outlet /></main>`,
})
export class AppComponent {
  private api = inject(ApiService);
  health = signal<Health | null>(null);
  offline = signal(false);
  constructor() {
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => this.offline.set(true) });
  }
}
