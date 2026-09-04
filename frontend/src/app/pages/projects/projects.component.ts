import { SlicePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { Project } from '../../core/models';

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [FormsModule, RouterLink, SlicePipe],
  template: `
    <h1>Reports</h1>
    <form class="row" (ngSubmit)="create()">
      <input name="name" [(ngModel)]="name" placeholder="New report name, e.g. The Boardwalk 2Q26" required />
      <button type="submit" [disabled]="!name.trim() || busy()">Create</button>
    </form>
    @if (error()) { <p class="err">{{ error() }}</p> }
    <table class="grid">
      <thead><tr><th>Name</th><th>Files</th><th>Updated</th><th></th></tr></thead>
      <tbody>
        @for (p of projects(); track p.id) {
          <tr>
            <td><a [routerLink]="['/projects', p.id, 'files']">{{ p.name }}</a></td>
            <td>{{ p.file_count ?? 0 }}</td>
            <td>{{ p.updated_at | slice: 0 : 16 }}</td>
            <td class="r"><button class="link danger" (click)="remove(p)">Delete</button></td>
          </tr>
        } @empty {
          <tr><td colspan="4" class="muted">No reports yet. Create one above.</td></tr>
        }
      </tbody>
    </table>`,
})
export class ProjectsComponent {
  private api = inject(ApiService);
  private router = inject(Router);
  projects = signal<Project[]>([]);
  name = '';
  busy = signal(false);
  error = signal<string | null>(null);

  constructor() { this.load(); }

  load(): void { this.api.listProjects().subscribe({ next: (ps) => this.projects.set(ps), error: (e) => this.error.set(e.message) }); }

  create(): void {
    this.busy.set(true);
    this.api.createProject(this.name.trim()).subscribe({
      next: (p) => { this.busy.set(false); this.router.navigate(['/projects', p.id, 'files']); },
      error: (e) => { this.busy.set(false); this.error.set(e.error?.detail ?? e.message); },
    });
  }

  remove(p: Project): void {
    if (!confirm(`Delete "${p.name}" and all its files and reports?`)) return;
    this.api.deleteProject(p.id).subscribe({ next: () => this.load(), error: (e) => this.error.set(e.message) });
  }
}
