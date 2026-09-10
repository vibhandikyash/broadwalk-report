import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ProjectDetail } from '../core/models';

/** The three stages of a project. The label doubles as the accessible name the tests navigate by. */
const TABS = [
  { key: 'files', label: 'Files' },
  { key: 'review', label: 'Review data' },
  { key: 'report', label: 'Report' },
] as const;
export type TabKey = (typeof TABS)[number]['key'];

/**
 * The project band: identity, where you are, and what still needs doing. It replaces the seven-step
 * stepper, which said the same thing on every page. The current tab renders as text rather than a
 * link so "the link to Review" stays unambiguous for both a reader and a test.
 */
@Component({
  selector: 'app-project-nav',
  standalone: true,
  imports: [RouterLink],
  template: `
    @if (project(); as p) {
      <header class="project-bar">
        <div class="project-id">
          <h1>{{ p.name }}</h1>
          <p class="project-meta small">
            <span>{{ p.files.length }} file{{ p.files.length === 1 ? '' : 's' }}</span>
            @if (needAttention(); as n) { <span class="warn">{{ n }} need attention</span> }
            @if (p.reports.length) { <span>{{ p.reports.length }} version{{ p.reports.length === 1 ? '' : 's' }}</span> }
            @if (gaps() !== null) {
              @if (gaps()) { <span class="chip chip-conflict">draft · {{ gaps() }} outstanding</span> }
              @else { <span class="chip chip-done">complete</span> }
            }
          </p>
        </div>
        <nav class="tabs" aria-label="Project pages">
          @for (t of tabs; track t.key) {
            @if (t.key === current()) {
              <span class="tab current" aria-current="page">{{ t.label }}</span>
            } @else if (t.key !== 'files' && !p.report_built) {
              <button type="button" class="tab" disabled title="Available once the files have been processed">{{ t.label }}</button>
            } @else if (t.key === 'report' && blocked()) {
              <button type="button" class="tab" disabled title="Save or discard your edits first">{{ t.label }}</button>
            } @else {
              <a class="tab" [routerLink]="['/projects', p.id, t.key]">{{ t.label }}</a>
            }
          }
        </nav>
        <div class="project-action"><ng-content /></div>
      </header>
    }`,
})
export class ProjectNavComponent {
  project = input<ProjectDetail | null>(null);
  current = input.required<TabKey>();
  /** Unsaved edits: leaving for the report would silently drop them, so that tab is held. */
  blocked = input(false);
  /** Outstanding review items, when the caller knows them; null hides the badge. */
  gaps = input<number | null>(null);
  tabs = TABS;

  needAttention = computed(() => {
    const bad = new Set(['failed', 'unsupported', 'unrecognized', 'needs_ocr']);
    return this.project()?.files.filter((f) => bad.has(f.status)).length ?? 0;
  });
}
