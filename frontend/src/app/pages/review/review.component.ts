import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Health, Issue, Overrides, ProjectDetail, ReportDataUi, UiSection, errorText } from '../../core/models';
import { StepperComponent } from '../../shared/stepper.component';
import { FieldChange, FieldEditorComponent } from './field-editor.component';
import { TableEditorComponent } from './table-editor.component';

export interface OverrideEntry { path: string; text: string; }
/** Origins in the order the summary reads best; the backend supplies the counts. */
const ORIGIN_LABELS = [
  { key: 'extracted', label: 'extracted' }, { key: 'ocr', label: 'via OCR' }, { key: 'computed', label: 'calculated' },
  { key: 'manual', label: 'entered by you' }, { key: 'ai_draft', label: 'AI drafts' }, { key: 'missing', label: 'not found' },
];

@Component({
  selector: 'app-review',
  standalone: true,
  imports: [RouterLink, StepperComponent, FieldEditorComponent, TableEditorComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="pending().size ? 'review' : p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· review extracted data</span></h1>
        <nav class="row" aria-label="Project pages">
          <a [routerLink]="['/projects', p.id, 'files']" class="btn secondary">← Files</a>
          @if (pending().size) {
            <button type="button" class="btn" disabled title="Save or discard your edits first">Report →</button>
          } @else {
            <a [routerLink]="['/projects', p.id, 'report']" class="btn">Report →</a>
          }
        </nav>
      </div>
    }
    <p class="status small" role="status" aria-live="polite">{{ status() }}</p>
    @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
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
          <button type="button" (click)="save()" [disabled]="!pending().size || saving()">{{ saving() ? 'Saving…' : 'Save' + (pending().size ? ' (' + pending().size + ')' : '') }}</button>
        </div>
      </div>
      @if (d.narrative_error) { <p class="warn small" role="status">AI drafting: {{ d.narrative_error }}</p> }
      <div class="review-layout">
        <aside class="sections" aria-label="Report sections">
          @for (s of d.sections; track s.key) {
            <button type="button" class="section-link" [class.active]="s.key === selected()" [attr.aria-current]="s.key === selected() ? 'true' : null" (click)="select(s.key)">
              <span class="pg" aria-hidden="true">p{{ s.page }}</span> {{ s.title }}
              @if (attentionCount(s); as n) { <span class="badge"><span class="sr-only">, </span>{{ n }}<span class="sr-only"> need attention</span></span> }
            </button>
          }
          @if (d.summary.completeness; as c) {
            <details class="completeness" [open]="!c.complete" aria-labelledby="completeness-h">
              <summary id="completeness-h">Report completeness: <strong>{{ c.complete ? 'complete' : c.gap_count + ' item' + (c.gap_count === 1 ? '' : 's') + ' outstanding' }}</strong></summary>
              <p class="small muted">A PDF can always be generated. It is marked as a draft until every item below is reviewed.@if (c.ai_drafts_pending) { {{ c.ai_drafts_pending }} AI draft{{ c.ai_drafts_pending === 1 ? '' : 's' }} still need review. }</p>
              <ul class="plain small">
                @for (g of c.gaps; track g.path) {
                  <li><button type="button" class="issue issue-warning small" (click)="jumpTo(g.path)"><span class="pg">p{{ g.page }}</span> {{ g.label }} <span class="muted">({{ g.reason }})</span></button></li>
                }
              </ul>
            </details>
          }
          @if (d.provenance; as pv) {
            <details class="prov-panel"><summary>Where the data came from</summary>
              <div class="counts small">
                @for (c of originCounts(pv.counts); track c.key) {
                  <span><span class="prov-dot prov-{{ c.key }}"></span> {{ c.count }} {{ c.label }}</span>
                }
              </div>
              <p class="small muted">Every field below states its own source. The same trail is printed in Appendix A of the generated report.</p>
              <ul class="plain small">
                @for (f of pv.files; track f.filename) {
                  <li><strong>{{ f.filename }}</strong>
                    @if (f.method !== 'native') { <span class="prov-tag prov-ocr">OCR</span> }
                    <div class="muted">{{ f.doc_labels.join('; ') }}@if (f.method !== 'native') { · text recovered by vision OCR@if (f.ocr_pages.length) { on page{{ f.ocr_pages.length === 1 ? '' : 's' }} {{ f.ocr_pages.join(', ') }} }@if (f.ocr_confidence != null) { ({{ (f.ocr_confidence * 100).toFixed(0) }}% confidence) } }</div>
                  </li>
                } @empty { <li class="muted">No source file has been consolidated yet.</li> }
              </ul>
            </details>
          }
          <details class="issues"><summary>Issues ({{ d.issues.length }})</summary>
            <ul class="plain">
              @for (i of d.issues; track $index) {
                <li><button type="button" class="issue issue-{{ i.severity }} small" (click)="jump(i)" [disabled]="!i.path"><span class="sr-only">{{ i.severity }}: </span>{{ i.message }}</button></li>
              }
            </ul>
          </details>
          <details class="corrections" (toggle)="loadOverrides($event)"><summary>Stored corrections</summary>
            @if (overrides(); as ov) {
              <ul class="plain small">
                @for (e of entries(); track e.path) {
                  <li class="row between"><code>{{ e.path }}</code> <span class="muted">{{ e.text }}</span>
                    <button type="button" class="link danger small" (click)="resetOverride(e.path)" [attr.aria-label]="'Reset correction ' + e.path">reset</button></li>
                } @empty { <li class="muted">No stored corrections.</li> }
              </ul>
              @if (entries().length) { <button type="button" class="link danger small" (click)="resetAll()">Reset all corrections</button> }
            }
          </details>
        </aside>
        <section class="editor" aria-labelledby="section-heading">
          @if (section(); as s) {
            <h2 id="section-heading" tabindex="-1" #heading>{{ s.title }} <span class="muted small">page {{ s.page }}</span></h2>
            <div class="fields">
              @for (f of visibleFields(s); track f.path) { <app-field-editor [f]="f" (changed)="onChange($event)" /> }
            </div>
            @for (t of s.tables; track t.path) {
              <app-table-editor [t]="t" [attentionOnly]="attentionOnly()" (changed)="onChange($event)" (addRow)="addRow($event)" (deleteRow)="deleteRow($event)" />
            }
          }
        </section>
      </div>
    } @else if (!error()) { <p class="muted" role="status">Loading…</p> }`,
})
export class ReviewComponent {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private pid = this.route.snapshot.paramMap.get('id')!;
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  heading = viewChild<ElementRef<HTMLElement>>('heading');
  project = signal<ProjectDetail | null>(null);
  data = signal<ReportDataUi | null>(null);
  health = signal<Health | null>(null);
  overrides = signal<Overrides | null>(null);
  selected = signal<string>('property');
  attentionOnly = signal(false);
  pending = signal<Map<string, unknown>>(new Map());
  saving = signal(false);
  drafting = signal(false);
  error = signal<string | null>(null);
  status = signal('');
  section = computed<UiSection | null>(() => this.data()?.sections.find((s) => s.key === this.selected()) ?? null);
  entries = computed<OverrideEntry[]>(() => this.overrideEntries(this.overrides()));

  constructor() {
    this.api.getProject(this.pid).subscribe({ next: (p) => this.project.set(p), error: (e) => this.fail(errorText(e)) });
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => undefined });
    this.load();
  }

  load(): void {
    this.api.reportData(this.pid).subscribe({
      next: (d) => { this.data.set(d); if (d.narrative_status === 'running') this.watchNarratives(); },
      error: (e) => this.fail(errorText(e)),
    });
  }

  fail(msg: string): void {
    this.error.set(msg);
    setTimeout(() => this.alert()?.nativeElement.focus(), 0);
  }

  attention(f: { status: string; effective: unknown }): boolean { return (f.status === 'missing' && f.effective == null) || f.status === 'conflict' || f.status === 'ai_draft'; }
  attentionCount(s: UiSection): number {
    return s.fields.filter((f) => this.attention(f)).length + s.tables.reduce((n, t) => n + t.rows.reduce((m, r) => m + r.cells.filter((c) => this.attention(c)).length, 0), 0);
  }
  visibleFields(s: UiSection) { return this.attentionOnly() ? s.fields.filter((f) => this.attention(f)) : s.fields; }
  originCounts(counts: Record<string, number>): { key: string; label: string; count: number }[] {
    return ORIGIN_LABELS.filter((o) => counts[o.key]).map((o) => ({ key: o.key, label: o.label, count: counts[o.key] }));
  }

  select(key: string): void { this.selected.set(key); }
  onChange(ch: FieldChange): void { const m = new Map(this.pending()); m.set(ch.path, ch.value); this.pending.set(m); }

  save(): void {
    const changes = Array.from(this.pending().entries()).map(([path, value]) => ({ path, value }));
    if (!changes.length) return;
    this.saving.set(true);
    this.error.set(null);
    this.api.patchReportData(this.pid, { changes }).subscribe({
      next: (d) => { this.data.set(d); this.pending.set(new Map()); this.saving.set(false); this.status.set(`Saved ${changes.length} change${changes.length === 1 ? '' : 's'}.`); this.overrides.set(null); },
      error: (e) => { this.saving.set(false); this.fail('Not saved. ' + errorText(e)); },
    });
  }
  addRow(table: string): void {
    this.api.patchReportData(this.pid, { add_rows: [{ table, values: {} }] }).subscribe({ next: (d) => { this.data.set(d); this.status.set('Row added.'); }, error: (e) => this.fail(errorText(e)) });
  }
  deleteRow(ev: { table: string; key: string }): void {
    if (!confirm('Remove this row from the report?')) return;
    this.api.patchReportData(this.pid, { delete_rows: [ev] }).subscribe({ next: (d) => { this.data.set(d); this.status.set('Row removed.'); }, error: (e) => this.fail(errorText(e)) });
  }
  rebuild(): void {
    if (this.pending().size && !confirm('Unsaved edits will be lost. Rebuild anyway?')) return;
    this.saving.set(true);
    this.api.rebuildReportData(this.pid).subscribe({
      next: (d) => { this.data.set(d); this.pending.set(new Map()); this.saving.set(false); this.status.set('Rebuilt from the processed files; your saved corrections were kept.'); },
      error: (e) => { this.saving.set(false); this.fail(errorText(e)); },
    });
  }
  draft(): void {
    this.drafting.set(true);
    this.status.set('Drafting narratives with AI…');
    this.api.draftNarratives(this.pid).subscribe({ next: () => this.watchNarratives(), error: (e) => { this.drafting.set(false); this.fail(errorText(e)); } });
  }
  private watchNarratives(): void {
    this.drafting.set(true);
    interval(2000).pipe(switchMap(() => this.api.reportData(this.pid)), takeWhile((d) => d.narrative_status === 'running', true), takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (d) => { this.data.set(d); if (d.narrative_status !== 'running') { this.drafting.set(false); this.status.set(d.narrative_status === 'done' ? 'AI drafts are ready for review.' : 'AI drafting failed.'); } },
        error: () => this.drafting.set(false),
      });
  }
  jump(i: Issue): void {
    if (!i.path) return;
    this.jumpTo(i.path);
  }
  jumpTo(path: string): void {
    this.selected.set(path.split('.')[0]);
    setTimeout(() => this.heading()?.nativeElement.focus(), 0);
  }

  loadOverrides(ev: Event): void {
    if ((ev.target as HTMLDetailsElement).open && !this.overrides()) this.api.overrides(this.pid).subscribe({ next: (ov) => this.overrides.set(ov), error: (e) => this.fail(errorText(e)) });
  }
  overrideEntries(ov: Overrides | null): OverrideEntry[] {
    if (!ov) return [];
    const out: OverrideEntry[] = [];
    for (const [path, v] of Object.entries(ov.fields ?? {})) out.push({ path, text: String(v) });
    for (const [table, rows] of Object.entries(ov.rows ?? {})) for (const key of Object.keys(rows)) out.push({ path: `${table}.rows.${key}`, text: 'manual row' });
    for (const [table, keys] of Object.entries(ov.deleted_rows ?? {})) if (keys.length) out.push({ path: `${table}.deleted`, text: 'removed rows: ' + keys.join(', ') });
    for (const path of Object.keys(ov.ai_drafts ?? {})) out.push({ path, text: 'AI draft' });
    return out;
  }
  resetOverride(path: string): void {
    this.api.resetOverrides(this.pid, { paths: [path] }).subscribe({ next: (ov) => { this.overrides.set(ov); this.status.set(`Correction ${path} reset.`); this.load(); }, error: (e) => this.fail(errorText(e)) });
  }
  resetAll(): void {
    if (!confirm('Discard every saved correction, manual row and AI draft for this report?')) return;
    this.api.resetOverrides(this.pid, {}).subscribe({ next: (ov) => { this.overrides.set(ov); this.status.set('All corrections reset.'); this.load(); }, error: (e) => this.fail(errorText(e)) });
  }
}
