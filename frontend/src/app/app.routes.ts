// app.routes.ts
import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'projects', pathMatch: 'full' },
  { path: 'projects', loadComponent: () => import('./pages/projects/projects.component').then((m) => m.ProjectsComponent) },
  { path: 'projects/:id/files', loadComponent: () => import('./pages/files/files.component').then((m) => m.FilesComponent) },
  { path: 'projects/:id/review', loadComponent: () => import('./pages/review/review.component').then((m) => m.ReviewComponent) },
  { path: 'projects/:id/report', loadComponent: () => import('./pages/report/report.component').then((m) => m.ReportComponent) },
  { path: '**', redirectTo: 'projects' },
];
