import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Health, Issue, ProjectDetail, ReportDataUi, UiSection } from '../../core/models';
import { StepperComponent } from '../../shared/stepper.component';
import { FieldChange, FieldEditorComponent } from './field-editor.component';
import { TableEditorComponent } from './table-editor.component';

@Component({
  selector: 'app-review',
  standalone: true,
  imports: [RouterLink, StepperComponent, FieldEditorComponent, TableEditorComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="pending().size ? 'review' : p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· review extracted data</span></h1>
        <nav class="row">
          <a [routerLink]="['/projects', p.id, 'files']" class="btn secondary">← Files</a>
          <a [routerLink]="['/projects', p.id, 'report']" class="btn" [class.disabled]="pending().size > 0">Report →</a>
        </nav>
      </div>
    }
    @if (error()) { <p class="err">{{ error() }}</p> }
    @if (data(); as d) {
      <div class="toolbar row between">
        <div class="row">
          <label class="small"><input type="checkbox" [checked]="attentionOnly()" (change)="attentionOnly.set(!attentionOnly())" /> needs attention only</label>
          <span class="small muted">{{ d.summary.missing }} missing · {{ d.summary.conflicts }} conflicts · {{ d.summary.ai_drafts }} AI drafts · {{ d.summary.errors }} errors · {{ d.summary.warnings }} warnings</span>
        </div>
        <div class="row">
          <button type="button" class="secondary" (click)="rebuild()" [disabled]="saving()">Rebuild from files</button>
          @if (health()?.llm_enabled) {
            <button type="button" class="secondary" (click)="draft()" [disabled]="drafting()">{{ drafting() ? 'Drafting…' : 'Draft narratives with AI' }}</button>
          }
          <button type="button" (click)="save()" [disabled]="!pending().size || saving()">{{ saving() ? 'Saving…' : 'Save ' + (pending().size ? '(' + pending().size + ')' : '') }}</button>
        </div>
      </div>
      @if (d.narrative_error) { <p class="warn small">AI drafting: {{ d.narrative_error }}</p> }
      <div class="review-layout">
        <aside class="sections">
          @for (s of d.sections; track s.key) {
            <button type="button" class="section-link" [class.active]="s.key === selected()" (click)="selected.set(s.key)">
              <span class="pg">p{{ s.page }}</span> {{ s.title }}
              @if (attentionCount(s); as n) { <span class="badge">{{ n }}</span> }
            </button>
          }
          <details class="issues"><summary>Issues ({{ d.issues.length }})</summary>
            @for (i of d.issues; track $index) { <div class="issue issue-{{ i.severity }} small" (click)="jump(i)">{{ i.message }}</div> }
          </details>
        </aside>
        <section class="editor">
          @if (section(); as s) {
            <h2>{{ s.title }} <span class="muted small">page {{ s.page }}</span></h2>
            <div class="fields">
              @for (f of visibleFields(s); track f.path) { <app-field-editor [f]="f" (changed)="onChange($event)" /> }
            </div>
            @for (t of s.tables; track t.path) {
              <app-table-editor [t]="t" [attentionOnly]="attentionOnly()" (changed)="onChange($event)" (addRow)="addRow($event)" (deleteRow)="deleteRow($event)" />
            }
          }
        </section>
      </div>
    } @else if (!error()) { <p class="muted">Loading…</p> }`,
})
export class ReviewComponent {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private pid = this.route.snapshot.paramMap.get('id')!;
  project = signal<ProjectDetail | null>(null);
  data = signal<ReportDataUi | null>(null);
  health = signal<Health | null>(null);
  selected = signal<string>('property');
  attentionOnly = signal(false);
  pending = signal<Map<string, unknown>>(new Map());
  saving = signal(false);
  drafting = signal(false);
  error = signal<string | null>(null);
  section = computed<UiSection | null>(() => this.data()?.sections.find((s) => s.key === this.selected()) ?? null);

  constructor() {
    this.api.getProject(this.pid).subscribe({ next: (p) => this.project.set(p), error: (e) => this.error.set(e.message) });
    this.api.health().subscribe((h) => this.health.set(h));
    this.load();
  }

  load(): void {
    this.api.reportData(this.pid).subscribe({
      next: (d) => { this.data.set(d); if (d.narrative_status === 'running') this.watchNarratives(); },
      error: (e) => this.error.set(e.error?.detail ?? e.message),
    });
  }

  attention(f: { status: string; effective: unknown }): boolean { return (f.status === 'missing' && f.effective == null) || f.status === 'conflict' || f.status === 'ai_draft'; }
  attentionCount(s: UiSection): number {
    return s.fields.filter((f) => this.attention(f)).length + s.tables.reduce((n, t) => n + t.rows.reduce((m, r) => m + r.cells.filter((c) => this.attention(c)).length, 0), 0);
  }
  visibleFields(s: UiSection) { return this.attentionOnly() ? s.fields.filter((f) => this.attention(f)) : s.fields; }

  onChange(ch: FieldChange): void { const m = new Map(this.pending()); m.set(ch.path, ch.value); this.pending.set(m); }

  save(): void {
    const changes = Array.from(this.pending().entries()).map(([path, value]) => ({ path, value }));
    this.saving.set(true);
    this.api.patchReportData(this.pid, { changes }).subscribe({
      next: (d) => { this.data.set(d); this.pending.set(new Map()); this.saving.set(false); },
      error: (e) => { this.saving.set(false); this.error.set(e.error?.detail ?? e.message); },
    });
  }
  addRow(table: string): void {
    this.api.patchReportData(this.pid, { add_rows: [{ table, values: {} }] }).subscribe({ next: (d) => this.data.set(d), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }
  deleteRow(ev: { table: string; key: string }): void {
    if (!confirm('Remove this row from the report?')) return;
    this.api.patchReportData(this.pid, { delete_rows: [ev] }).subscribe({ next: (d) => this.data.set(d), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }
  rebuild(): void {
    if (this.pending().size && !confirm('Unsaved edits will be lost. Rebuild anyway?')) return;
    this.saving.set(true);
    this.api.rebuildReportData(this.pid).subscribe({ next: (d) => { this.data.set(d); this.pending.set(new Map()); this.saving.set(false); }, error: (e) => { this.saving.set(false); this.error.set(e.error?.detail ?? e.message); } });
  }
  draft(): void {
    this.drafting.set(true);
    this.api.draftNarratives(this.pid).subscribe({ next: () => this.watchNarratives(), error: (e) => { this.drafting.set(false); this.error.set(e.error?.detail ?? e.message); } });
  }
  private watchNarratives(): void {
    this.drafting.set(true);
    interval(2000).pipe(switchMap(() => this.api.reportData(this.pid)), takeWhile((d) => d.narrative_status === 'running', true), takeUntilDestroyed(this.destroy))
      .subscribe({ next: (d) => { this.data.set(d); if (d.narrative_status !== 'running') this.drafting.set(false); }, error: () => this.drafting.set(false) });
  }
  jump(i: Issue): void { if (i.path) this.selected.set(i.path.split('.')[0]); }
}
