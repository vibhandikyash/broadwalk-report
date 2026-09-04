import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { DocTypeOption, FileExtraction, Health, PatchBody, Project, ProjectDetail, ProjectFile, Report, ReportDataUi } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  health(): Observable<Health> { return this.http.get<Health>(`${this.base}/health`); }
  docTypes(): Observable<DocTypeOption[]> { return this.http.get<DocTypeOption[]>(`${this.base}/doc-types`); }

  listProjects(): Observable<Project[]> { return this.http.get<Project[]>(`${this.base}/projects`); }
  createProject(name: string): Observable<Project> { return this.http.post<Project>(`${this.base}/projects`, { name }); }
  getProject(id: string): Observable<ProjectDetail> { return this.http.get<ProjectDetail>(`${this.base}/projects/${id}`); }
  deleteProject(id: string): Observable<void> { return this.http.delete<void>(`${this.base}/projects/${id}`); }

  uploadFiles(pid: string, files: File[]): Observable<ProjectFile[]> {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    return this.http.post<ProjectFile[]>(`${this.base}/projects/${pid}/files`, fd);
  }
  patchFile(pid: string, fid: string, body: { ignored?: boolean; doc_type_override?: string; clear_override?: boolean }): Observable<ProjectFile> {
    return this.http.patch<ProjectFile>(`${this.base}/projects/${pid}/files/${fid}`, body);
  }
  reprocessFile(pid: string, fid: string): Observable<ProjectFile> { return this.http.post<ProjectFile>(`${this.base}/projects/${pid}/files/${fid}/reprocess`, {}); }
  deleteFile(pid: string, fid: string): Observable<void> { return this.http.delete<void>(`${this.base}/projects/${pid}/files/${fid}`); }
  fileExtraction(pid: string, fid: string): Observable<FileExtraction> { return this.http.get<FileExtraction>(`${this.base}/projects/${pid}/files/${fid}/extraction`); }

  reportData(pid: string): Observable<ReportDataUi> { return this.http.get<ReportDataUi>(`${this.base}/projects/${pid}/report-data`); }
  rebuildReportData(pid: string): Observable<ReportDataUi> { return this.http.post<ReportDataUi>(`${this.base}/projects/${pid}/report-data/rebuild`, {}); }
  patchReportData(pid: string, body: PatchBody): Observable<ReportDataUi> { return this.http.patch<ReportDataUi>(`${this.base}/projects/${pid}/report-data`, body); }
  draftNarratives(pid: string): Observable<{ status: string }> { return this.http.post<{ status: string }>(`${this.base}/projects/${pid}/narratives`, {}); }

  previewUrl(pid: string): string { return `${this.base}/projects/${pid}/report/preview?t=${Date.now()}`; }
  createReport(pid: string): Observable<Report> { return this.http.post<Report>(`${this.base}/projects/${pid}/reports`, {}); }
  listReports(pid: string): Observable<Report[]> { return this.http.get<Report[]>(`${this.base}/projects/${pid}/reports`); }
  getReport(pid: string, rid: string): Observable<Report> { return this.http.get<Report>(`${this.base}/projects/${pid}/reports/${rid}`); }
  downloadUrl(pid: string, rid: string): string { return `${this.base}/projects/${pid}/reports/${rid}/download`; }
}
