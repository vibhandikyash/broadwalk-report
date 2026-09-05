import { Component, computed, input } from '@angular/core';
import { Stage } from '../core/models';

const STEPS = ['Upload', 'Process', 'Extract', 'Review', 'Correct', 'Generate', 'Download'];
const ACTIVE: Record<Stage, number> = { upload: 0, processing: 1, review: 3, generated: 6 };

@Component({
  selector: 'app-stepper',
  standalone: true,
  template: `
    <nav aria-label="Workflow progress">
      <ol class="stepper">
        @for (s of steps; track s; let i = $index) {
          <li [class.done]="i < active()" [class.active]="i === active()" [attr.aria-current]="i === active() ? 'step' : null">
            <span class="n" aria-hidden="true">{{ i + 1 }}</span>{{ s }}@if (i < active()) { <span class="sr-only"> (done)</span> }
          </li>
        }
      </ol>
    </nav>`,
})
export class StepperComponent {
  stage = input<Stage>('upload');
  steps = STEPS;
  active = computed(() => ACTIVE[this.stage()] ?? 0);
}
