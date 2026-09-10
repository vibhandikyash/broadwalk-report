import { DecimalPipe, JsonPipe } from '@angular/common';
import { Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, interval, switchMap } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AssetKind, DocTypeOption, FileExtraction, ProjectDetail, ProjectFile, errorText } from '../../core/models';
import { ShellStore } from '../../core/shell.store';
import { StatusChipComponent } from '../../shared/status-chip.component';

const ACTIVE = new Set(['queued', 'processing']);

@Component({
  selector: 'app-files',
  standalone: true,
  imports: [FormsModule, RouterLink, JsonPipe, DecimalPipe, StatusChipComponent],
  template: `
    @if (project(); as p) {
      <div class="workbench two-pane">
      <section class="pane pane-main" aria-label="Source files">
      <div class="row page-head">
        <h1>Source files</h1>
        <span class="muted small">{{ p.files.length }} file{{ p.files.length === 1 ? '' : 's' }}{{ processed(p) }}</span>
        <span class="spacer"></span>
        <div class="project-action">
          @if (p.report_built) {
            <a class="btn" [routerLink]="['/projects', p.id, 'review']">Continue to review →</a>
          } @else {
            <button type="button" disabled title="Available once the files have been processed">Continue to review →</button>
          }
        </div>
      </div>
      <label class="dropzone" [class.drag]="dragging()" tabindex="0" (keydown.enter)="picker.click()"
             (keydown.space)="$event.preventDefault(); picker.click()"
             (dragover)="$event.preventDefault(); dragging.set(true)" (dragleave)="dragging.set(false)" (drop)="onDrop($event)">
        <input #picker type="file" multiple accept=".xlsx,.xlsm,.pdf" (change)="onPick($event)" class="sr-only" aria-label="Choose source files" />
        <strong>Drop quarterly exports here — .xlsx, .xlsm, .pdf</strong>
        <span class="muted small">any filenames, any order · or click to browse</span>
      </label>
      @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
      <div class="scroll table-surface">
      <table class="grid files-grid">
        <caption class="sr-only">Uploaded files and their processing status</caption>
        <thead><tr><th scope="col">File</th><th scope="col">Status</th><th scope="col">Detected type</th><th scope="col">Override</th><th scope="col">Incl.</th><th scope="col">Actions</th></tr></thead>
        <tbody>
          @for (f of p.files; track f.id) {
            <tr [class.ignored]="f.ignored">
              <td><div class="fname mono" [title]="f.original_filename">{{ f.original_filename }}</div>
                <div class="small muted">{{ (f.size / 1024) | number: '1.0-0' }} KB</div>
                @if (f.error) { <div class="small" [class.err]="f.status !== 'unrecognized'" [class.warn]="f.status === 'unrecognized'">▲ {{ f.error }}</div> }</td>
              <td><app-status-chip [status]="f.status" /></td>
              <td>
                @for (part of f.parts; track part.locator) {
                  <div class="small"><strong>{{ label(part.doc_type) }}</strong>
                    @if (part.doc_type !== 'unknown') { <span class="muted tabular">{{ part.confidence * 100 | number: '1.0-0' }}%</span> }
                    <div class="muted mono">{{ part.locator }}</div>
                    @for (w of part.warnings; track w) { <div class="warn">▲ {{ w }}</div> }
                  </div>
                } @empty { <span class="muted">—</span> }
              </td>
              <td>
                @if (f.parts.length <= 1 && f.status !== 'unsupported') {
                  <select [ngModel]="f.doc_type_override ?? ''" (ngModelChange)="override(f, $event)" [attr.aria-label]="'Document type for ' + f.original_filename" [disabled]="active(f)">
                    <option value="">auto</option>
                    @for (t of docTypes(); track t.key) { <option [value]="t.key">{{ t.label }}</option> }
                  </select>
                } @else { <span class="muted small">per-sheet (auto)</span> }
              </td>
              <td><input type="checkbox" [checked]="!f.ignored" (change)="toggleIgnore(f)" [attr.aria-label]="'Use ' + f.original_filename" /></td>
              <td>
                <div class="actions">
                  <button type="button" class="secondary btn-icon small" (click)="reprocess(f)" [disabled]="f.status === 'unsupported' || active(f)" title="Reprocess" [attr.aria-label]="'Reprocess ' + f.original_filename">↻</button>
                  <button type="button" class="secondary btn-icon small" (click)="showExtraction(f)" title="View raw payload" [attr.aria-label]="'Show extracted data for ' + f.original_filename">&#123; &#125;</button>
                  <button type="button" class="secondary btn-icon small" (click)="remove(f)" [disabled]="active(f)" title="Remove" [attr.aria-label]="'Remove ' + f.original_filename">✕</button>
                </div>
              </td>
            </tr>
          } @empty { <tr><td colspan="6" class="muted">No files yet.</td></tr> }
        </tbody>
      </table>
      <p class="status small" role="status" aria-live="polite">{{ status() }}</p>
      </div>
      </section>
      <aside class="pane pane-side" aria-label="Report images and extracted data">
      <section class="card assets" aria-labelledby="assets-h">
        <h2 id="assets-h" class="card-kicker">Report imagery</h2>
        @for (kind of kinds; track kind) {
          <div class="asset">
            <div class="small muted">{{ kind === 'cover' ? 'Cover photo' : 'Sponsor logo' }}</div>
            @if (p.assets[kind]) {
              <img [src]="api.assetUrl(p.id, kind) + '&v=' + assetVersion()" [alt]="'Current ' + kind" class="thumb" />
            } @else {
              <div class="asset-empty">Drop {{ kind === 'cover' ? 'a photo' : 'a logo' }} (.png, .jpg, .webp)</div>
            }
            <div class="row">
              <label class="btn secondary small">{{ p.assets[kind] ? 'Replace' : 'Choose' }}
                <input type="file" accept=".png,.jpg,.jpeg,.webp" class="sr-only" (change)="onAsset(kind, $event)" [attr.aria-label]="'Choose ' + (kind === 'cover' ? 'cover photo' : 'logo')" /></label>
              @if (p.assets[kind]) { <button type="button" class="link danger small" (click)="removeAsset(kind)">Remove {{ kind }}</button> }
            </div>
          </div>
        }
      </section>
      @if (extraction(); as ex) {
        <details open class="panel"><summary>Extracted payload <button type="button" class="link" (click)="extraction.set(null)">close</button></summary>
          <pre class="small">{{ ex | json }}</pre></details>
      }
      </aside>
      </div>
    } @else if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> } @else { <p class="muted">Loading…</p> }`,
})
export class FilesComponent {
  api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private destroy = inject(DestroyRef);
  private shell = inject(ShellStore);
  private pid = this.route.snapshot.paramMap.get('id')!;
  private poll: Subscription | null = null;
  picker = viewChild.required<ElementRef<HTMLInputElement>>('picker');
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  project = signal<ProjectDetail | null>(null);
  docTypes = signal<DocTypeOption[]>([]);
  extraction = signal<FileExtraction | null>(null);
  dragging = signal(false);
  error = signal<string | null>(null);
  status = signal('');
  assetVersion = signal(0);
  kinds: AssetKind[] = ['cover', 'logo'];

  constructor() {
    this.api.docTypes().subscribe({ next: (t) => this.docTypes.set(t), error: () => undefined });
    this.load();
  }

  label(key: string): string { return this.docTypes().find((t) => t.key === key)?.label ?? key; }
  active(f: ProjectFile): boolean { return ACTIVE.has(f.status); }
  /** The trailing half of the count line: how many of the files are through processing. */
  processed(p: ProjectDetail): string {
    const done = p.files.filter((f) => !ACTIVE.has(f.status)).length;
    return p.files.length ? ` · ${done} processed` : '';
  }

  load(): void {
    this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.shell.setProject(p); this.announce(p); this.syncPolling(p); }, error: (e) => this.fail(errorText(e)) });
  }

  private announce(p: ProjectDetail): void {
    const n = p.files.filter((f) => ACTIVE.has(f.status)).length;
    const bad = p.files.filter((f) => ['failed', 'unsupported', 'unrecognized', 'needs_ocr'].includes(f.status)).length;
    if (n) this.status.set(`${n} of ${p.files.length} files processing…`);
    else if (p.files.length) this.status.set(`All ${p.files.length} files finished${bad ? `, ${bad} need attention` : ''}. ${p.report_built ? 'Report data is ready to review.' : ''}`);
    else this.status.set('');
  }

  private syncPolling(p: ProjectDetail): void {
    const active = p.files.some((f) => ACTIVE.has(f.status));
    if (active && !this.poll) {
      this.poll = interval(2000).pipe(switchMap(() => this.api.getProject(this.pid)), takeUntilDestroyed(this.destroy))
        .subscribe((np) => { this.project.set(np); this.shell.setProject(np); this.announce(np); if (!np.files.some((f) => ACTIVE.has(f.status))) { this.poll?.unsubscribe(); this.poll = null; } });
    }
  }

  fail(msg: string): void {
    this.error.set(msg);
    setTimeout(() => this.alert()?.nativeElement.focus(), 0);
  }

  onPick(ev: Event): void { const input = ev.target as HTMLInputElement; this.upload(Array.from(input.files ?? [])); input.value = ''; }
  onDrop(ev: DragEvent): void { ev.preventDefault(); this.dragging.set(false); this.upload(Array.from(ev.dataTransfer?.files ?? [])); }

  upload(files: File[]): void {
    if (!files.length) return;
    this.error.set(null);
    this.status.set(`Uploading ${files.length} file${files.length === 1 ? '' : 's'}…`);
    this.api.uploadFiles(this.pid, files).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) });
  }

  override(f: ProjectFile, key: string): void {
    const body = key ? { doc_type_override: key } : { clear_override: true };
    this.api.patchFile(this.pid, f.id, body).subscribe({ next: () => this.load(), error: (e) => { this.fail(errorText(e)); this.load(); } });
  }
  toggleIgnore(f: ProjectFile): void { this.api.patchFile(this.pid, f.id, { ignored: !f.ignored }).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) }); }
  reprocess(f: ProjectFile): void { this.api.reprocessFile(this.pid, f.id).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) }); }
  remove(f: ProjectFile): void { if (confirm(`Remove ${f.original_filename}?`)) this.api.deleteFile(this.pid, f.id).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) }); }
  showExtraction(f: ProjectFile): void { this.api.fileExtraction(this.pid, f.id).subscribe({ next: (ex) => this.extraction.set(ex), error: (e) => this.fail(errorText(e)) }); }

  onAsset(kind: AssetKind, ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.api.putAsset(this.pid, kind, file).subscribe({ next: () => { this.assetVersion.update((v) => v + 1); this.status.set(`${kind} image saved.`); this.load(); }, error: (e) => this.fail(errorText(e)) });
  }
  removeAsset(kind: AssetKind): void { this.api.deleteAsset(this.pid, kind).subscribe({ next: () => { this.status.set(`${kind} image removed.`); this.load(); }, error: (e) => this.fail(errorText(e)) }); }
}
