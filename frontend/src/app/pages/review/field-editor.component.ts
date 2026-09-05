import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UiField } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';

export interface FieldChange { path: string; value: unknown; }
let counter = 0;

@Component({
  selector: 'app-field-editor',
  standalone: true,
  imports: [FormsModule, StatusChipComponent],
  template: `
    <div class="field" [class.attention]="needsAttention()">
      <div class="field-head">
        <label [for]="id">{{ f().label }}</label>
        <app-status-chip [status]="f().status" />
        @if (f().source; as s) {
          <button type="button" class="link small" (click)="showSource.set(!showSource())" [attr.aria-expanded]="showSource()" [attr.aria-controls]="id + '-src'" [attr.aria-label]="'Show source of ' + f().label">source</button>
        }
        @if (f().override !== null && f().override !== undefined) {
          <button type="button" class="link small" (click)="reset()" [attr.aria-label]="'Reset ' + f().label + ' to the extracted value'">reset</button>
        }
      </div>
      @switch (f().kind) {
        @case ('longtext') { <textarea [id]="id" rows="4" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" [attr.aria-label]="f().label" [attr.aria-describedby]="describedBy()"></textarea> }
        @case ('date') { <input [id]="id" type="date" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" [attr.aria-label]="f().label" [attr.aria-describedby]="describedBy()" /> }
        @case ('text') { <input [id]="id" type="text" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" [attr.aria-label]="f().label" [attr.aria-describedby]="describedBy()" /> }
        @default { <input [id]="id" type="number" step="any" [disabled]="f().readonly" [ngModel]="numberText()" (ngModelChange)="editNumber($event)" [attr.aria-label]="f().label + (f().kind === 'percent' ? ' (percent)' : '')" [attr.aria-describedby]="describedBy()" />
          @if (f().kind === 'percent') { <span class="unit" aria-hidden="true">%</span> } }
      }
      @if (f().alternatives.length) {
        <fieldset class="alts small">
          <legend class="muted">Sources disagree. Choose:</legend>
          <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(f().value)" (change)="choose(f().value)" /> {{ fmt(f().value) }} <span class="muted">({{ f().source?.filename }})</span></label>
          @for (a of f().alternatives; track $index) {
            <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(a.value)" (change)="choose(a.value)" /> {{ fmt(a.value) }} <span class="muted">({{ a.source?.filename }}{{ a.note ? ', ' + a.note : '' }})</span></label>
          }
        </fieldset>
      }
      @if (f().note) { <div class="small muted" [id]="id + '-note'">{{ f().note }}</div> }
      @if (showSource() && f().source; as s) {
        <div class="source small" [id]="id + '-src'"><strong>{{ s.filename ?? 'computed' }}</strong> {{ s.locator }} @if (s.text) { <span class="muted">· "{{ s.text }}"</span> }</div>
      }
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
  describedBy = computed(() => (this.f().note ? this.id + '-note' : null));

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
