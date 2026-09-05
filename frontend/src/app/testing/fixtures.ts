import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { ProjectDetail, ProjectFile, Report, ReportDataUi, UiField, UiSection } from '../core/models';

export function routeStub(id = 'p1') {
  return { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id }) } } };
}

export function file(over: Partial<ProjectFile> = {}): ProjectFile {
  return {
    id: 'f1', project_id: 'p1', original_filename: 'fin.xlsx', ext: '.xlsx', size: 2048, status: 'processed', error: null,
    parts: [{ doc_type: 'yardi_budget_comparison', confidence: 0.9, locator: "sheet 'Report1'", warnings: [] }],
    doc_type_override: null, ignored: false, uploaded_at: '2026-09-05T00:00:00', processed_at: '2026-09-05T00:00:01', ...over,
  };
}

export function report(over: Partial<Report> = {}): Report {
  return { id: 'r1', project_id: 'p1', version: 1, status: 'done', error: null, created_at: '2026-09-05T00:00:00', has_pdf: true, ...over };
}

export function detail(over: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: 'p1', name: 'Boardwalk', created_at: '2026-09-05T00:00:00', updated_at: '2026-09-05T00:00:00', files: [file()], reports: [],
    stage: 'review', report_built: true, processing: [], assets: { cover: false, logo: false }, ...over,
  };
}

export function uiField(over: Partial<UiField> = {}): UiField {
  return {
    path: 'property.fields.units', key: 'units', label: 'Units', kind: 'integer', value: 338, override: null, effective: 338, status: 'extracted',
    source: { filename: 'rr.xlsx', locator: "sheet 'RR' summary block", text: 'Totals' }, alternatives: [], note: null, readonly: false, ...over,
  };
}

export function uiData(over: Partial<ReportDataUi> = {}): ReportDataUi {
  const units = uiField();
  const lender = uiField({ path: 'financing.fields.lender', key: 'lender', label: 'Lender', kind: 'text', value: null, effective: null, status: 'missing', source: null });
  const price = uiField({
    path: 'capital.fields.purchase_price', key: 'purchase_price', label: 'Purchase price', kind: 'money', value: 48000000, effective: 48000000, status: 'conflict',
    alternatives: [{ value: 38100000, source: { filename: 'costar.pdf' }, note: 'CoStar recorded sale price' }],
  });
  const noi = uiField({ path: 'commentary.fields.noi_actual', key: 'noi_actual', label: 'NOI actual', kind: 'money', value: 550, effective: 550, status: 'derived', readonly: true, source: null });
  const sections: UiSection[] = [
    { key: 'property', title: 'Property', page: 1, fields: [units], tables: [] },
    { key: 'capital', title: 'Capital Summary', page: 3, fields: [price], tables: [] },
    {
      key: 'underwriting', title: 'Original Underwriting Budget', page: 3, fields: [], tables: [{
        path: 'underwriting.tables.budget', key: 'budget', title: 'Original underwriting budget', editable_rows: true,
        columns: [{ key: 'category', label: 'Category', kind: 'text', derived: false }, { key: 'original_budget', label: 'Original budget', kind: 'money', derived: false }, { key: 'pct_spent', label: '% spent', kind: 'percent', derived: true }],
        rows: [{ key: 'manual-1', label: 'Roofs', manual: true, subject: false, cells: [
          uiField({ path: 'underwriting.tables.budget.rows.manual-1.category', key: 'category', label: 'Category', kind: 'text', value: 'Roofs', effective: 'Roofs', status: 'manual' }),
          uiField({ path: 'underwriting.tables.budget.rows.manual-1.original_budget', key: 'original_budget', label: 'Original budget', kind: 'money', value: 75000, effective: 75000, status: 'manual' }),
          uiField({ path: 'underwriting.tables.budget.rows.manual-1.pct_spent', key: 'pct_spent', label: '% spent', kind: 'percent', value: 0, effective: 0, status: 'derived', readonly: true }),
        ] }],
        totals: [uiField({ path: 'underwriting.tables.budget.totals.original_budget', key: 'original_budget', label: 'Original budget', kind: 'money', value: 75000, effective: 75000, status: 'derived', readonly: true })],
      }],
    },
    { key: 'financing', title: 'Financing', page: 4, fields: [lender], tables: [] },
    { key: 'commentary', title: 'Commentary', page: 5, fields: [noi], tables: [] },
  ];
  return {
    built_at: '2026-09-05T00:00:00', summary: { missing: 1, conflicts: 1, ai_drafts: 0, errors: 0, warnings: 1, infos: 0 },
    issues: [{ path: 'financing.fields.lender', severity: 'warning', message: 'Missing: Lender' }, { path: null, severity: 'info', message: 'notes.docx: unsupported' }],
    sections, meta: {}, narrative_status: null, narrative_error: null, ...over,
  };
}

export const backendDown = { status: 0, message: 'Http failure response: 0 Unknown Error' };
export const detail422 = (msg: string) => ({ status: 422, error: { detail: msg }, message: 'Http failure response: 422' });
