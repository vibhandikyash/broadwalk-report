export type FileStatus = 'queued' | 'processing' | 'processed' | 'failed' | 'unsupported' | 'unrecognized' | 'needs_ocr';
export type Stage = 'upload' | 'processing' | 'review' | 'generated';
export type AssetKind = 'cover' | 'logo';

export interface Project { id: string; name: string; created_at: string; updated_at: string; file_count?: number; }
export interface Part { doc_type: string; confidence: number; locator: string; warnings: string[]; }
export interface ProjectFile {
  id: string; project_id: string; original_filename: string; ext: string; size: number; status: FileStatus;
  error: string | null; parts: Part[]; doc_type_override: string | null; ignored: boolean; uploaded_at: string; processed_at: string | null;
}
export interface Report { id: string; project_id: string; version: number; status: string; error: string | null; created_at: string; has_pdf: boolean; }
export interface ProjectDetail extends Project {
  files: ProjectFile[]; reports: Report[]; stage: Stage; report_built: boolean; processing: string[]; assets: Record<AssetKind, boolean>;
}
export interface DocTypeOption { key: string; label: string; }
export interface Health { ok: boolean; llm_enabled: boolean; llm_provider: string | null; pdf_renderer: boolean; workers: number; }
export interface Source { file_id?: string | null; filename?: string | null; locator?: string | null; text?: string | null; }
export interface Alternative { value: unknown; source: Source | null; note: string | null; }
export type Kind = 'money' | 'number' | 'integer' | 'percent' | 'date' | 'text' | 'longtext';
export type Status = 'extracted' | 'derived' | 'manual' | 'ai_draft' | 'missing' | 'conflict';
export interface UiField {
  path: string; key: string; label: string; kind: Kind; value: unknown; override: unknown; effective: unknown; status: Status;
  source: Source | null; alternatives: Alternative[]; note: string | null; readonly: boolean;
}
export interface UiColumn { key: string; label: string; kind: Kind; derived: boolean; }
export interface UiRow { key: string; label: string; manual: boolean; subject: boolean; cells: UiField[]; }
export interface UiTable { path: string; key: string; title: string; columns: UiColumn[]; rows: UiRow[]; totals: UiField[]; editable_rows: boolean; }
export interface UiSection { key: string; title: string; page: number; fields: UiField[]; tables: UiTable[]; }
export interface Issue { path: string | null; severity: 'error' | 'warning' | 'info'; message: string; }
export interface Summary { missing: number; conflicts: number; ai_drafts: number; errors: number; warnings: number; infos: number; }
export interface ReportDataUi {
  built_at: string | null; summary: Summary; issues: Issue[]; sections: UiSection[]; meta: Record<string, unknown>;
  narrative_status: string | null; narrative_error: string | null;
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
