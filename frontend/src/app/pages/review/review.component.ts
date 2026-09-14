import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Gap, Health, Issue, Overrides, ReportDataUi, UiSection, errorText } from '../../core/models';
import { ShellStore } from '../../core/shell.store';
import { FieldChange, FieldEditorComponent } from './field-editor.component';
import { PagePreviewComponent } from '../../shared/page-preview.component';
import { TableEditorComponent } from './table-editor.component';

export interface OverrideEntry { path: string; text: string; }
/** The inspector's tabs: the page being edited, then the four ways of interrogating the data. */
const INSPECTOR_TABS = [
  { key: 'page', label: 'Page' }, { key: 'gaps', label: 'Outstanding' }, { key: 'issues', label: 'Issues' },
  { key: 'sources', label: 'Sources' }, { key: 'corrections', label: 'Corrections' },
] as const;
type InspectorTab = (typeof INSPECTOR_TABS)[number]['key'];
/** Origins in the order the summary reads best; the backend supplies the counts. */
const ORIGIN_LABELS = [
  { key: 'extracted', label: 'extracted' }, { key: 'inferred', label: 'inferred' }, { key: 'ocr', label: 'via OCR' }, { key: 'computed', label: 'calculated' },
  { key: 'manual', label: 'entered by you' }, { key: 'ai_draft', label: 'AI drafts' }, { key: 'missing', label: 'not found' },
];
/** The marks the editor prints beside every value, taught once at the foot of the section list. */
const LEGEND = [
  { key: 'inferred', glyph: '~', label: 'inferred from a differently labelled source value' },
  { key: 'extracted', glyph: '●', label: 'extracted from a file' },
  { key: 'ocr', glyph: '◐', label: 'recovered by OCR' },
  { key: 'computed', glyph: 'ƒ', label: 'calculated' },
  { key: 'manual', glyph: '✎', label: 'entered by reviewer' },
  { key: 'ai_draft', glyph: '✱', label: 'AI draft — needs review' },
  { key: 'missing', glyph: '○', label: 'not found' },
  { key: 'conflict', glyph: '≠', label: 'sources disagree' },
];
const SEVERITY_MARK: Record<string, string> = { error: '✕', warning: '▲', info: 'ℹ' };

@Component({
  selector: 'app-review',
  standalone: true,
  imports: [FieldEditorComponent, TableEditorComponent, PagePreviewComponent],
  template: `
    @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
    @if (data(); as d) {
      <div class="workbench">
        <aside class="pane pane-nav" aria-label="Report sections">
          <div class="pane-head"><h2 class="pane-title">Sections · by printed page</h2></div>
          @for (s of d.sections; track s.key) {
            <button type="button" class="section-link" [class.active]="s.key === selected()" [attr.aria-current]="s.key === selected() ? 'true' : null" (click)="select(s.key)">
              <span class="title">{{ s.title }}</span>
              @if (attentionCount(s); as n) { <span class="badge"><span class="sr-only">, </span>{{ n }}<span class="sr-only"> need attention</span></span> }
              @else { <span class="badge ok" aria-hidden="true">✓</span> }
              <span class="pg" aria-hidden="true">p{{ s.page }}</span>
            </button>
          }
          <div class="prov-legend">
            <h2 class="pane-title">Provenance marks</h2>
            <ul class="plain">
              @for (m of legend; track m.key) {
                <li><span class="prov-mark prov-{{ m.key }}" aria-hidden="true">{{ m.glyph }}</span>{{ m.label }}</li>
              }
            </ul>
          </div>
        </aside>

        <section class="pane pane-main" aria-labelledby="section-heading">
          <div class="toolbar row">
            @if (section(); as s) {
              <h2 id="section-heading" tabindex="-1" #heading>{{ s.title }}</h2>
              <span class="muted small">page {{ s.page }} of {{ lastPage(d) }}</span>
            }
            <span class="spacer"></span>
            <label class="small"><input type="checkbox" [checked]="attentionOnly()" (change)="attentionOnly.set(!attentionOnly())" /> needs attention only</label>
            <button type="button" class="secondary small" (click)="rebuild()" [disabled]="saving()">↻ Rebuild from files</button>
            @if (health()?.llm_enabled) {
              <button type="button" class="secondary small ai" (click)="draft()" [disabled]="drafting()">{{ drafting() ? 'Drafting…' : '✱ Draft narratives with AI' }}</button>
            }
            <button type="button" class="small" [class.secondary]="!pending().size" (click)="save()" [disabled]="!pending().size || saving()">{{ saving() ? 'Saving…' : (pending().size ? 'Save · ' + pending().size : 'Saved') }}</button>
          </div>
          @if (d.narrative_error) { <p class="warn small" role="status">AI drafting: {{ d.narrative_error }}</p> }
          @if (section(); as s) {
            <div class="fields">
              @for (f of visibleFields(s); track f.path) { <app-field-editor [f]="f" (changed)="onChange($event)" /> }
            </div>
            @for (t of s.tables; track t.path) {
              <app-table-editor [t]="t" [attentionOnly]="attentionOnly()" (changed)="onChange($event)" (addRow)="addRow($event)" (deleteRow)="deleteRow($event)" />
            }
          }
          <p class="status small" role="status" aria-live="polite">{{ status() }}</p>
        </section>

        <aside class="pane pane-side" aria-label="Inspector">
          <div class="inspector-tabs" role="tablist" aria-label="Inspector">
            @for (t of inspectorTabs; track t.key) {
              <button type="button" role="tab" class="itab" [class.current]="t.key === inspector()"
                      [attr.aria-selected]="t.key === inspector()" (click)="selectInspector(t.key)">{{ t.label }}@if (count(t.key, d) !== null) { <span class="itab-n">· {{ count(t.key, d) }}</span> }</button>
            }
          </div>

          @switch (inspector()) {
            @case ('page') {
              @if (section(); as s) {
                <app-page-preview [url]="previewUrl()" [page]="s.preview_page" [pages]="d.preview_total_pages ?? 10" (refresh)="refreshPreview()" />
                <h3 class="panel-head">On this page</h3>
                <ul class="plain gap-list">
                  @for (g of pageGaps(); track g.path) {
                    <li><button type="button" class="gap" (click)="jumpTo(g.path)">
                      <span class="gap-head"><span class="prov-mark prov-missing" aria-hidden="true">○</span><span class="gap-label">{{ g.label }}</span><span class="jump">jump →</span></span>
                      <span class="gap-reason">{{ g.reason }}</span>
                    </button></li>
                  } @empty { <li class="ok small">✓ Nothing outstanding on this page.</li> }
                </ul>
                <ul class="plain small page-issues">
                  @for (i of pageIssues(); track $index) {
                    <li><button type="button" class="issue issue-{{ i.severity }} small" (click)="jump(i)" [disabled]="!i.path"><span class="sr-only">{{ i.severity }}: </span>{{ i.message }}</button></li>
                  }
                </ul>
              }
            }
            @case ('gaps') {
              <div class="completeness">
                @if (d.summary.completeness; as c) {
                  <h2 class="pane-title">{{ c.complete ? 'Complete' : c.gap_count + ' item' + (c.gap_count === 1 ? '' : 's') + ' outstanding' }}</h2>
                  <p class="small muted">A PDF can always be generated — it is stamped <strong>DRAFT</strong> until every item below is reviewed.@if (c.ai_drafts_pending) { {{ c.ai_drafts_pending }} AI draft{{ c.ai_drafts_pending === 1 ? '' : 's' }} still need review. }</p>
                  @for (grp of gapGroups(c.gaps); track grp.key) {
                    <div class="gap-group">
                      <div class="gap-group-head"><span class="gap-group-title">{{ grp.title }}</span><span class="muted">p{{ grp.page }} · {{ grp.items.length }} item{{ grp.items.length === 1 ? '' : 's' }}</span></div>
                      <ul class="plain gap-list">
                        @for (g of grp.items; track g.path) {
                          <li><button type="button" class="gap issue" (click)="jumpTo(g.path)">
                            <span class="gap-head"><span class="prov-mark prov-missing" aria-hidden="true">○</span><span class="gap-label"><span class="pg">p{{ g.page }}</span> {{ g.label }}</span><span class="jump">jump →</span></span>
                            <span class="gap-reason">{{ g.reason }}</span>
                          </button></li>
                        }
                      </ul>
                    </div>
                  }
                }
              </div>
            }
            @case ('issues') {
              <div class="issues">
                <ul class="plain">
                  @for (i of d.issues; track $index) {
                    <li><button type="button" class="issue issue-{{ i.severity }} small" (click)="jump(i)" [disabled]="!i.path">
                      <span class="issue-head"><span class="mark" aria-hidden="true">{{ severityMark(i.severity) }}</span>{{ i.severity }}@if (where(i, d); as w) { · {{ w }} }</span>
                      <span class="issue-msg">{{ i.message }}</span>
                    </button></li>
                  }
                </ul>
              </div>
            }
            @case ('sources') {
              <div class="prov-panel">
                @if (d.provenance; as pv) {
                  <p class="small muted">Where this report's values came from. The same trail is printed in Appendix A of the generated report.</p>
                  <ul class="plain">
                    @for (f of pv.files; track f.filename) {
                      <li><div class="src-name mono" [title]="f.filename">{{ f.filename }}</div>
                        <div class="src-row"><span class="muted small">{{ f.doc_labels.join('; ') }}</span>
                          @if (f.method !== 'native') { <span class="prov-tag prov-ocr">◐ OCR</span> }
                        </div>
                        @if (f.method !== 'native') { <div class="muted small">text recovered by vision OCR@if (f.ocr_pages.length) { on page{{ f.ocr_pages.length === 1 ? '' : 's' }} {{ f.ocr_pages.join(', ') }} }@if (f.ocr_confidence != null) { ({{ (f.ocr_confidence * 100).toFixed(0) }}% confidence) }</div> }
                      </li>
                    } @empty { <li class="muted">No source file has been consolidated yet.</li> }
                  </ul>
                  <div class="counts small">
                    @for (c of originCounts(pv.counts); track c.key) {
                      <span><span class="prov-dot prov-{{ c.key }}"></span> {{ c.count }} {{ c.label }}</span>
                    }
                  </div>
                }
              </div>
            }
            @case ('corrections') {
              <div class="corrections">
                @if (overrides(); as ov) {
                  <p class="small muted">Reviewer overrides stored on this report. Resetting restores the extracted value.</p>
                  <ul class="plain small">
                    @for (e of entries(); track e.path) {
                      <li class="row between"><span class="prov-mark prov-manual" aria-hidden="true">✎</span><code>{{ e.path }}</code> <span class="muted">{{ e.text }}</span>
                        <button type="button" class="link danger small" (click)="resetOverride(e.path)" [attr.aria-label]="'Reset correction ' + e.path">reset</button></li>
                    } @empty { <li class="muted">No stored corrections yet. Edit any field and save — it will appear here, resettable.</li> }
                  </ul>
                  @if (entries().length) { <button type="button" class="link danger small" (click)="resetAll()">Reset all corrections</button> }
                }
              </div>
            }
          }
        </aside>
      </div>
    } @else if (!error()) { <p class="muted" role="status">Loading…</p> }`,
})
export class ReviewComponent {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private shell = inject(ShellStore);
  protected pid = this.route.snapshot.paramMap.get('id')!;
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  heading = viewChild<ElementRef<HTMLElement>>('heading');
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
  inspectorTabs = INSPECTOR_TABS;
  legend = LEGEND;
  inspector = signal<InspectorTab>('page');
  /** Bumped after a save so the preview re-requests and shows the corrected page. */
  private previewToken = signal(0);
  previewUrl = computed(() => `${this.api.previewUrl(this.pid)}&r=${this.previewToken()}`);
  /** The issues that land on the page being edited — several sections can share one printed page. */
  pageIssues = computed<Issue[]>(() => {
    const d = this.data(), s = this.section();
    if (!d || !s) return [];
    const keys = new Set(d.sections.filter((x) => x.page === s.page).map((x) => x.key));
    return d.issues.filter((i) => i.path && keys.has(i.path.split('.')[0]));
  });
  /** The outstanding items that print on the page being edited. */
  pageGaps = computed<Gap[]>(() => {
    const d = this.data(), s = this.section();
    if (!d || !s) return [];
    return (d.summary.completeness?.gaps ?? []).filter((g) => g.page === s.page);
  });

  constructor() {
    // The pending edits die with this screen, so the hold they put on the Report tab must die too.
    this.destroy.onDestroy(() => this.shell.blocked.set(false));
    this.api.getProject(this.pid).subscribe({ next: (p) => this.shell.setProject(p), error: (e) => this.fail(errorText(e)) });
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => undefined });
    this.load();
  }

  load(): void {
    this.api.reportData(this.pid).subscribe({
      next: (d) => {
        this.data.set(d);
        this.shell.gaps.set(d.summary.completeness?.gap_count ?? null);
        this.shell.origins.set(d.provenance?.counts ?? null);
        if (d.narrative_status === 'running') this.watchNarratives();
      },
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
  /** The last printed page, so the heading can say "page 2 of 10" without a second request. */
  lastPage(d: ReportDataUi): number { return d.sections.reduce((n, s) => Math.max(n, s.page), 0); }
  severityMark(s: string): string { return SEVERITY_MARK[s] ?? 'ℹ'; }
  /** An issue's home, as the reader knows it: the section's title and printed page. */
  where(i: Issue, d: ReportDataUi): string | null {
    if (!i.path) return null;
    const s = d.sections.find((x) => x.key === i.path!.split('.')[0]);
    return s ? `${s.title} · p${s.page}` : null;
  }
  /** Outstanding items bucketed by the section they belong to, in section order. */
  gapGroups(gaps: Gap[]): { key: string; title: string; page: number; items: Gap[] }[] {
    const sections = this.data()?.sections ?? [];
    const out = new Map<string, { key: string; title: string; page: number; items: Gap[] }>();
    for (const g of gaps) {
      const s = sections.find((x) => x.key === g.group);
      const entry = out.get(g.group) ?? { key: g.group, title: s?.title ?? g.group, page: s?.page ?? g.page, items: [] };
      entry.items.push(g);
      out.set(g.group, entry);
    }
    return [...out.values()];
  }

  refreshPreview(): void { this.previewToken.update((v) => v + 1); }

  /** The number beside a tab, or null for the tabs that do not carry one. */
  count(tab: string, d: ReportDataUi): number | null {
    if (tab === 'gaps') return d.summary.completeness?.gap_count ?? 0;
    if (tab === 'issues') return d.issues.length;
    if (tab === 'corrections') return this.entries().length;
    return null;
  }

  selectInspector(tab: InspectorTab): void {
    this.inspector.set(tab);
    if (tab === 'corrections' && !this.overrides()) this.fetchOverrides();
  }

  select(key: string): void { this.selected.set(key); }
  onChange(ch: FieldChange): void {
    const m = new Map(this.pending());
    m.set(ch.path, ch.value);
    this.pending.set(m);
    this.shell.blocked.set(true);
  }

  save(): void {
    const changes = Array.from(this.pending().entries()).map(([path, value]) => ({ path, value }));
    if (!changes.length) return;
    this.saving.set(true);
    this.error.set(null);
    this.api.patchReportData(this.pid, { changes }).subscribe({
      next: (d) => { this.data.set(d); this.pending.set(new Map()); this.shell.blocked.set(false); this.saving.set(false); this.status.set(`Saved ${changes.length} change${changes.length === 1 ? '' : 's'}.`); this.overrides.set(null); this.refreshPreview(); },
      error: (e) => { this.saving.set(false); this.fail('Not saved. ' + errorText(e)); },
    });
  }
  addRow(table: string): void {
    this.api.patchReportData(this.pid, { add_rows: [{ table, values: {} }] }).subscribe({ next: (d) => { this.data.set(d); this.status.set('Row added.'); this.refreshPreview(); }, error: (e) => this.fail(errorText(e)) });
  }
  deleteRow(ev: { table: string; key: string }): void {
    if (!confirm('Remove this row from the report?')) return;
    this.api.patchReportData(this.pid, { delete_rows: [ev] }).subscribe({ next: (d) => { this.data.set(d); this.status.set('Row removed.'); this.refreshPreview(); }, error: (e) => this.fail(errorText(e)) });
  }
  rebuild(): void {
    if (this.pending().size && !confirm('Unsaved edits will be lost. Rebuild anyway?')) return;
    this.saving.set(true);
    this.api.rebuildReportData(this.pid).subscribe({
      next: (d) => { this.data.set(d); this.pending.set(new Map()); this.shell.blocked.set(false); this.saving.set(false); this.status.set('Rebuilt from the processed files; your saved corrections were kept.'); this.refreshPreview(); },
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

  fetchOverrides(): void {
    this.api.overrides(this.pid).subscribe({ next: (ov) => this.overrides.set(ov), error: (e) => this.fail(errorText(e)) });
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
