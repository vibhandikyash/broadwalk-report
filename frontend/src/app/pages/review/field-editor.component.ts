import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UiField } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';

export interface FieldChange { path: string; value: unknown; }

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
          <button type="button" class="link small" (click)="showSource.set(!showSource())" title="Where did this value come from?">source</button>
        }
        @if (f().override !== null && f().override !== undefined) {
          <button type="button" class="link small" (click)="reset()">reset</button>
        }
      </div>
      @switch (f().kind) {
        @case ('longtext') { <textarea [id]="id" rows="4" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)"></textarea> }
        @case ('date') { <input [id]="id" type="date" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" /> }
        @case ('text') { <input [id]="id" type="text" [disabled]="f().readonly" [ngModel]="text()" (ngModelChange)="edit($event)" /> }
        @default { <input [id]="id" type="number" step="any" [disabled]="f().readonly" [ngModel]="numberText()" (ngModelChange)="editNumber($event)" />
          @if (f().kind === 'percent') { <span class="unit">%</span> } }
      }
      @if (f().alternatives.length) {
        <div class="alts small">
          <span class="muted">Sources disagree. Choose:</span>
          <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(f().value)" (change)="choose(f().value)" /> {{ fmt(f().value) }} <span class="muted">({{ f().source?.filename }})</span></label>
          @for (a of f().alternatives; track $index) {
            <label><input type="radio" [name]="id + '-alt'" [checked]="isChosen(a.value)" (change)="choose(a.value)" /> {{ fmt(a.value) }} <span class="muted">({{ a.source?.filename }}{{ a.note ? ', ' + a.note : '' }})</span></label>
          }
        </div>
      }
      @if (f().note) { <div class="small muted">{{ f().note }}</div> }
      @if (showSource() && f().source; as s) {
        <div class="source small"><strong>{{ s.filename ?? 'computed' }}</strong> {{ s.locator }} @if (s.text) { <span class="muted">· "{{ s.text }}"</span> }</div>
      }
    </div>`,
})
export class FieldEditorComponent {
  f = input.required<UiField>();
  compact = input(false);
  changed = output<FieldChange>();
  showSource = signal(false);
  private counter = Math.random().toString(36).slice(2, 8);
  get id(): string { return 'f-' + this.counter; }

  needsAttention = computed(() => (this.f().status === 'missing' && this.f().effective == null) || this.f().status === 'conflict' || this.f().status === 'ai_draft');
  text = computed(() => (this.f().effective == null ? '' : String(this.f().effective)));
  numberText = computed(() => {
    const v = this.f().effective;
    if (v == null || v === '') return '';
    return this.f().kind === 'percent' ? String(Math.round(Number(v) * 1e6) / 1e4) : String(v);
  });

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
