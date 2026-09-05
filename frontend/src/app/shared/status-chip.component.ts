import { Component, input } from '@angular/core';

const LABELS: Record<string, string> = {
  extracted: 'extracted', derived: 'derived', manual: 'edited', ai_draft: 'AI draft', missing: 'missing', conflict: 'conflict',
  queued: 'queued', processing: 'processing', processed: 'processed', failed: 'failed', unsupported: 'unsupported',
  unrecognized: 'not recognised', needs_ocr: 'needs OCR', rendering: 'rendering', done: 'done',
};

@Component({
  selector: 'app-status-chip',
  standalone: true,
  template: `<span class="chip chip-{{ status() }}">{{ label }}</span>`,
})
export class StatusChipComponent {
  status = input.required<string>();
  get label(): string { return LABELS[this.status()] ?? this.status(); }
}
