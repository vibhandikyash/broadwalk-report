import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UiField } from '../../core/models';

export interface FieldChange { path: string; value: unknown; }
let counter = 0;

/** One mark per origin, so a glance down the left edge of the editor says where the page came from.
 *  A conflict is a status rather than an origin, and gets its own mark ahead of the origin's. */
const MARKS: Record<string, string> = {
  inferred: '~',
  extracted: '●', ocr: '◐', computed: 'ƒ', manual: '✎', ai_draft: '✱', missing: '○', conflict: '≠',
};

@Component({
  selector: 'app-field-editor',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="field" [class.attention]="needsAttention()">
      <span class="prov-mark prov-{{ mark().key }}" aria-hidden="true" [title]="mark().title">{{ mark().glyph }}</span>
      <div class="field-head">
        <label [for]="id">{{ f().label }}</label>
        <div class="field-tag prov-{{ mark().key }}">{{ mark().title }}</div>
        @if (f().override !== null && f().override !== undefined) {
          <button type="button" class="link small" (click)="reset()" [attr.aria-label]="'Reset ' + f().label + ' to the extracted value'">reset</button>
        }
      </div>
      <div class="field-body">
        @if (f().alternatives.length) {
          <fieldset class="alts small">
            <legend>≠ two sources disagree — choose one</legend>
            <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(f().value)" (change)="choose(f().value)" /> <strong class="tabular">{{ fmt(f().value) }}</strong> <span class="muted mono">{{ f().source?.filename }}</span></label>
            @for (a of f().alternatives; track $index) {
              <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(a.value)" (change)="choose(a.value)" /> <strong class="tabular">{{ fmt(a.value) }}</strong> <span class="muted mono">{{ a.source?.filename }}{{ a.note ? ' · ' + a.note : '' }}</span></label>
            }
          </fieldset>
        }
        @switch (f().kind) {
          @case ('longtext') { <textarea [id]="id" rows="3" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" [attr.aria-label]="f().label" [attr.aria-describedby]="describedBy()" [attr.placeholder]="placeholder()"></textarea> }
          @case ('date') { <input [id]="id" type="date" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" [attr.aria-label]="f().label" [attr.aria-describedby]="describedBy()" /> }
          @case ('text') { <input [id]="id" type="text" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" [attr.aria-label]="f().label" [attr.aria-describedby]="describedBy()" [attr.placeholder]="placeholder()" /> }
          @default { <input [id]="id" type="number" step="any" [disabled]="f().readonly" [ngModel]="numberText()" (ngModelChange)="editNumber($event)" [attr.aria-label]="f().label + (f().kind === 'percent' ? ' (percent)' : '')" [attr.aria-describedby]="describedBy()" [attr.placeholder]="placeholder()" />
            @if (f().kind === 'percent') { <span class="unit" aria-hidden="true">%</span> } }
        }
        @if (f().note) { <div class="small muted" [id]="id + '-note'">{{ f().note }}</div> }
        @if (p(); as pv) {
          @if (compact()) {
            <span class="prov-tag prov-{{ pv.origin }}" [title]="pv.label + ' — ' + pv.detail"><span class="sr-only">{{ pv.label }}: </span>{{ tag(pv.origin) }}</span>
          } @else {
            @if (pv.origin === 'missing' && pv.reason) { <div class="field-reason">{{ pv.reason }}</div> }
            <button type="button" class="prov-toggle" (click)="showSource.set(!showSource())"
                    [attr.aria-expanded]="showSource()" [attr.aria-controls]="id + '-src'"
                    [attr.aria-label]="(showSource() ? 'Hide' : 'Show') + ' where ' + f().label + ' came from'">
              <span class="caret" aria-hidden="true">{{ showSource() ? '▼' : '▶' }}</span>
              <span class="prov" [id]="id + '-prov'">
                <span class="prov-dot prov-{{ pv.origin }}" aria-hidden="true"></span><span class="prov-label">{{ pv.label }}</span>
                @if (pv.ocr) { <span class="prov-tag prov-ocr">OCR</span> }
                <span class="prov-detail">{{ pv.detail }}</span>
              </span>
            </button>
            @if (showSource()) {
              <div class="source" [id]="id + '-src'">
                {{ pv.detail }}
                @if (f().source; as s) { @if (s.text) { <div>source text: “{{ s.text }}”</div> } }
                @if (pv.doc_label) { <div>recognised as {{ pv.doc_label }}</div> }
                @if (pv.ocr) { <div style="color: var(--p-oc)">◐ recovered by vision OCR@if (pv.ocr_confidence != null) { · {{ (pv.ocr_confidence * 100).toFixed(0) }}% confidence }</div> }
              </div>
            }
          }
        }
      </div>
    </div>`,
})
export class FieldEditorComponent {
  f = input.required<UiField>();
  compact = input(false);
  changed = output<FieldChange>();
  showSource = signal(false);
  readonly id = 'f-' + (++counter).toString(36);

  needsAttention = computed(() => (this.f().status === 'missing' && this.f().effective == null) || this.f().status === 'conflict' || this.f().status === 'ai_draft');
  text = computed(() => (this.f().effective == null ? '' : String(this.f().effective)));
  numberText = computed(() => {
    const v = this.f().effective;
    if (v == null || v === '') return '';
    return this.f().kind === 'percent' ? String(Math.round(Number(v) * 1e6) / 1e4) : String(v);
  });
  /** Where this value came from, or why it is absent; the backend answers for every field. */
  p = computed(() => this.f().provenance);
  placeholder = computed(() => (this.f().status === 'missing' && this.f().effective == null ? 'enter value…' : null));
  describedBy = computed(() => [this.f().note ? this.id + '-note' : null, this.compact() ? null : this.id + '-prov'].filter(Boolean).join(' ') || null);
  mark = computed(() => {
    const key = this.f().status === 'conflict' ? 'conflict' : this.p().origin;
    return { key, glyph: MARKS[key] ?? '·', title: this.f().status === 'conflict' ? 'Sources disagree' : this.p().label };
  });
  /** Compact table cells have no room for a sentence: a two-letter tag carries the origin, the full text is the tooltip. */
  tag(origin: string): string {
    return { extracted: 'src', inferred: 'infer', ocr: 'OCR', computed: 'calc', manual: 'you', ai_draft: 'ai', missing: 'none' }[origin] ?? origin;
  }

  edit(value: string): void { this.changed.emit({ path: this.f().path, value: value === '' ? null : value }); }
  editNumber(value: string | number | null): void {
    if (value === '' || value === null || value === undefined) { this.changed.emit({ path: this.f().path, value: null }); return; }
    const n = Number(value);
    this.changed.emit({ path: this.f().path, value: this.f().kind === 'percent' ? n / 100 : n });
  }
  reset(): void { this.changed.emit({ path: this.f().path, value: null }); }
  choose(v: unknown): void { this.changed.emit({ path: this.f().path, value: v }); }
  isChosen(v: unknown): boolean { return this.f().effective === v; }
  fmt(v: unknown): string { return typeof v === 'number' ? v.toLocaleString() : String(v ?? '—'); }
}
