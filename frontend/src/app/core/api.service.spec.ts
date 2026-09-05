import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ApiService } from './api.service';
import { errorText } from './models';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('lists projects from /api/projects', () => {
    let got: unknown;
    api.listProjects().subscribe((p) => (got = p));
    const req = http.expectOne('/api/projects');
    expect(req.request.method).toBe('GET');
    req.flush([{ id: 'a', name: 'A' }]);
    expect(got).toEqual([{ id: 'a', name: 'A' }]);
  });

  it('uploads files as multipart form data under the "files" key', () => {
    api.uploadFiles('p1', [new File(['x'], 'a.xlsx'), new File(['y'], 'b.pdf')]).subscribe();
    const req = http.expectOne('/api/projects/p1/files');
    expect(req.request.method).toBe('POST');
    const fd = req.request.body as FormData;
    expect(fd.getAll('files').map((f) => (f as File).name)).toEqual(['a.xlsx', 'b.pdf']);
    req.flush([]);
  });

  it('sends corrections as a PATCH with changes, add_rows and delete_rows', () => {
    api.patchReportData('p1', { changes: [{ path: 'a.fields.b', value: 1 }], delete_rows: [{ table: 't', key: 'k' }] }).subscribe();
    const req = http.expectOne('/api/projects/p1/report-data');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ changes: [{ path: 'a.fields.b', value: 1 }], delete_rows: [{ table: 't', key: 'k' }] });
    req.flush({});
  });

  it('builds download, snapshot and asset URLs', () => {
    expect(api.downloadUrl('p1', 'r2')).toBe('/api/projects/p1/reports/r2/download');
    expect(api.snapshotUrl('p1', 'r2')).toBe('/api/projects/p1/reports/r2/snapshot');
    expect(api.assetUrl('p1', 'cover')).toMatch(/^\/api\/projects\/p1\/assets\/cover\?t=\d+$/);
  });

  it('resets overrides through the recovery endpoint', () => {
    api.resetOverrides('p1', { paths: ['x.fields.y'] }).subscribe();
    const req = http.expectOne('/api/projects/p1/report-data/overrides/reset');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ paths: ['x.fields.y'] });
    req.flush({});
  });
});

describe('errorText', () => {
  it('prefers the backend detail, then explains an unreachable backend', () => {
    expect(errorText({ error: { detail: 'nope' }, message: 'x' })).toBe('nope');
    expect(errorText({ error: { detail: [{ msg: 'a' }, { msg: 'b' }] } })).toBe('a; b');
    expect(errorText({ status: 0, message: 'Http failure' })).toContain('not reachable');
    expect(errorText({ message: 'boom' })).toBe('boom');
  });
});
