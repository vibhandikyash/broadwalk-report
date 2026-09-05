import { Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Completeness, ProjectDetail, Report, ReportDataUi, errorText } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';
import { StepperComponent } from '../../shared/stepper.component';

const BUSY = new Set(['queued', 'rendering']);

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [RouterLink, StepperComponent, StatusChipComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· report</span></h1>
        <nav class="row" aria-label="Project pages">
          <a [routerLink]="['/projects', p.id, 'review']" class="btn secondary">← Review</a>
          <button type="button" (click)="generate()" [disabled]="generating()">{{ generating() ? 'Rendering…' : (completeness()?.complete === false ? 'Generate draft PDF' : 'Generate PDF') }}</button>
        </nav>
      </div>
      @if (completeness(); as c) {
        <p class="small completeness-line" [class.warn]="!c.complete" [class.ok]="c.complete">
          @if (c.complete) { <span class="chip chip-done">complete</span> Every item a finished investor report needs has been reviewed. }
          @else { <span class="chip chip-conflict">draft</span> {{ c.gap_count }} item{{ c.gap_count === 1 ? '' : 's' }} outstanding on the Review page. A PDF can still be generated; it is marked as a draft on every page until the review is complete. }
        </p>
      }
      @if (summary(); as s) {
        @if (s.conflicts || s.errors) {
          <p class="warn small">{{ s.conflicts }} unresolved conflicts use the primary source, {{ s.errors }} errors. Fix them on the Review page and regenerate.</p>
        }
      }
      <p class="status small" role="status" aria-live="polite">{{ status() }}</p>
      @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
      <div class="report-layout">
        <div class="preview"><iframe [src]="previewUrl()" title="Report preview" sandbox=""></iframe></div>
        <aside class="versions" aria-labelledby="versions-h">
          <h3 id="versions-h">Versions</h3>
          <ul class="plain">
          @for (r of reports(); track r.id) {
            <li class="version">
              <div><strong>v{{ r.version }}</strong> <span class="small muted">{{ r.created_at.slice(0, 16) }}</span></div>
              <div class="row"><app-status-chip [status]="r.status" />
                @if (r.complete === false) { <span class="chip chip-conflict" [title]="r.gap_count + ' items were outstanding when this version was generated'">draft · {{ r.gap_count }} outstanding</span> }
                @else if (r.complete === true) { <span class="chip chip-done">complete</span> }
                @if (r.status === 'done') {
                  <a class="btn small" [href]="api.downloadUrl(pid, r.id)" target="_blank" rel="noopener">Download PDF<span class="sr-only"> version {{ r.version }}</span></a>
                  <a class="link small" [href]="api.snapshotUrl(pid, r.id)" target="_blank" rel="noopener">data snapshot<span class="sr-only"> for version {{ r.version }}</span></a>
                }
              </div>
              @if (r.error) { <div class="small err">{{ r.error }}</div> }
            </li>
          } @empty { <li class="muted small">No PDF generated yet.</li> }
          </ul>
          <button type="button" class="link small" (click)="refreshPreview()">Refresh preview</button>
        </aside>
      </div>
    } @else if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> } @else { <p class="muted" role="status">Loading…</p> }`,
})
export class ReportComponent {
  api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private sanitizer = inject(DomSanitizer);
  private destroy = inject(DestroyRef);
  pid = this.route.snapshot.paramMap.get('id')!;
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  project = signal<ProjectDetail | null>(null);
  reports = signal<Report[]>([]);
  summary = signal<ReportDataUi['summary'] | null>(null);
  completeness = signal<Completeness | null>(null);
  previewUrl = signal<SafeResourceUrl>(this.sanitizer.bypassSecurityTrustResourceUrl(this.api.previewUrl(this.pid)));
  generating = signal(false);
  error = signal<string | null>(null);
  status = signal('');

  constructor() {
    this.api.getProject(this.pid).subscribe({
      next: (p) => { this.project.set(p); this.reports.set(p.reports); if (p.reports.some((r) => BUSY.has(r.status))) this.watch(); },
      error: (e) => this.fail(errorText(e)),
    });
    this.api.reportData(this.pid).subscribe({ next: (d) => { this.summary.set(d.summary); this.completeness.set(d.summary.completeness ?? null); }, error: () => this.summary.set(null) });
  }

  fail(msg: string): void {
    this.error.set(msg);
    setTimeout(() => this.alert()?.nativeElement.focus(), 0);
  }

  refreshPreview(): void { this.previewUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.api.previewUrl(this.pid))); }

  generate(): void {
    this.generating.set(true);
    this.error.set(null);
    this.status.set('Rendering the PDF…');
    this.api.createReport(this.pid).subscribe({ next: () => this.watch(), error: (e) => { this.generating.set(false); this.fail(errorText(e)); } });
  }

  private watch(): void {
    this.generating.set(true);
    interval(1500).pipe(switchMap(() => this.api.listReports(this.pid)), takeWhile((rs) => rs.some((r) => BUSY.has(r.status)), true), takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (rs) => {
          this.reports.set(rs);
          if (!rs.some((r) => BUSY.has(r.status))) {
            this.generating.set(false);
            const latest = rs[0];
            if (latest) this.status.set(latest.status === 'done' ? `PDF version ${latest.version} is ready to download.` : `Version ${latest.version} failed: ${latest.error ?? 'unknown error'}`);
            this.api.getProject(this.pid).subscribe({ next: (p) => this.project.set(p), error: () => undefined });
          }
        },
        error: (e) => { this.generating.set(false); this.fail(errorText(e)); },
      });
  }
}
