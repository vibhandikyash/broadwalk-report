import { SlicePipe } from '@angular/common';
import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { Project, errorText } from '../../core/models';

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [FormsModule, RouterLink, SlicePipe],
  template: `
    <h1>Reports</h1>
    <form class="row" (ngSubmit)="create()">
      <label for="new-name" class="sr-only">New report name</label>
      <input id="new-name" name="name" [(ngModel)]="name" placeholder="New report name, e.g. The Boardwalk 2Q26" required />
      <button type="submit" [disabled]="!name.trim() || busy()">Create</button>
    </form>
    @if (error()) { <p class="err" role="alert" tabindex="-1" #alert>{{ error() }}</p> }
    @if (loading()) { <p class="muted" role="status">Loading…</p> }
    <table class="grid">
      <caption class="sr-only">Report projects</caption>
      <thead><tr><th scope="col">Name</th><th scope="col">Files</th><th scope="col">Updated</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>
        @for (p of projects(); track p.id) {
          <tr>
            <td><a [routerLink]="['/projects', p.id, 'files']">{{ p.name }}</a></td>
            <td>{{ p.file_count ?? 0 }}</td>
            <td>{{ p.updated_at | slice: 0 : 16 }}</td>
            <td class="r"><button type="button" class="link danger" (click)="remove(p)" [attr.aria-label]="'Delete ' + p.name">Delete</button></td>
          </tr>
        } @empty {
          @if (!loading()) { <tr><td colspan="4" class="muted">No reports yet. Create one above.</td></tr> }
        }
      </tbody>
    </table>`,
})
export class ProjectsComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  alert = viewChild<ElementRef<HTMLElement>>('alert');
  projects = signal<Project[]>([]);
  name = '';
  busy = signal(false);
  loading = signal(true);
  error = signal<string | null>(null);

  constructor() { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.listProjects().subscribe({ next: (ps) => { this.projects.set(ps); this.loading.set(false); }, error: (e) => { this.loading.set(false); this.fail(errorText(e)); } });
  }

  fail(msg: string): void {
    this.error.set(msg);
    setTimeout(() => this.alert()?.nativeElement.focus(), 0);
  }

  create(): void {
    if (!this.name.trim()) return;
    this.busy.set(true);
    this.api.createProject(this.name.trim()).subscribe({
      next: (p) => { this.busy.set(false); this.router.navigate(['/projects', p.id, 'files']); },
      error: (e) => { this.busy.set(false); this.fail(errorText(e)); },
    });
  }

  remove(p: Project): void {
    if (!confirm(`Delete "${p.name}" and all its files and reports?`)) return;
    this.api.deleteProject(p.id).subscribe({ next: () => this.load(), error: (e) => this.fail(errorText(e)) });
  }
}
