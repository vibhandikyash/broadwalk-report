import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Completeness, ProjectDetail, Report, ReportDataUi, errorText } from '../../core/models';
import { ShellStore } from '../../core/shell.store';
import { StatusChipComponent } from '../../shared/status-chip.component';
import { PagePreviewComponent } from '../../shared/page-preview.component';

const BUSY = new Set(['queued', 'rendering']);

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [RouterLink, StatusChipComponent, PagePreviewComponent],
  template: `
    @if (project(); as p) {
      <div class="narrow-page report-page">
        <div class="row page-head">
          <h1>Report</h1>
          <span class="spacer"></span>
          <div class="project-action">
            <button type="button" (click)="generate()" [disabled]="generating()">{{ generating() ? 'Rendering…' : (completeness()?.complete === false ? 'Generate draft PDF' : 'Generate PDF') }}</button>
          </div>
        </div>

        @if (completeness(); as c) {
          <div class="report-banner" [class.complete]="c.complete">
            <span class="mark" aria-hidden="true">{{ c.complete ? '✓' : '○' }}</span>
            <div class="banner-text">
              <div class="headline">{{ c.complete ? 'Complete — every value reviewed' : 'Draft · ' + c.gap_count + ' item' + (c.gap_count === 1 ? '' : 's') + ' outstanding' }}</div>
              <p class="small completeness-line" [class.warn]="!c.complete" [class.ok]="c.complete">
                @if (c.complete) { Every item a finished investor report needs has been reviewed. The next PDF is stamped as final. }
                @else { {{ c.gap_count }} item{{ c.gap_count === 1 ? '' : 's' }} outstanding on the Review page. A PDF can always be generated — it is stamped DRAFT until every item is reviewed. }
              </p>
            </div>
            @if (!c.complete) { <a class="btn secondary" [routerLink]="['/projects', p.id, 'review']">Resolve in Review →</a> }
          </div>
        }
        @if (summary(); as s) {
          @if (s.conflicts || s.errors) {
            <p class="warn small">{{ s.conflicts }} unresolved conflicts use the primary source, {{ s.errors }} errors. Fix them on the Review page and regenerate.</p>
          }
        }
        @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }

        <div class="report-cols">
          <section class="report-preview" aria-label="Report preview">
            <h2>Preview</h2>
            <app-page-preview [url]="previewUrl()" [page]="page()" [pages]="pages()" (refresh)="refreshPreview()" />
            <div class="page-nav">
              <button type="button" class="secondary btn-icon" (click)="step(-1)" [disabled]="page() <= 1" aria-label="Previous page">‹</button>
              <button type="button" class="secondary btn-icon" (click)="step(1)" [disabled]="page() >= pages()" aria-label="Next page">›</button>
              <span class="muted small">The full report renders as a landscape PDF.</span>
            </div>
          </section>
          <section class="report-versions" aria-labelledby="versions-h">
            <h2 id="versions-h">Versions</h2>
            <ul class="plain">
            @for (r of reports(); track r.id) {
              <li class="version card">
                <div class="row">
                  <strong>v{{ r.version }}</strong>
                  @if (r.complete === false) { <span class="chip chip-draft" [title]="r.gap_count + ' items were outstanding when this version was generated'">draft · {{ r.gap_count }} outstanding</span> }
                  @else if (r.complete === true) { <span class="chip chip-done">complete</span> }
                  <span class="spacer"></span>
                  <span class="small muted">{{ r.created_at.slice(0, 16).replace('T', ' ') }}</span>
                </div>
                <div class="row">
                  <app-status-chip [status]="r.status" />
                  @if (r.status === 'done') {
                    <a class="btn secondary small" [href]="api.downloadUrl(pid, r.id)" target="_blank" rel="noopener">↓ PDF<span class="sr-only"> version {{ r.version }}</span></a>
                    <a class="link small" [href]="api.snapshotUrl(pid, r.id)" target="_blank" rel="noopener">data snapshot<span class="sr-only"> for version {{ r.version }}</span></a>
                  }
                </div>
                @if (r.error) { <div class="small err">{{ r.error }}</div> }
              </li>
            } @empty { <li class="muted small">No PDF generated yet.</li> }
            </ul>
          </section>
        </div>
        <p class="status small" role="status" aria-live="polite">{{ status() }}</p>
      </div>
    } @else if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> } @else { <p class="muted" role="status">Loading…</p> }`,
})
export class ReportComponent {
  api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private shell = inject(ShellStore);
  pid = this.route.snapshot.paramMap.get('id')!;
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  project = signal<ProjectDetail | null>(null);
  reports = signal<Report[]>([]);
  summary = signal<ReportDataUi['summary'] | null>(null);
  completeness = signal<Completeness | null>(null);
  page = signal(1);
  pages = signal(10);
  private previewToken = signal(0);
  previewUrl = computed(() => `${this.api.previewUrl(this.pid)}&r=${this.previewToken()}`);
  generating = signal(false);
  error = signal<string | null>(null);
  status = signal('');

  constructor() {
    this.api.getProject(this.pid).subscribe({
      next: (p) => { this.project.set(p); this.shell.setProject(p); this.reports.set(p.reports); if (p.reports.some((r) => BUSY.has(r.status))) this.watch(); },
      error: (e) => this.fail(errorText(e)),
    });
    this.api.reportData(this.pid).subscribe({
      next: (d) => {
        this.summary.set(d.summary);
        this.completeness.set(d.summary.completeness ?? null);
        this.shell.gaps.set(d.summary.completeness?.gap_count ?? null);
        this.shell.origins.set(d.provenance?.counts ?? null);
        this.pages.set(d.preview_total_pages ?? 10);
      },
      error: () => this.summary.set(null),
    });
  }

  fail(msg: string): void {
    this.error.set(msg);
    setTimeout(() => this.alert()?.nativeElement.focus(), 0);
  }

  refreshPreview(): void { this.previewToken.update((v) => v + 1); }
  step(by: number): void { this.page.update((n) => Math.min(Math.max(n + by, 1), this.pages())); }

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
            this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.shell.setProject(p); }, error: () => undefined });
          }
        },
        error: (e) => { this.generating.set(false); this.fail(errorText(e)); },
      });
  }
}
