import { DecimalPipe, JsonPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, interval, switchMap } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { DocTypeOption, FileExtraction, ProjectDetail, ProjectFile } from '../../core/models';
import { StatusChipComponent } from '../../shared/status-chip.component';
import { StepperComponent } from '../../shared/stepper.component';

@Component({
  selector: 'app-files',
  standalone: true,
  imports: [FormsModule, RouterLink, JsonPipe, DecimalPipe, StatusChipComponent, StepperComponent],
  template: `
    @if (project(); as p) {
      <app-stepper [stage]="p.stage" />
      <div class="row between">
        <h1>{{ p.name }} <span class="muted">· source files</span></h1>
        <nav class="row">
          <a [routerLink]="['/projects', p.id, 'review']" class="btn" [class.disabled]="!p.report_built">Review data →</a>
          <a [routerLink]="['/projects', p.id, 'report']" class="btn secondary" [class.disabled]="!p.report_built">Report</a>
        </nav>
      </div>
      <label class="dropzone" [class.drag]="dragging()" (dragover)="$event.preventDefault(); dragging.set(true)" (dragleave)="dragging.set(false)" (drop)="onDrop($event)">
        <input type="file" multiple accept=".xlsx,.xlsm,.pdf" (change)="onPick($event)" hidden />
        <strong>Drop files here or click to choose</strong>
        <span class="muted small">Yardi, HelloData, CoStar and Slate exports (.xlsx, .pdf). Any names, any order.</span>
      </label>
      @if (error()) { <p class="err">{{ error() }}</p> }
      <table class="grid">
        <thead><tr><th>File</th><th>Status</th><th>Detected as</th><th>Type override</th><th>Use</th><th></th></tr></thead>
        <tbody>
          @for (f of p.files; track f.id) {
            <tr [class.muted]="f.ignored">
              <td>{{ f.original_filename }}<div class="small muted">{{ (f.size / 1024) | number: '1.0-0' }} KB</div>
                @if (f.error) { <div class="small err">{{ f.error }}</div> }</td>
              <td><app-status-chip [status]="f.status" /></td>
              <td>
                @for (part of f.parts; track part.locator) {
                  <div class="small"><code>{{ part.locator }}</code> → <strong>{{ label(part.doc_type) }}</strong>
                    @if (part.doc_type !== 'unknown') { <span class="muted">({{ part.confidence * 100 | number: '1.0-0' }}%)</span> }
                    @for (w of part.warnings; track w) { <div class="warn">{{ w }}</div> }
                  </div>
                }
              </td>
              <td>
                @if (f.parts.length <= 1 && f.status !== 'unsupported') {
                  <select [ngModel]="f.doc_type_override ?? ''" (ngModelChange)="override(f, $event)">
                    <option value="">auto-detect</option>
                    @for (t of docTypes(); track t.key) { <option [value]="t.key">{{ t.label }}</option> }
                  </select>
                } @else { <span class="muted small">per-sheet (auto)</span> }
              </td>
              <td><label class="small"><input type="checkbox" [checked]="!f.ignored" (change)="toggleIgnore(f)" /> include</label></td>
              <td class="r nowrap">
                <button class="link" (click)="reprocess(f)" [disabled]="f.status === 'unsupported' || f.status === 'processing'">Reprocess</button>
                <button class="link" (click)="showExtraction(f)">Data</button>
                <button class="link danger" (click)="remove(f)">Remove</button>
              </td>
            </tr>
          } @empty { <tr><td colspan="6" class="muted">No files yet.</td></tr> }
        </tbody>
      </table>
      @if (extraction(); as ex) {
        <details open class="panel"><summary>Extracted payload <button class="link" (click)="extraction.set(null)">close</button></summary>
          <pre class="small">{{ ex | json }}</pre></details>
      }
    }`,
})
export class FilesComponent {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private pid = this.route.snapshot.paramMap.get('id')!;
  private poll: Subscription | null = null;
  project = signal<ProjectDetail | null>(null);
  docTypes = signal<DocTypeOption[]>([]);
  extraction = signal<FileExtraction | null>(null);
  dragging = signal(false);
  error = signal<string | null>(null);

  constructor() {
    this.api.docTypes().subscribe((t) => this.docTypes.set(t));
    this.load();
  }

  label(key: string): string { return this.docTypes().find((t) => t.key === key)?.label ?? key; }

  load(): void {
    this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.syncPolling(p); }, error: (e) => this.error.set(e.message) });
  }

  private syncPolling(p: ProjectDetail): void {
    const active = p.files.some((f) => f.status === 'queued' || f.status === 'processing');
    if (active && !this.poll) {
      this.poll = interval(2000).pipe(switchMap(() => this.api.getProject(this.pid)), takeUntilDestroyed(this.destroy))
        .subscribe((np) => { this.project.set(np); if (!np.files.some((f) => f.status === 'queued' || f.status === 'processing')) { this.poll?.unsubscribe(); this.poll = null; } });
    }
  }

  onPick(ev: Event): void { const input = ev.target as HTMLInputElement; this.upload(Array.from(input.files ?? [])); input.value = ''; }
  onDrop(ev: DragEvent): void { ev.preventDefault(); this.dragging.set(false); this.upload(Array.from(ev.dataTransfer?.files ?? [])); }

  upload(files: File[]): void {
    if (!files.length) return;
    this.api.uploadFiles(this.pid, files).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }

  override(f: ProjectFile, key: string): void {
    const body = key ? { doc_type_override: key } : { clear_override: true };
    this.api.patchFile(this.pid, f.id, body).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.error?.detail ?? e.message) });
  }
  toggleIgnore(f: ProjectFile): void { this.api.patchFile(this.pid, f.id, { ignored: !f.ignored }).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.message) }); }
  reprocess(f: ProjectFile): void { this.api.reprocessFile(this.pid, f.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.error?.detail ?? e.message) }); }
  remove(f: ProjectFile): void { if (confirm(`Remove ${f.original_filename}?`)) this.api.deleteFile(this.pid, f.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.message) }); }
  showExtraction(f: ProjectFile): void { this.api.fileExtraction(this.pid, f.id).subscribe({ next: (ex) => this.extraction.set(ex), error: (e) => this.error.set(e.message) }); }
}
