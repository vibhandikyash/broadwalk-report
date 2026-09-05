import { Component, input, output } from '@angular/core';
import { UiRow, UiTable } from '../../core/models';
import { FieldChange, FieldEditorComponent } from './field-editor.component';

@Component({
  selector: 'app-table-editor',
  standalone: true,
  imports: [FieldEditorComponent],
  template: `
    <div class="table-block">
      <div class="row between"><h3>{{ t().title }}</h3>
        @if (t().editable_rows) { <button type="button" class="link" (click)="addRow.emit(t().path)" [attr.aria-label]="'Add row to ' + t().title">+ add row</button> }
      </div>
      <div class="scroll">
      <table class="grid cells">
        <caption class="sr-only">{{ t().title }}</caption>
        <thead><tr><th scope="col">Row</th>@for (c of t().columns; track c.key) { <th scope="col">{{ c.label }}</th> }<th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>
          @for (r of rows(); track r.key) {
            <tr [class.subject]="r.subject">
              <th scope="row" class="rowlabel">{{ r.label }} @if (r.manual) { <span class="chip chip-manual">added</span> }</th>
              @for (cell of r.cells; track cell.path) {
                <td><app-field-editor [f]="cell" [compact]="true" (changed)="changed.emit($event)" /></td>
              }
              <td class="r">@if (t().editable_rows || r.manual) { <button type="button" class="link danger small" (click)="deleteRow.emit({ table: t().path, key: r.key })" [attr.aria-label]="'Delete row ' + r.label">delete</button> }</td>
            </tr>
          } @empty { <tr><td [attr.colspan]="t().columns.length + 2" class="muted">No rows extracted.@if (t().editable_rows) { Add rows manually.}</td></tr> }
          @if (t().totals.length) {
            <tr class="totals"><th scope="row" class="rowlabel">Total</th>
              @for (c of t().columns; track c.key) {
                <td>@if (totalFor(c.key); as cell) { <app-field-editor [f]="cell" [compact]="true" (changed)="changed.emit($event)" /> }</td>
              }<td></td></tr>
          }
        </tbody>
      </table>
      </div>
    </div>`,
})
export class TableEditorComponent {
  t = input.required<UiTable>();
  attentionOnly = input(false);
  changed = output<FieldChange>();
  addRow = output<string>();
  deleteRow = output<{ table: string; key: string }>();

  rows(): UiRow[] {
    if (!this.attentionOnly()) return this.t().rows;
    return this.t().rows.filter((r) => r.cells.some((c) => (c.status === 'missing' && c.effective == null) || c.status === 'conflict'));
  }
  totalFor(key: string) { return this.t().totals.find((c) => c.key === key) ?? null; }
}
