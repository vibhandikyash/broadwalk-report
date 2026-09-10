import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { Project, Stage, errorText } from '../../core/models';

/** Where a project has got to, in the order the work happens. */
const STAGES: Record<Stage, { label: string; chip: string }> = {
  upload: { label: 'Awaiting files', chip: 'chip-queued' },
  processing: { label: 'Processing', chip: 'chip-processing' },
  review: { label: 'Ready to review', chip: 'chip-derived' },
  generated: { label: 'Report generated', chip: 'chip-done' },
};

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div class="narrow-page">
    <div class="row page-head">
      <h1>Projects</h1>
      <span class="spacer"></span>
      @if (naming()) {
        <form class="row new-project" (ngSubmit)="create()">
          <label for="new-name" class="sr-only">New report name</label>
          <input id="new-name" name="name" [(ngModel)]="name" placeholder="e.g. The Boardwalk 2Q26" required autofocus />
          <button type="submit" [disabled]="!name.trim() || busy()">Create</button>
          <button type="button" class="link" (click)="naming.set(false)">cancel</button>
        </form>
      } @else {
        <button type="button" (click)="naming.set(true)">+ New project</button>
      }
    </div>
    <p class="muted page-lede">Quarterly investor reports, from raw exports to signed-off PDF — every value traceable to its source.</p>
    @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
    @if (loading()) { <p class="muted" role="status">Loading…</p> }
    @if (projects().length) {
      <div class="project-grid">
        @for (p of projects(); track p.id) {
          <div class="card project-card">
            <a class="project-card-link" [routerLink]="['/projects', p.id, resume(p)]">
              <span class="card-kicker">Quarterly report</span>
              <span class="card-title">{{ p.name }}</span>
            </a>
            <span class="tags">
              <span class="chip {{ stage(p).chip }}">{{ stage(p).label }}</span>
              <span class="chip">{{ p.file_count ?? 0 }} file{{ (p.file_count ?? 0) === 1 ? '' : 's' }}</span>
              @if (p.latest_version) {
                @if (p.latest_gap_count) { <span class="chip chip-conflict">draft · {{ p.latest_gap_count }}</span> }
                @else { <span class="chip chip-done">complete</span> }
              }
            </span>
            <span class="card-meta">
              @if (p.files_attention) { <span class="warn">{{ p.files_attention }} file{{ p.files_attention === 1 ? ' needs' : 's need' }} attention</span> }
              @if (p.latest_version) { <span>v{{ p.latest_version }}</span> } @else { <span class="muted">no PDF yet</span> }
              <span class="muted" [title]="p.updated_at">{{ when(p.updated_at) }}</span>
            </span>
            <div class="project-card-actions">
              <button type="button" class="link danger small" (click)="remove(p)" [attr.aria-label]="'Delete ' + p.name">Delete</button>
            </div>
          </div>
        }
      </div>
    } @else if (!loading()) {
      <div class="empty-state">
        <div class="mark" aria-hidden="true">○</div>
        <h2>No projects yet</h2>
        <p class="muted">Create a report for a property and quarter, drop in the raw exports — Yardi, HelloData, CoStar, Slate, any filenames, any order — and every number will be classified, extracted and consolidated for your review.</p>
      </div>
    }
    </div>`,
})
export class ProjectsComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  projects = signal<Project[]>([]);
  name = '';
  naming = signal(false);
  busy = signal(false);
  loading = signal(true);
  error = signal<string | null>(null);

  constructor() { this.load(); }

  stage(p: Project) { return STAGES[p.stage ?? 'upload'] ?? STAGES.upload; }
  /** Open a project where its work actually stands, rather than always at the files list. */
  resume(p: Project): string {
    if (p.stage === 'generated') return 'report';
    return p.report_built ? 'review' : 'files';
  }
  /** A date a person reads at a glance; the exact stamp stays in the title attribute. */
  when(iso: string): string {
    const then = new Date(iso);
    if (isNaN(then.getTime())) return iso;
    const mins = Math.round((Date.now() - then.getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`;
    if (mins < 60 * 24 * 7) return `${Math.round(mins / (60 * 24))} d ago`;
    return then.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  load(): void {
    this.loading.set(true);
    this.api.listProjects().subscribe({ next: (ps) => { this.projects.set(ps); this.loading.set(false); }, error: (e) => { this.loading.set(false); this.fail(errorText(e)); } });
  }

  fail(msg: string): void {
    this.error.set(msg);
    setTimeout(() => this.alert()?.nativeElement.focus(), 0);
  }

  create(): void {
    if (!this.name.trim()) return;
    this.busy.set(true);
    this.api.createProject(this.name.trim()).subscribe({
      next: (p) => { this.busy.set(false); this.naming.set(false); this.router.navigate(['/projects', p.id, 'files']); },
      error: (e) => { this.busy.set(false); this.fail(errorText(e)); },
    });
  }

  remove(p: Project): void {
    if (!confirm(`Delete "${p.name}" and all its files and reports?`)) return;
    this.api.deleteProject(p.id).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) });
  }
}
