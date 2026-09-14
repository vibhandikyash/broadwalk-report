import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { ProjectDetail, ProjectFile, Provenance, Report, ReportDataUi, UiField, UiSection } from '../core/models';

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
  return { id: 'r1', project_id: 'p1', version: 1, status: 'done', error: null, created_at: '2026-09-05T00:00:00', has_pdf: true, complete: true, gap_count: 0, ...over };
}

export function detail(over: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    id: 'p1', name: 'Boardwalk', created_at: '2026-09-05T00:00:00', updated_at: '2026-09-05T00:00:00', files: [file()], reports: [],
    stage: 'review', report_built: true, processing: [], assets: { cover: false, logo: false }, ...over,
  };
}

export function provenance(over: Partial<Provenance> = {}): Provenance {
  return {
    origin: 'extracted', label: 'Extracted', detail: "rr.xlsx · sheet 'RR' summary block", filename: 'rr.xlsx',
    locator: "sheet 'RR' summary block", doc_type: 'yardi_rent_roll', doc_label: 'Yardi Rent Roll summary (occupancy)',
    quote: 'Totals', ocr_confidence: null, reason: null, ocr: false, ...over,
  };
}

export function uiField(over: Partial<UiField> = {}): UiField {
  return {
    path: 'property.fields.units', key: 'units', label: 'Units', kind: 'integer', value: 338, override: null, effective: 338, status: 'extracted',
    source: { filename: 'rr.xlsx', locator: "sheet 'RR' summary block", text: 'Totals' }, provenance: provenance(),
    alternatives: [], note: null, readonly: false, ...over,
  };
}

export function uiData(over: Partial<ReportDataUi> = {}): ReportDataUi {
  const units = uiField();
  const missingProv = provenance({
    origin: 'missing', label: 'Not found', filename: null, locator: null, doc_type: null, doc_label: null, quote: null,
    detail: 'Loan servicing summary would carry this value, and no such file was uploaded.',
    reason: 'Loan servicing summary would carry this value, and no such file was uploaded.',
  });
  const lender = uiField({ path: 'financing.fields.lender', key: 'lender', label: 'Lender', kind: 'text', value: null, effective: null, status: 'missing', source: null, provenance: missingProv });
  const price = uiField({
    path: 'capital.fields.purchase_price', key: 'purchase_price', label: 'Purchase price', kind: 'money', value: 48000000, effective: 48000000, status: 'conflict',
    alternatives: [{ value: 38100000, source: { filename: 'costar.pdf' }, note: 'CoStar recorded sale price' }],
  });
  const noi = uiField({ path: 'commentary.fields.noi_actual', key: 'noi_actual', label: 'NOI actual', kind: 'money', value: 550, effective: 550, status: 'derived', readonly: true, source: null, provenance: provenance({ origin: 'computed', label: 'Calculated', detail: 'Calculated by the system from other values in this report', filename: null, locator: null, doc_type: null, doc_label: null, quote: null }) });
  const sections: UiSection[] = [
    { key: 'property', title: 'Property', page: 2, preview_page: 2, fields: [units], tables: [] },
    { key: 'capital', title: 'Capital Summary', page: 3, preview_page: 5, fields: [price], tables: [] },
    {
      key: 'underwriting', title: 'Original Underwriting Budget', page: 3, preview_page: 5, fields: [], tables: [{
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
    { key: 'financing', title: 'Financing', page: 4, preview_page: 8, fields: [lender], tables: [] },
    { key: 'commentary', title: 'Commentary', page: 5, preview_page: 11, fields: [noi], tables: [] },
  ];
  return {
    built_at: '2026-09-05T00:00:00',
    summary: { missing: 1, conflicts: 1, ai_drafts: 0, errors: 0, warnings: 1, infos: 0, completeness: {
      complete: false, gap_count: 2, ai_drafts_pending: 0,
      gaps: [{ path: 'financing.fields.lender', label: 'Lender', page: 4, group: 'financing', reason: 'needed for a complete report' },
             { path: 'status.fields.status1_title', label: 'Status item 1: title', page: 10, group: 'status', reason: 'at least one status item with a title and body' }],
      groups: [{ key: 'financing', label: 'Financing terms', page: 4, complete: false, gap_count: 1 }, { key: 'status', label: 'Status update', page: 10, complete: false, gap_count: 1 }],
    } },
    issues: [{ path: 'financing.fields.lender', severity: 'warning', message: 'Missing: Lender' }, { path: null, severity: 'info', message: 'notes.docx: unsupported' }],
    sections, meta: {}, narrative_status: null, narrative_error: null, preview_total_pages: 29,
    provenance: { counts: { extracted: 2, inferred: 0, ocr: 1, computed: 2, manual: 2, ai_draft: 0, missing: 1 }, files: [
      { filename: 'rr.xlsx', doc_labels: ['Yardi Rent Roll summary (occupancy)'], method: 'native', ocr_pages: [], ocr_confidence: null },
      { filename: 'scan.pdf', doc_labels: ['Slate capital calls'], method: 'ocr', ocr_pages: [1], ocr_confidence: 0.94 },
    ] }, ...over,
  };
}

export const backendDown = { status: 0, message: 'Http failure response: 0 Unknown Error' };
export const detail422 = (msg: string) => ({ status: 422, error: { detail: msg }, message: 'Http failure response: 422' });
