import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { backendDown, detail422 } from '../../testing/fixtures';
import { ProjectsComponent } from './projects.component';

const tick = () => new Promise((r) => setTimeout(r, 0));

function setup(api: Partial<Record<keyof ApiService, unknown>>) {
  TestBed.configureTestingModule({ providers: [provideRouter([]), { provide: ApiService, useValue: api }] });
  const fixture = TestBed.createComponent(ProjectsComponent);
  fixture.detectChanges();
  return fixture;
}

describe('ProjectsComponent', () => {
  it('lists projects and links to their files page', () => {
    const fixture = setup({ listProjects: () => of([{ id: 'a1', name: 'Boardwalk', created_at: '', updated_at: '2026-09-05T10:00:00', file_count: 3 }]) });
    const el: HTMLElement = fixture.nativeElement;
    const link = el.querySelector('.project-card-link')!;
    expect(link.querySelector('.card-title')!.textContent).toBe('Boardwalk');
    expect(link.getAttribute('href')).toBe('/projects/a1/files');
    expect(el.querySelector('button[aria-label="Delete Boardwalk"]')).not.toBeNull();
  });

  it('creates a project and navigates to its files page', () => {
    const create = vi.fn(() => of({ id: 'new1', name: 'X' }));
    const fixture = setup({ listProjects: () => of([]), createProject: create });
    const nav = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture.componentInstance.name = '  X ';
    fixture.componentInstance.create();
    expect(create).toHaveBeenCalledWith('X');
    expect(nav).toHaveBeenCalledWith(['/projects', 'new1', 'files']);
  });

  it('shows the backend detail when creation fails and keeps the form usable', async () => {
    const fixture = setup({ listProjects: () => of([]), createProject: () => throwError(() => detail422('name too long')) });
    fixture.componentInstance.name = 'X';
    fixture.componentInstance.create();
    fixture.detectChanges();
    await tick();
    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('name too long');
    expect(document.activeElement).toBe(alert);
    expect(fixture.componentInstance.busy()).toBe(false);
  });

  it('explains an unreachable backend on load', () => {
    const fixture = setup({ listProjects: () => throwError(() => backendDown) });
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('not reachable');
    expect(fixture.componentInstance.loading()).toBe(false);
  });
});
