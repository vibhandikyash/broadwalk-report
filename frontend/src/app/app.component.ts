import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { ApiService } from './core/api.service';
import { Health } from './core/models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink],
  template: `
    <a class="skip" href="#main">Skip to content</a>
    <header class="topbar">
      <a routerLink="/projects" class="brand">Investor Report Generator</a>
      <span class="spacer"></span>
      @if (health(); as h) {
        <span class="muted small" role="status">PDF {{ h.pdf_renderer ? 'ready' : 'unavailable' }} · AI {{ h.llm_enabled ? 'on (' + h.llm_provider + ')' : 'off' }} · OCR {{ h.ocr_enabled ? 'on (' + h.ocr_provider + ')' : 'off' }}</span>
      } @else if (offline()) {
        <span class="err small" role="alert">Backend not reachable on /api. Start it (see README) and reload.</span>
      }
    </header>
    <main id="main" class="container" tabindex="-1"><router-outlet /></main>`,
})
export class AppComponent {
  private api = inject(ApiService);
  health = signal<Health | null>(null);
  offline = signal(false);
  constructor() {
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => this.offline.set(true) });
  }
}
