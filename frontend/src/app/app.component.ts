import { Component, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { ApiService } from './core/api.service';
import { Health } from './core/models';
import { ShellStore } from './core/shell.store';
import { ThemeService } from './core/theme.service';

/** The four destinations, left to right. The last three need a project; Projects never does. */
const TABS = [
  { key: 'projects', label: 'Projects', scoped: false },
  { key: 'files', label: 'Files', scoped: true },
  { key: 'review', label: 'Review', scoped: true },
  { key: 'report', label: 'Report', scoped: true },
] as const;

interface Tab { key: string; label: string; link: unknown[] | null; current: boolean; held: string | null; }

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink],
  template: `
    <a class="skip" href="#main">Skip to content</a>
    <header class="topbar">
      <div class="project-id">
        <span class="kicker">Investor Report Generator</span>
        <h1 [title]="title()">{{ title() }}</h1>
      </div>
      <nav class="tabs" aria-label="Primary">
        @for (t of tabs(); track t.key) {
          @if (t.current) {
            <span class="tab current" aria-current="page">{{ t.label }}</span>
          } @else if (t.link) {
            <a class="tab" [routerLink]="t.link">{{ t.label }}</a>
          } @else {
            <button type="button" class="tab" disabled [title]="t.held">{{ t.label }}</button>
          }
        }
      </nav>
      <span class="spacer"></span>
      @if (health(); as h) {
        <span class="muted small health">PDF {{ h.pdf_renderer ? 'ready' : 'unavailable' }} · AI {{ h.llm_enabled ? 'on' : 'off' }} · OCR {{ h.ocr_enabled ? 'on' : 'off' }}</span>
      } @else if (offline()) {
        <span class="err small" role="alert">Backend not reachable on /api. Start it (see README) and reload.</span>
      }
      @if (shell.gaps(); as g) {
        <span class="chip chip-draft">draft · {{ g }} outstanding</span>
      } @else if (shell.gaps() === 0) {
        <span class="chip chip-done">complete</span>
      }
      @if (shell.mix(); as m) {
        <div class="progress">
          <div class="progress-track" role="img" [attr.aria-label]="m.resolved + ' of ' + m.total + ' values resolved'">
            <span class="progress-ex" [style.width]="m.ex"></span>
            <span class="progress-co" [style.width]="m.co"></span>
            <span class="progress-mi" [style.width]="m.mi"></span>
          </div>
          <span class="progress-line" aria-hidden="true">{{ m.resolved.toLocaleString() }} of {{ m.total.toLocaleString() }} values resolved</span>
        </div>
      }
      <button type="button" class="secondary btn-icon" (click)="theme.toggle()"
              [attr.aria-pressed]="theme.dark()" aria-label="Toggle dark theme" title="Toggle theme">{{ theme.dark() ? '☀' : '☾' }}</button>
    </header>
    <main id="main" class="app-main" tabindex="-1"><router-outlet /></main>`,
})
export class AppComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  shell = inject(ShellStore);
  theme = inject(ThemeService);
  health = signal<Health | null>(null);
  offline = signal(false);
  /** The routed URL, so the header can mark the current tab without each page telling it. */
  private url = signal('');

  title = computed(() => this.shell.project()?.name ?? 'All reports');

  tabs = computed<Tab[]>(() => {
    const p = this.shell.project();
    const url = this.url();
    return TABS.map((t) => {
      // A project page lives *under* /projects, so "starts with" would mark the index tab current on
      // every screen and turn the only way back into inert text. It is current only when it is the page.
      const current = t.scoped ? url.endsWith('/' + t.key) : url === '/' + t.key || url.startsWith('/' + t.key + '?');
      if (!t.scoped) return { key: t.key, label: t.label, link: ['/' + t.key], current, held: null };
      if (!p) return { key: t.key, label: t.label, link: null, current, held: 'Open a report first' };
      if (t.key !== 'files' && !p.report_built) return { key: t.key, label: t.label, link: null, current, held: 'Available once the files have been processed' };
      if (t.key === 'report' && this.shell.blocked()) return { key: t.key, label: t.label, link: null, current, held: 'Save or discard your edits first' };
      return { key: t.key, label: t.label, link: ['/projects', p.id, t.key], current, held: null };
    });
  });

  constructor() {
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => this.offline.set(true) });
    this.url.set(this.router.url);
    this.router.events.pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd)).subscribe((e) => {
      this.url.set(e.urlAfterRedirects);
      // Stop advertising a report the reader has left — whether they went to the index or straight
      // to a different project, whose own page will refill the store when its data arrives.
      const id = /^\/projects\/([^/]+)\//.exec(e.urlAfterRedirects)?.[1];
      if (!id || id !== this.shell.project()?.id) this.shell.clear();
    });
  }
}
