export type FileStatus = 'queued' | 'processing' | 'processed' | 'failed' | 'unsupported' | 'unrecognized' | 'needs_ocr';
export type Stage = 'upload' | 'processing' | 'review' | 'generated';
export type AssetKind = 'cover' | 'logo';

/** A project as the index lists it: where it has got to and what is waiting, without a per-project read. */
export interface Project {
  id: string; name: string; created_at: string; updated_at: string; file_count?: number;
  files_attention?: number; stage?: Stage; report_built?: boolean;
  latest_version?: number | null; latest_gap_count?: number | null;
}
export interface Part { doc_type: string; confidence: number; locator: string; warnings: string[]; }
export interface ProjectFile {
  id: string; project_id: string; original_filename: string; ext: string; size: number; status: FileStatus;
  error: string | null; parts: Part[]; doc_type_override: string | null; ignored: boolean; uploaded_at: string; processed_at: string | null;
}
export interface Report {
  id: string; project_id: string; version: number; status: string; error: string | null; created_at: string; has_pdf: boolean;
  complete: boolean | null; gap_count: number | null;
}
export interface ProjectDetail extends Project {
  files: ProjectFile[]; reports: Report[]; stage: Stage; report_built: boolean; processing: string[]; assets: Record<AssetKind, boolean>;
}
export interface DocTypeOption { key: string; label: string; }
export interface Health {
  ok: boolean;
  llm_enabled: boolean;
  llm_provider: string | null;
  ocr_enabled?: boolean;
  ocr_provider?: string | null;
  pdf_renderer: boolean;
  workers: number;
}
export type Method = 'native' | 'ocr' | 'mixed';
export interface Source {
  file_id?: string | null; filename?: string | null; locator?: string | null; text?: string | null;
  doc_type?: string | null; method?: Method; ocr_confidence?: number | null;
}
export interface Alternative { value: unknown; source: Source | null; note: string | null; }
export type Kind = 'money' | 'number' | 'integer' | 'percent' | 'date' | 'text' | 'longtext';
export type Status = 'extracted' | 'inferred' | 'derived' | 'manual' | 'ai_draft' | 'missing' | 'conflict';
export type Origin = 'extracted' | 'inferred' | 'ocr' | 'computed' | 'manual' | 'ai_draft' | 'missing';
/** Where a value came from, or why it is absent. Produced by the backend so the review screen and the report agree. */
export interface Provenance {
  origin: Origin; label: string; detail: string; filename: string | null; locator: string | null;
  doc_type: string | null; doc_label: string | null; quote: string | null; ocr_confidence: number | null;
  reason: string | null; ocr: boolean;
}
export interface UiField {
  path: string; key: string; label: string; kind: Kind; value: unknown; override: unknown; effective: unknown; status: Status;
  source: Source | null; provenance: Provenance; alternatives: Alternative[]; note: string | null; readonly: boolean;
}
export interface UiColumn { key: string; label: string; kind: Kind; derived: boolean; }
export interface UiRow { key: string; label: string; manual: boolean; subject: boolean; cells: UiField[]; }
export interface UiTable { path: string; key: string; title: string; columns: UiColumn[]; rows: UiRow[]; totals: UiField[]; editable_rows: boolean; }
/** `preview_page` is the sheet of the live preview this section prints on; the interleaved
 *  data-sources sheets mean it is not the same number as `page`. */
export interface UiSection { key: string; title: string; page: number; preview_page: number; fields: UiField[]; tables: UiTable[]; }
export interface Issue { path: string | null; severity: 'error' | 'warning' | 'info'; message: string; }
export interface Gap { path: string; label: string; page: number; group: string; reason: string; }
export interface GapGroup { key: string; label: string; page: number; complete: boolean; gap_count: number; }
/** Structural means a PDF can be generated; complete means every requirement of a finished report is met. */
export interface Completeness { complete: boolean; gap_count: number; ai_drafts_pending: number; gaps: Gap[]; groups: GapGroup[]; }
export interface Summary { missing: number; conflicts: number; ai_drafts: number; errors: number; warnings: number; infos: number; completeness?: Completeness; }
export interface ProvenanceFile {
  filename: string; doc_labels: string[]; method: Method; ocr_pages: number[]; ocr_confidence: number | null;
}
export interface ProvenanceSummary { counts: Record<Origin, number>; files: ProvenanceFile[]; }
export interface ReportDataUi {
  built_at: string | null; summary: Summary; issues: Issue[]; sections: UiSection[]; meta: Record<string, unknown>;
  narrative_status: string | null; narrative_error: string | null; provenance?: ProvenanceSummary;
  preview_total_pages?: number;
}
export interface Change { path: string; value: unknown; }
export interface PatchBody { changes?: Change[]; add_rows?: { table: string; key?: string; values: Record<string, unknown> }[]; delete_rows?: { table: string; key: string }[]; }
export interface FileExtraction { parts: Part[]; extractions: { doc_type: string; locator: string; data: unknown; warnings: string[] }[]; }
export interface Overrides {
  fields?: Record<string, unknown>; rows?: Record<string, Record<string, Record<string, unknown>>>;
  deleted_rows?: Record<string, string[]>; ai_drafts?: Record<string, string>;
}

/** Message for the user from an HTTP failure: the backend's detail when there is one, else the transport error. */
export function errorText(e: unknown): string {
  const err = e as { error?: { detail?: unknown }; status?: number; message?: string } | null;
  const detail = err?.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ');
  if (err?.status === 0) return 'The backend is not reachable. Start it and reload the page.';
  return err?.message ?? String(e);
}
