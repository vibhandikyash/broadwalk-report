import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { ProjectDetail, Report, ReportDataUi } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';
import { StepperComponent } from '../../shared/stepper.component';

@Component({
  selector: 'app-report',
  standalone: true,
  imports: [RouterLink, StepperComponent, StatusChipComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· report</span></h1>
        <nav class="row">
          <a [routerLink]="['/projects', p.id, 'review']" class="btn secondary">← Review</a>
          <button type="button" (click)="generate()" [disabled]="generating()">{{ generating() ? 'Rendering…' : 'Generate PDF' }}</button>
        </nav>
      </div>
      @if (summary(); as s) {
        @if (s.missing || s.conflicts || s.errors) {
          <p class="warn small">{{ s.missing }} missing values will print as "—", {{ s.conflicts }} unresolved conflicts use the primary source, {{ s.errors }} errors. You can still generate; fix them on the Review page and regenerate.</p>
        }
      }
      @if (error()) { <p class="err">{{ error() }}</p> }
      <div class="report-layout">
        <div class="preview"><iframe [src]="previewUrl()" title="Report preview"></iframe></div>
        <aside class="versions">
          <h3>Versions</h3>
          @for (r of reports(); track r.id) {
            <div class="version">
              <div><strong>v{{ r.version }}</strong> <span class="small muted">{{ r.created_at.slice(0, 16) }}</span></div>
              <div class="row"><app-status-chip [status]="r.status" />
                @if (r.status === 'done') { <a class="btn small" [href]="api.downloadUrl(pid, r.id)" target="_blank" rel="noopener">Download PDF</a> }
              </div>
              @if (r.error) { <div class="small err">{{ r.error }}</div> }
            </div>
          } @empty { <p class="muted small">No PDF generated yet.</p> }
          <button type="button" class="link small" (click)="refreshPreview()">Refresh preview</button>
        </aside>
      </div>
    }`,
})
export class ReportComponent {
  api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private sanitizer = inject(DomSanitizer);
  private destroy = inject(DestroyRef);
  pid = this.route.snapshot.paramMap.get('id')!;
  project = signal<ProjectDetail | null>(null);
  reports = signal<Report[]>([]);
  summary = signal<ReportDataUi['summary'] | null>(null);
  previewUrl = signal<SafeResourceUrl>(this.sanitizer.bypassSecurityTrustResourceUrl(this.api.previewUrl(this.pid)));
  generating = signal(false);
  error = signal<string | null>(null);

  constructor() {
    this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.reports.set(p.reports); if (p.reports.some((r) => r.status === 'queued' || r.status === 'rendering')) this.watch(); }, error: (e) => this.error.set(e.message) });
    this.api.reportData(this.pid).subscribe({ next: (d) => this.summary.set(d.summary), error: () => this.summary.set(null) });
  }

  refreshPreview(): void { this.previewUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.api.previewUrl(this.pid))); }

  generate(): void {
    this.generating.set(true);
    this.api.createReport(this.pid).subscribe({ next: () => this.watch(), error: (e) => { this.generating.set(false); this.error.set(e.error?.detail ?? e.message); } });
  }

  private watch(): void {
    this.generating.set(true);
    interval(1500).pipe(switchMap(() => this.api.listReports(this.pid)), takeWhile((rs) => rs.some((r) => r.status === 'queued' || r.status === 'rendering'), true), takeUntilDestroyed(this.destroy))
      .subscribe({ next: (rs) => { this.reports.set(rs); if (!rs.some((r) => r.status === 'queued' || r.status === 'rendering')) { this.generating.set(false); this.api.getProject(this.pid).subscribe((p) => this.project.set(p)); } }, error: (e) => { this.generating.set(false); this.error.set(e.message); } });
  }
}
