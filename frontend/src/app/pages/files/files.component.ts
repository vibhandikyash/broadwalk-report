import { DecimalPipe, JsonPipe } from '@angular/common';
import { Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, interval, switchMap } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AssetKind, DocTypeOption, FileExtraction, ProjectDetail, ProjectFile, errorText } from '../../core/models';
import { ProjectNavComponent } from '../../shared/project-nav.component';
import { StatusChipComponent } from '../../shared/status-chip.component';

const ACTIVE = new Set(['queued', 'processing']);

@Component({
  selector: 'app-files',
  standalone: true,
  imports: [FormsModule, RouterLink, JsonPipe, DecimalPipe, StatusChipComponent, ProjectNavComponent],
  template: `
    @if (project(); as p) {
      <app-project-nav [project]="p" current="files">
        @if (p.report_built) {
          <a class="btn" [routerLink]="['/projects', p.id, 'review']">Continue to review →</a>
        } @else {
          <button type="button" disabled title="Available once the files have been processed">Continue to review →</button>
        }
      </app-project-nav>
      <div class="workbench two-pane">
      <section class="pane pane-main" aria-label="Source files">
      <label class="dropzone" [class.drag]="dragging()" tabindex="0" (keydown.enter)="picker.click()"
             (keydown.space)="$event.preventDefault(); picker.click()"
             (dragover)="$event.preventDefault(); dragging.set(true)" (dragleave)="dragging.set(false)" (drop)="onDrop($event)">
        <input #picker type="file" multiple accept=".xlsx,.xlsm,.pdf" (change)="onPick($event)" class="sr-only" aria-label="Choose source files" />
        <strong>Drop files here or click to choose</strong>
        <span class="muted small">Yardi, HelloData, CoStar and Slate exports (.xlsx, .pdf). Any names, any order.</span>
      </label>
      <p class="status small" role="status" aria-live="polite">{{ status() }}</p>
      @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
      <div class="scroll">
      <table class="grid">
        <caption class="sr-only">Uploaded files and their processing status</caption>
        <thead><tr><th scope="col">File</th><th scope="col">Status</th><th scope="col">Detected as</th><th scope="col">Type override</th><th scope="col">Use</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>
          @for (f of p.files; track f.id) {
            <tr [class.muted]="f.ignored">
              <td>{{ f.original_filename }}<div class="small muted">{{ (f.size / 1024) | number: '1.0-0' }} KB</div>
                @if (f.error) { <div class="small" [class.err]="f.status !== 'unrecognized'" [class.warn]="f.status === 'unrecognized'">{{ f.error }}</div> }</td>
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
                  <select [ngModel]="f.doc_type_override ?? ''" (ngModelChange)="override(f, $event)" [attr.aria-label]="'Document type for ' + f.original_filename" [disabled]="active(f)">
                    <option value="">auto-detect</option>
                    @for (t of docTypes(); track t.key) { <option [value]="t.key">{{ t.label }}</option> }
                  </select>
                } @else { <span class="muted small">per-sheet (auto)</span> }
              </td>
              <td><label class="small"><input type="checkbox" [checked]="!f.ignored" (change)="toggleIgnore(f)" [attr.aria-label]="'Use ' + f.original_filename" /> include</label></td>
              <td class="r nowrap">
                <button type="button" class="link" (click)="reprocess(f)" [disabled]="f.status === 'unsupported' || active(f)" [attr.aria-label]="'Reprocess ' + f.original_filename">Reprocess</button>
                <button type="button" class="link" (click)="showExtraction(f)" [attr.aria-label]="'Show extracted data for ' + f.original_filename">Data</button>
                <button type="button" class="link danger" (click)="remove(f)" [disabled]="active(f)" [attr.aria-label]="'Remove ' + f.original_filename">Remove</button>
              </td>
            </tr>
          } @empty { <tr><td colspan="6" class="muted">No files yet.</td></tr> }
        </tbody>
      </table>
      </div>
      </section>
      <aside class="pane pane-side" aria-label="Report images and extracted data">
      <section class="panel assets" aria-labelledby="assets-h">
        <h2 id="assets-h" class="small">Report images <span class="muted">(optional: cover photo and logo, png / jpg / webp)</span></h2>
        @for (kind of kinds; track kind) {
          <div class="row">
            <label class="small">{{ kind === 'cover' ? 'Cover / property photo' : 'Logo' }}
              <input type="file" accept=".png,.jpg,.jpeg,.webp" (change)="onAsset(kind, $event)" [attr.aria-label]="'Choose ' + (kind === 'cover' ? 'cover photo' : 'logo')" /></label>
            @if (p.assets[kind]) {
              <img [src]="api.assetUrl(p.id, kind) + '&v=' + assetVersion()" [alt]="'Current ' + kind" class="thumb" />
              <button type="button" class="link danger" (click)="removeAsset(kind)">Remove {{ kind }}</button>
            }
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

  load(): void {
    this.api.getProject(this.pid).subscribe({ next: (p) => { this.project.set(p); this.announce(p); this.syncPolling(p); }, error: (e) => this.fail(errorText(e)) });
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
        .subscribe((np) => { this.project.set(np); this.announce(np); if (!np.files.some((f) => ACTIVE.has(f.status))) { this.poll?.unsubscribe(); this.poll = null; } });
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
