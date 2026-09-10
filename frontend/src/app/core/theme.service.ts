import { Injectable, signal } from '@angular/core';

const KEY = 'irg-theme';

/**
 * Light or dark, as a class on <body> — the Organic token sheet redefines the whole ground under
 * `body.dark`, so one class is the whole switch. The choice is remembered; with no stored choice the
 * operating system decides, and keeps deciding until the reader overrides it here.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly dark = signal(false);

  constructor() {
    let dark = false;
    try {
      const stored = localStorage.getItem(KEY);
      dark = stored ? stored === 'dark' : !!globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches;
    } catch {
      dark = false;  // private browsing, or no DOM at all under the unit tests
    }
    this.apply(dark);
  }

  toggle(): void { this.apply(!this.dark()); }

  private apply(dark: boolean): void {
    this.dark.set(dark);
    document.body?.classList.toggle('dark', dark);
    try { localStorage.setItem(KEY, dark ? 'dark' : 'light'); } catch { /* nothing to remember it with */ }
  }
}
