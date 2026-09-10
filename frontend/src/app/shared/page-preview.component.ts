import { Component, ElementRef, computed, effect, inject, input, output, signal, viewChild } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

/** The report page box in CSS pixels: 10in x 5.625in at 96dpi, exactly as report.css lays it out. */
const PAGE_W = 960;
const PAGE_H = 540;

/**
 * The page of the live report that the section being edited prints on.
 *
 * The preview is one sandboxed document holding every page stacked in order, and a sandboxed frame
 * cannot be scripted or scrolled from here. So the frame is scaled to the pane and slid vertically by
 * whole pages instead — no scripting, and no second request when the reviewer moves between sections.
 */
@Component({
  selector: 'app-page-preview',
  standalone: true,
  template: `
    <figure class="page-view">
      <div class="page-view-frame" #box [style.height.px]="height()">
        <iframe [src]="src()" title="Live report preview" sandbox="" aria-hidden="true" tabindex="-1"
                [style.width.px]="pageWidth" [style.height.px]="totalHeight()"
                [style.transform]="'scale(' + scale() + ')'" [style.top.px]="offset()"></iframe>
      </div>
      <figcaption class="page-view-cap small">
        <span>Page {{ page() }} of the printed report</span>
        <button type="button" class="link small" (click)="refresh.emit()">refresh</button>
      </figcaption>
    </figure>`,
})
export class PagePreviewComponent {
  private sanitizer = inject(DomSanitizer);
  /** Preview URL. The parent changes it (a new cache-busting token) to pick up saved edits. */
  url = input.required<string>();
  /** Printed page to show, 1-based. */
  page = input.required<number>();
  /** Total pages in the preview, so the frame is tall enough for the last one. */
  pages = input(10);
  refresh = output<void>();

  readonly pageWidth = PAGE_W;
  private box = viewChild<ElementRef<HTMLElement>>('box');
  private width = signal(PAGE_W / 2);

  src = computed<SafeResourceUrl>(() => this.sanitizer.bypassSecurityTrustResourceUrl(this.url()));
  scale = computed(() => this.width() / PAGE_W);
  height = computed(() => Math.round(PAGE_H * this.scale()));
  totalHeight = computed(() => PAGE_H * Math.max(this.pages(), this.page()));
  offset = computed(() => -Math.round((this.page() - 1) * PAGE_H * this.scale()));

  constructor() {
    effect((onCleanup) => {
      const el = this.box()?.nativeElement;
      if (!el || typeof ResizeObserver === 'undefined') return;  // jsdom in the unit tests has no observer
      const ro = new ResizeObserver(([entry]) => this.width.set(entry.contentRect.width));
      ro.observe(el);
      onCleanup(() => ro.disconnect());
    });
  }
}
