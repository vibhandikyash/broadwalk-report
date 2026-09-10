import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { ShellStore } from '../../core/shell.store';
import { backendDown, detail, detail422, uiData, uiField } from '../../testing/fixtures';
import { routeStub } from '../../testing/fixtures';
import { FieldEditorComponent } from './field-editor.component';
import { ReviewComponent } from './review.component';

const tick = () => new Promise((r) => setTimeout(r, 0));
/** Click one of the inspector's tabs by its visible name. */
const inspector = (el: HTMLElement, name: string) => {
  const tab = Array.from(el.querySelectorAll('.inspector-tabs button') as NodeListOf<HTMLButtonElement>)
    .find((b) => b.textContent!.includes(name));
  if (!tab) throw new Error(`no inspector tab named ${name}`);
  tab.click();
  return tab;
};

function setup(api: Partial<Record<keyof ApiService, unknown>>) {
  const base = { getProject: () => of(detail()), health: () => of({ ok: true, llm_enabled: false, llm_provider: null, pdf_renderer: true, workers: 3 }),
                 reportData: () => of(uiData()), previewUrl: () => '/api/projects/p1/report/preview?t=1' };
  TestBed.configureTestingModule({ providers: [provideRouter([]), routeStub(), { provide: ApiService, useValue: { ...base, ...api } }] });
  const fixture = TestBed.createComponent(ReviewComponent);
  fixture.detectChanges();
  return fixture;
}

describe('ReviewComponent', () => {
  it('renders the sections, marks the current one and disables calculated fields', async () => {
    const fixture = setup({});
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelectorAll('.section-link').length).toBe(5);
    expect(el.querySelector('.section-link[aria-current="true"]')!.textContent).toContain('Property');
    fixture.componentInstance.select('commentary');
    fixture.detectChanges();
    await tick();  // ngModel applies [disabled] asynchronously
    fixture.detectChanges();
    expect((el.querySelector('#section-heading') as HTMLElement).textContent).toContain('Commentary');
    expect((el.querySelector('input[aria-label="NOI actual"]') as HTMLInputElement).disabled).toBe(true);
  });

  it('collects edits, saves them in one batch and announces the result', () => {
    const patch = vi.fn(() => of(uiData()));
    const fixture = setup({ patchReportData: patch });
    const c = fixture.componentInstance;
    c.onChange({ path: 'property.fields.units', value: 340 });
    c.onChange({ path: 'financing.fields.lender', value: 'Fannie Mae' });
    c.onChange({ path: 'property.fields.units', value: 341 });
    fixture.detectChanges();
    expect(c.pending().size).toBe(2);
    expect(fixture.nativeElement.querySelector('.toolbar button:last-of-type').textContent).toContain('Save · 2');
    expect(TestBed.inject(ShellStore).blocked()).toBe(true);  // the header holds the Report tab
    c.save();
    fixture.detectChanges();
    expect(patch).toHaveBeenCalledWith('p1', { changes: [{ path: 'property.fields.units', value: 341 }, { path: 'financing.fields.lender', value: 'Fannie Mae' }] });
    expect(c.pending().size).toBe(0);
    expect(fixture.nativeElement.querySelector('[role="status"]').textContent).toContain('Saved 2 changes');
    expect(TestBed.inject(ShellStore).blocked()).toBe(false);  // reachable again once saved
  });

  it('keeps the edits and focuses the message when the backend rejects them', async () => {
    const fixture = setup({ patchReportData: () => throwError(() => detail422('property.fields.units: Units: expected a whole number')) });
    const c = fixture.componentInstance;
    c.onChange({ path: 'property.fields.units', value: 12.5 });
    c.save();
    fixture.detectChanges();
    await tick();
    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('Not saved. property.fields.units: Units: expected a whole number');
    expect(document.activeElement).toBe(alert);
    expect(c.pending().size).toBe(1);
    expect(c.saving()).toBe(false);
  });

  it('resets a field, picks a conflict alternative and converts percentages', async () => {
    const fixture = setup({});
    const c = fixture.componentInstance;
    c.select('capital');
    fixture.detectChanges();
    const radios = fixture.nativeElement.querySelectorAll('.alts input[type="radio"]') as NodeListOf<HTMLInputElement>;
    expect(radios.length).toBe(2);
    radios[1].click();
    expect(c.pending().get('capital.fields.purchase_price')).toBe(38100000);
    const fe = TestBed.createComponent(FieldEditorComponent);
    fe.componentRef.setInput('f', uiField({ path: 'x.fields.rate', kind: 'percent', value: 0.0523, effective: 0.0523, override: 0.0523, status: 'manual' }));
    fe.detectChanges();
    await tick();  // ngModel writes the value asynchronously
    fe.detectChanges();
    const emitted: unknown[] = [];
    fe.componentInstance.changed.subscribe((e) => emitted.push(e));
    expect((fe.nativeElement.querySelector('input[type="number"]') as HTMLInputElement).value).toBe('5.23');
    fe.componentInstance.editNumber('6');
    fe.componentInstance.reset();
    expect(emitted).toEqual([{ path: 'x.fields.rate', value: 0.06 }, { path: 'x.fields.rate', value: null }]);
    expect(fe.nativeElement.querySelector('button[aria-label^="Reset"]')).not.toBeNull();
  });

  it('adds and deletes rows through the API', () => {
    const patch = vi.fn(() => of(uiData()));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const fixture = setup({ patchReportData: patch });
    const c = fixture.componentInstance;
    c.select('underwriting');
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[aria-label^="Add row"]') as HTMLButtonElement).click();
    expect(patch).toHaveBeenLastCalledWith('p1', { add_rows: [{ table: 'underwriting.tables.budget', values: {} }] });
    (fixture.nativeElement.querySelector('button[aria-label="Delete row Roofs"]') as HTMLButtonElement).click();
    expect(patch).toHaveBeenLastCalledWith('p1', { delete_rows: [{ table: 'underwriting.tables.budget', key: 'manual-1' }] });
  });

  it('jumps from an issue to its section and moves focus to the heading', async () => {
    const fixture = setup({});
    inspector(fixture.nativeElement, 'Issues');
    fixture.detectChanges();
    const buttons = fixture.nativeElement.querySelectorAll('.issues button.issue') as NodeListOf<HTMLButtonElement>;
    expect(buttons.length).toBe(2);
    expect(buttons[1].disabled).toBe(true);  // no path to jump to
    buttons[0].click();
    fixture.detectChanges();
    await tick();
    expect(fixture.componentInstance.selected()).toBe('financing');
    expect(document.activeElement).toBe(fixture.nativeElement.querySelector('#section-heading'));
  });

  it('lists stored corrections and resets one through the recovery endpoint', () => {
    const reset = vi.fn(() => of({ fields: {} }));
    const fixture = setup({ overrides: () => of({ fields: { 'property.fields.units': 'lots' }, rows: { 'underwriting.tables.budget': { 'manual-1': {} } }, deleted_rows: { 'submarket.tables.comps': ['westchase'] }, ai_drafts: { 'capex.fields.narrative': 'x' } }), resetOverrides: reset });
    inspector(fixture.nativeElement, 'Corrections');
    fixture.detectChanges();
    const items = Array.from(fixture.nativeElement.querySelectorAll('.corrections li code') as NodeListOf<HTMLElement>).map((c) => c.textContent);
    expect(items).toEqual(['property.fields.units', 'underwriting.tables.budget.rows.manual-1', 'submarket.tables.comps.deleted', 'capex.fields.narrative']);
    (fixture.nativeElement.querySelector('button[aria-label="Reset correction property.fields.units"]') as HTMLButtonElement).click();
    expect(reset).toHaveBeenCalledWith('p1', { paths: ['property.fields.units'] });
  });

  it('lists completeness gaps by page and jumps to the section of a gap', async () => {
    const fixture = setup({});
    const el: HTMLElement = fixture.nativeElement;
    inspector(el, 'Outstanding');
    fixture.detectChanges();
    const panel = el.querySelector('.completeness') as HTMLElement;
    expect(panel.querySelector('.pane-title')!.textContent).toContain('2 items outstanding');
    const buttons = panel.querySelectorAll('button.issue') as NodeListOf<HTMLButtonElement>;
    expect(buttons.length).toBe(2);
    expect(buttons[0].textContent).toContain('p4');
    buttons[0].click();
    fixture.detectChanges();
    await tick();
    expect(fixture.componentInstance.selected()).toBe('financing');
    expect(document.activeElement).toBe(el.querySelector('#section-heading'));
  });

  it('states under every field where its value came from, and flags OCR in a table cell', async () => {
    const fixture = setup({});
    const el: HTMLElement = fixture.nativeElement;
    const line = el.querySelector('.field .prov') as HTMLElement;
    expect(line.textContent).toContain('Extracted');
    expect(line.textContent).toContain("rr.xlsx · sheet 'RR' summary block");
    // a missing value explains itself rather than showing a bare dash
    fixture.componentInstance.select('financing');
    fixture.detectChanges();
    const missing = el.querySelector('.field .prov') as HTMLElement;
    expect(missing.textContent).toContain('Not found');
    expect(missing.textContent).toContain('no such file was uploaded');
    expect(missing.querySelector('.prov-dot.prov-missing')).not.toBeNull();
    // table cells get the compact tag with the full sentence as its tooltip
    fixture.componentInstance.select('underwriting');
    fixture.detectChanges();
    const tag = el.querySelector('table.cells .prov-tag') as HTMLElement;
    expect(tag.textContent).toContain('src');
    expect(tag.getAttribute('title')).toContain('Extracted');
  });

  it('summarises the origins and names the files that needed OCR', () => {
    const fixture = setup({});
    inspector(fixture.nativeElement, 'Sources');
    fixture.detectChanges();
    const panel = fixture.nativeElement.querySelector('.prov-panel') as HTMLElement;
    expect(panel.querySelector('.counts')!.textContent).toContain('via OCR');
    const items = panel.querySelectorAll('li');
    expect(items.length).toBe(2);
    expect(items[1].textContent).toContain('scan.pdf');
    expect(items[1].querySelector('.prov-tag.prov-ocr')).not.toBeNull();
    expect(items[1].textContent).toContain('on page 1');
    expect(items[1].textContent).toContain('94% confidence');
    expect(items[0].querySelector('.prov-tag.prov-ocr')).toBeNull();
  });

  it('lifts the header’s hold when the review screen goes away with edits pending', () => {
    const fixture = setup({});
    const shell = TestBed.inject(ShellStore);
    fixture.componentInstance.onChange({ path: 'property.fields.units', value: 340 });
    expect(shell.blocked()).toBe(true);
    fixture.destroy();  // the pending edits are gone, so the Report tab must not stay held
    expect(shell.blocked()).toBe(false);
  });

  it('tells the header to hold the report while edits are unsaved', () => {
    const fixture = setup({});
    const shell = TestBed.inject(ShellStore);
    const save = () => fixture.nativeElement.querySelector('.toolbar button:last-of-type') as HTMLButtonElement;
    expect(shell.blocked()).toBe(false);
    expect(save().disabled).toBe(true);
    expect(save().textContent).toContain('Saved');
    fixture.componentInstance.onChange({ path: 'property.fields.units', value: 340 });
    fixture.detectChanges();
    expect(shell.blocked()).toBe(true);  // the Report tab is held until this is saved or discarded
    expect(save().disabled).toBe(false);
  });

  it('keeps the section list free of diagnostics and puts them behind inspector tabs', () => {
    const fixture = setup({});
    const el: HTMLElement = fixture.nativeElement;
    const nav = el.querySelector('.pane-nav')!;
    expect(nav.querySelectorAll('.section-link').length).toBe(5);
    for (const cls of ['.completeness', '.issues', '.corrections', '.prov-panel']) {
      expect(nav.querySelector(cls)).toBeNull();  // navigation only; diagnostics live in the inspector
    }
    const tabs = Array.from(el.querySelectorAll('.inspector-tabs button') as NodeListOf<HTMLButtonElement>);
    expect(tabs.map((b) => b.textContent!.replace(/[·\d]/g, '').trim())).toEqual(['Page', 'Outstanding', 'Issues', 'Sources', 'Corrections']);
    expect(tabs[1].textContent).toContain('2');   // outstanding count on the tab
    expect(tabs[2].textContent).toContain('2');   // issue count on the tab
    expect(el.querySelector('.page-view')).not.toBeNull();  // Page is the tab you land on
    inspector(el, 'Issues');
    fixture.detectChanges();
    expect(el.querySelector('.page-view')).toBeNull();
    expect(el.querySelector('.issues button.issue')).not.toBeNull();
    expect(el.querySelector('.inspector-tabs button.current')!.textContent).toContain('Issues');
  });

  it('explains an unreachable backend', () => {
    const fixture = setup({ reportData: () => throwError(() => backendDown), getProject: () => throwError(() => backendDown) });
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('not reachable');
  });
});
