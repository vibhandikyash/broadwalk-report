import { Injectable, computed, signal } from '@angular/core';
import { Origin, ProjectDetail } from './models';

/** The three bands of the header's progress bar, in the order they stack. */
export interface Mix { ex: string; co: string; mi: string; resolved: number; total: number; }

/**
 * What the one header across the top needs to know. There is a single bar on every screen — brand,
 * the five destinations, the draft chip and the progress of the report — so the project context has
 * to outlive the routed page that loaded it. Each project page writes here as its data arrives, and
 * clears it on the way out; the header only reads.
 */
@Injectable({ providedIn: 'root' })
export class ShellStore {
  readonly project = signal<ProjectDetail | null>(null);
  /** Outstanding review items, when a page knows them; null hides the chip. */
  readonly gaps = signal<number | null>(null);
  /** Values per origin, from the consolidated report data; null hides the bar. */
  readonly origins = signal<Partial<Record<Origin, number>> | null>(null);
  /** Unsaved edits: leaving for the report would silently drop them, so that tab is held. */
  readonly blocked = signal(false);

  setProject(p: ProjectDetail | null): void { this.project.set(p); }
  clear(): void { this.project.set(null); this.gaps.set(null); this.origins.set(null); this.blocked.set(false); }

  /** OCR-recovered values count as extracted and AI drafts as still open: the bar answers
   *  "is this number settled?", not "which code path produced it". */
  readonly mix = computed<Mix | null>(() => {
    const c = this.origins();
    if (!c) return null;
    const ex = (c.extracted ?? 0) + (c.ocr ?? 0) + (c.manual ?? 0);
    const co = c.computed ?? 0;
    const mi = (c.missing ?? 0) + (c.ai_draft ?? 0);
    const total = ex + co + mi;
    if (!total) return null;
    const pct = (n: number) => ((n / total) * 100).toFixed(1) + '%';
    return { ex: pct(ex), co: pct(co), mi: pct(mi), resolved: ex + co, total };
  });
}
