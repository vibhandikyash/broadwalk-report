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
    <div class="row between page-head">
      <h1>Reports</h1>
      <form class="row" (ngSubmit)="create()">
        <label for="new-name" class="sr-only">New report name</label>
        <input id="new-name" name="name" [(ngModel)]="name" placeholder="New report name, e.g. The Boardwalk 2Q26" required />
        <button type="submit" [disabled]="!name.trim() || busy()">Create</button>
      </form>
    </div>
    @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
    @if (loading()) { <p class="muted" role="status">Loading…</p> }
    <table class="grid">
      <caption class="sr-only">Report projects</caption>
      <thead><tr><th scope="col">Name</th><th scope="col">Stage</th><th scope="col">Files</th><th scope="col">Latest report</th><th scope="col">Updated</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>
        @for (p of projects(); track p.id) {
          <tr>
            <td><a [routerLink]="['/projects', p.id, resume(p)]">{{ p.name }}</a></td>
            <td><span class="chip {{ stage(p).chip }}">{{ stage(p).label }}</span></td>
            <td class="tabular">{{ p.file_count ?? 0 }}
              @if (p.files_attention) { <div class="small warn">{{ p.files_attention }} need attention</div> }
            </td>
            <td>
              @if (p.latest_version) {
                <span class="nowrap">v{{ p.latest_version }}</span>
                @if (p.latest_gap_count) { <span class="chip chip-conflict">draft · {{ p.latest_gap_count }}</span> }
                @else { <span class="chip chip-done">complete</span> }
              } @else { <span class="muted">—</span> }
            </td>
            <td class="small muted nowrap" [title]="p.updated_at">{{ when(p.updated_at) }}</td>
            <td class="r"><button type="button" class="link danger" (click)="remove(p)" [attr.aria-label]="'Delete ' + p.name">Delete</button></td>
          </tr>
        } @empty {
          @if (!loading()) { <tr><td colspan="6" class="muted">No reports yet. Create one above.</td></tr> }
        }
      </tbody>
    </table>
    </div>`,
})
export class ProjectsComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  projects = signal<Project[]>([]);
  name = '';
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
      next: (p) => { this.busy.set(false); this.router.navigate(['/projects', p.id, 'files']); },
      error: (e) => { this.busy.set(false); this.fail(errorText(e)); },
    });
  }

  remove(p: Project): void {
    if (!confirm(`Delete "${p.name}" and all its files and reports?`)) return;
    this.api.deleteProject(p.id).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) });
  }
}
