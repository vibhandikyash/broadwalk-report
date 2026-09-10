import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { AppComponent } from './app.component';
import { ApiService } from './core/api.service';
import { ShellStore } from './core/shell.store';
import { detail } from './testing/fixtures';

const health = { ok: true, llm_enabled: false, llm_provider: null, pdf_renderer: true, workers: 3 };

function setup() {
  // A stub target so the header's navigation handling can actually be exercised.
  const routes = [{ path: 'projects', children: [] }, { path: 'projects/:id/files', children: [] }];
  TestBed.configureTestingModule({ providers: [provideRouter(routes), { provide: ApiService, useValue: { health: () => of(health) } }] });
  const fixture = TestBed.createComponent(AppComponent);
  fixture.detectChanges();
  return fixture;
}

const tabs = (el: HTMLElement) => Array.from(el.querySelectorAll('.tabs .tab') as NodeListOf<HTMLElement>);
const tab = (el: HTMLElement, label: string) => tabs(el).find((t) => t.textContent!.trim() === label)!;

describe('AppComponent header', () => {
  it('offers the four destinations, with the project ones held until a project is open', () => {
    const fixture = setup();
    const el: HTMLElement = fixture.nativeElement;
    expect(tabs(el).map((t) => t.textContent!.trim())).toEqual(['Projects', 'Files', 'Review', 'Report']);
    expect(el.querySelector('.project-id h1')!.textContent).toContain('All reports');
    for (const label of ['Files', 'Review', 'Report']) {
      expect((tab(el, label) as HTMLButtonElement).disabled).toBe(true);
    }
    expect(tab(el, 'Projects').getAttribute('href')).toBe('/projects');
  });

  it('names the open project and opens Files before the data is built', () => {
    const fixture = setup();
    TestBed.inject(ShellStore).setProject(detail({ report_built: false }));
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.project-id h1')!.textContent).toContain('Boardwalk');
    expect(tab(el, 'Files').getAttribute('href')).toBe('/projects/p1/files');
    for (const label of ['Review', 'Report']) {
      const held = tab(el, label) as HTMLButtonElement;
      expect(held.disabled).toBe(true);
      expect(held.title).toContain('once the files have been processed');
    }
  });

  it('holds the report tab while the review has unsaved edits', () => {
    const fixture = setup();
    const shell = TestBed.inject(ShellStore);
    shell.setProject(detail());
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(tab(el, 'Report').getAttribute('href')).toBe('/projects/p1/report');
    shell.blocked.set(true);
    fixture.detectChanges();
    const held = tab(el, 'Report') as HTMLButtonElement;
    expect(held.disabled).toBe(true);
    expect(held.title).toContain('Save or discard');
  });

  it('drops a project’s context on the way out, including straight to another project', async () => {
    const fixture = setup();
    const shell = TestBed.inject(ShellStore);
    const router = TestBed.inject(Router);
    shell.setProject(detail());
    shell.gaps.set(12);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.chip-draft')).not.toBeNull();
    await router.navigateByUrl('/projects/p9/files');  // a different project: p1's numbers are not p9's
    fixture.detectChanges();
    expect(shell.project()).toBeNull();
    expect(shell.gaps()).toBeNull();
    expect(fixture.nativeElement.querySelector('.chip-draft')).toBeNull();
  });

  it('keeps the index reachable from inside a project', async () => {
    const fixture = setup();
    const shell = TestBed.inject(ShellStore);
    await TestBed.inject(Router).navigateByUrl('/projects/p1/files');
    shell.setProject(detail());
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    // /projects/p1/files sits under /projects, but only the index itself is the Projects page
    expect(tab(el, 'Projects').tagName).toBe('A');
    expect(tab(el, 'Projects').getAttribute('href')).toBe('/projects');
    expect(el.querySelectorAll('.tab.current').length).toBe(1);
    expect(el.querySelector('.tab.current')!.textContent!.trim()).toBe('Files');
  });

  it('shows the draft chip and the resolved-values bar from the report data', () => {
    const fixture = setup();
    const shell = TestBed.inject(ShellStore);
    shell.setProject(detail());
    shell.gaps.set(36);
    shell.origins.set({ extracted: 556, ocr: 0, computed: 293, manual: 0, ai_draft: 0, missing: 72 });
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.chip-draft')!.textContent).toContain('36 outstanding');
    expect(el.querySelector('.progress-line')!.textContent).toContain('849 of 921 values resolved');
    shell.gaps.set(0);
    fixture.detectChanges();
    expect(el.querySelector('.chip-done')!.textContent).toContain('complete');
  });
});
