import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { backendDown, detail, report, routeStub, uiData } from '../../testing/fixtures';
import { ReportComponent } from './report.component';

const tick = () => new Promise((r) => setTimeout(r, 0));

function setup(api: Partial<Record<keyof ApiService, unknown>>) {
  const base = { previewUrl: () => '/api/projects/p1/report/preview', downloadUrl: (p: string, r: string) => `/api/projects/${p}/reports/${r}/download`,
                 snapshotUrl: (p: string, r: string) => `/api/projects/${p}/reports/${r}/snapshot`, reportData: () => of(uiData()) };
  TestBed.configureTestingModule({ providers: [provideRouter([]), routeStub(), { provide: ApiService, useValue: { ...base, ...api } }] });
  const fixture = TestBed.createComponent(ReportComponent);
  fixture.detectChanges();
  return fixture;
}

describe('ReportComponent', () => {
  it('lists versions with download and snapshot links and a sandboxed preview', () => {
    const fixture = setup({ getProject: () => of(detail({ reports: [report(), report({ id: 'r2', version: 2, status: 'failed', error: 'page 8 is 40 pt too tall', has_pdf: false })] })) });
    const el: HTMLElement = fixture.nativeElement;
    const links = Array.from(el.querySelectorAll('.version a') as NodeListOf<HTMLAnchorElement>).map((a) => a.getAttribute('href'));
    expect(links).toEqual(['/api/projects/p1/reports/r1/download', '/api/projects/p1/reports/r1/snapshot']);
    expect(el.textContent).toContain('page 8 is 40 pt too tall');
    expect(el.querySelector('iframe')!.getAttribute('sandbox')).toBe('');
    expect(el.querySelector('.warn')!.textContent).toContain('1 missing values');
  });

  it('generates a version and announces completion after polling', () => {
    vi.useFakeTimers();
    try {
      const lists = [[report({ status: 'rendering', has_pdf: false })], [report({ status: 'done' })]];
      const list = vi.fn(() => of(lists.shift() ?? [report()]));
      const fixture = setup({ getProject: () => of(detail()), createReport: () => of(report({ status: 'queued' })), listReports: list });
      fixture.componentInstance.generate();
      fixture.detectChanges();
      expect(fixture.componentInstance.generating()).toBe(true);
      expect(fixture.nativeElement.querySelector('nav button').textContent).toContain('Rendering');
      vi.advanceTimersByTime(1600);
      fixture.detectChanges();
      expect(fixture.componentInstance.generating()).toBe(true);
      vi.advanceTimersByTime(1600);
      fixture.detectChanges();
      expect(fixture.componentInstance.generating()).toBe(false);
      expect(fixture.nativeElement.querySelector('[role="status"]').textContent).toContain('PDF version 1 is ready');
      expect(fixture.nativeElement.querySelector('a.btn.small')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows a failed version with its reason', () => {
    vi.useFakeTimers();
    try {
      const list = vi.fn(() => of([report({ status: 'failed', error: 'Content does not fit the page: page 10 (Status Update) is 30 pt too tall', has_pdf: false })]));
      const fixture = setup({ getProject: () => of(detail()), createReport: () => of(report({ status: 'queued' })), listReports: list });
      fixture.componentInstance.generate();
      vi.advanceTimersByTime(1600);
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('[role="status"]').textContent).toContain('Version 1 failed');
      expect(fixture.nativeElement.querySelector('.version .err').textContent).toContain('page 10');
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows the backend detail when generation is refused', async () => {
    const fixture = setup({ getProject: () => of(detail()), createReport: () => throwError(() => ({ status: 409, error: { detail: 'Report data has not been built yet' } })) });
    fixture.componentInstance.generate();
    fixture.detectChanges();
    await tick();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('not been built');
    expect(fixture.componentInstance.generating()).toBe(false);
  });

  it('explains an unreachable backend', () => {
    const fixture = setup({ getProject: () => throwError(() => backendDown), reportData: () => throwError(() => backendDown) });
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('not reachable');
  });
});
