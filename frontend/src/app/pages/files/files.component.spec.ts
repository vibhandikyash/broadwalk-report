import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { backendDown, detail, detail422, file, routeStub } from '../../testing/fixtures';
import { FilesComponent } from './files.component';

const tick = () => new Promise((r) => setTimeout(r, 0));

function setup(api: Partial<Record<keyof ApiService, unknown>>) {
  const base = { docTypes: () => of([{ key: 'yardi_budget_comparison', label: 'Yardi Budget Comparison' }]), assetUrl: () => '/api/x' };
  TestBed.configureTestingModule({ providers: [provideRouter([]), routeStub(), { provide: ApiService, useValue: { ...base, ...api } }] });
  const fixture = TestBed.createComponent(FilesComponent);
  fixture.detectChanges();
  return fixture;
}

describe('FilesComponent', () => {
  it('renders every file status distinctly and explains unrecognised files', () => {
    const files = [file(), file({ id: 'f2', original_filename: 'notes.docx', status: 'unsupported', error: "Unsupported file type '.docx'", parts: [] }),
                   file({ id: 'f3', original_filename: 'odd.xlsx', status: 'unrecognized', error: 'No recognised report found in this file, so it is not used.', parts: [{ doc_type: 'unknown', confidence: 0, locator: "sheet 'S'", warnings: [] }] }),
                   file({ id: 'f4', original_filename: 'scan.pdf', status: 'needs_ocr', error: 'PDF has no extractable text', parts: [] })];
    const fixture = setup({ getProject: () => of(detail({ files })) });
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.chip-unsupported')!.textContent).toBe('unsupported');
    expect(el.querySelector('.chip-unrecognized')!.textContent).toBe('not recognised');
    expect(el.querySelector('.chip-needs_ocr')!.textContent).toBe('needs OCR');
    expect(el.textContent).toContain('so it is not used');
    expect(el.querySelector('select[aria-label="Document type for odd.xlsx"]')).not.toBeNull();
    expect(el.querySelector('[role="status"]')!.textContent).toContain('3 need attention');
    expect(el.querySelector('.tabs a[href$="/review"]')!.textContent).toContain('Review data');
    const cta = el.querySelector('.project-action a.btn') as HTMLAnchorElement;  // the first-run next step
    expect(cta.textContent).toContain('Continue to review');
    expect(cta.getAttribute('href')).toContain('/review');
  });

  it('disables navigation until report data exists and shows processing progress', async () => {
    const fixture = setup({ getProject: () => of(detail({ report_built: false, stage: 'processing', files: [file({ status: 'processing' }), file({ id: 'f2', status: 'processed' })] })) });
    await tick();  // ngModel applies [disabled] asynchronously
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const laterTabs = Array.from(el.querySelectorAll('.tabs button') as NodeListOf<HTMLButtonElement>);
    expect(laterTabs.map((b) => b.textContent!.trim())).toEqual(['Review data', 'Report']);
    expect(laterTabs.every((b) => b.disabled)).toBe(true);  // nothing to review until the files are processed
    expect(el.querySelector('.tabs a')).toBeNull();
    expect(el.querySelector('[role="status"]')!.textContent).toContain('1 of 2 files processing');
    expect((el.querySelector('button[aria-label="Reprocess fin.xlsx"]') as HTMLButtonElement).disabled).toBe(true);
    expect((el.querySelector('select[aria-label="Document type for fin.xlsx"]') as HTMLSelectElement).disabled).toBe(true);
  });

  it('uploads through the API, announces progress and reloads', () => {
    const upload = vi.fn(() => of([]));
    const getProject = vi.fn(() => of(detail({ files: [] })));
    const fixture = setup({ getProject, uploadFiles: upload });
    fixture.componentInstance.upload([new File(['x'], 'a.xlsx')]);
    fixture.detectChanges();
    expect(upload).toHaveBeenCalledWith('p1', [expect.any(File)]);
    expect(getProject).toHaveBeenCalledTimes(2);
  });

  it('surfaces an upload failure as a focused alert', async () => {
    const fixture = setup({ getProject: () => of(detail()), uploadFiles: () => throwError(() => ({ status: 413, error: { detail: 'big.xlsx exceeds the 50 MB upload limit' } })) });
    fixture.componentInstance.upload([new File(['x'], 'big.xlsx')]);
    fixture.detectChanges();
    await tick();
    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('exceeds the 50 MB');
    expect(document.activeElement).toBe(alert);
  });

  it('polls while files are active and stops when they finish', () => {
    vi.useFakeTimers();
    try {
      const responses = [detail({ report_built: false, stage: 'processing', files: [file({ status: 'queued' })] }), detail({ files: [file({ status: 'processed' })] })];
      const getProject = vi.fn(() => of(responses.shift() ?? detail()));
      const fixture = setup({ getProject });
      expect(fixture.nativeElement.querySelector('[role="status"]').textContent).toContain('processing');
      vi.advanceTimersByTime(2100);
      fixture.detectChanges();
      expect(getProject).toHaveBeenCalledTimes(2);
      expect(fixture.nativeElement.querySelector('[role="status"]').textContent).toContain('All 1 files finished');
      vi.advanceTimersByTime(5000);
      expect(getProject).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reports a refused type change (409) without losing the page', async () => {
    const fixture = setup({ getProject: () => of(detail()), patchFile: () => throwError(() => ({ status: 409, error: { detail: 'fin.xlsx is still processing' } })) });
    fixture.componentInstance.override(file(), 'yardi_rent_roll');
    fixture.detectChanges();
    await tick();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('still processing');
    expect(fixture.nativeElement.querySelector('table')).not.toBeNull();
  });

  it('uploads report images and shows the current one', () => {
    const put = vi.fn(() => of({ cover: true, logo: false }));
    const fixture = setup({ getProject: () => of(detail({ assets: { cover: true, logo: false } })), putAsset: put, deleteAsset: () => of({ cover: false, logo: false }) });
    const input = document.createElement('input');
    input.type = 'file';
    Object.defineProperty(input, 'files', { value: [new File(['png'], 'c.png')], configurable: true });
    fixture.componentInstance.onAsset('cover', { target: input } as unknown as Event);
    expect(put).toHaveBeenCalledWith('p1', 'cover', expect.any(File));
    expect(fixture.nativeElement.querySelector('img.thumb')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('button.link.danger')?.textContent).toContain('Remove');
  });

  it('explains an unreachable backend', () => {
    const fixture = setup({ getProject: () => throwError(() => backendDown) });
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('not reachable');
  });

  it('keeps the dropzone keyboard operable', () => {
    const fixture = setup({ getProject: () => of(detail()) });
    const zone = fixture.nativeElement.querySelector('label.dropzone') as HTMLElement;
    expect(zone.getAttribute('tabindex')).toBe('0');
    const click = vi.spyOn(fixture.componentInstance.picker().nativeElement, 'click');
    zone.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    expect(click).toHaveBeenCalled();
  });
});
