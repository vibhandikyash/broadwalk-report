// frontend/src/app/shared/stepper.component.ts
import { Component, computed, input } from '@angular/core';
import { Stage } from '../core/models';

const STEPS = ['Upload', 'Process', 'Extract', 'Review', 'Correct', 'Generate', 'Download'];
const ACTIVE: Record<Stage, number> = { upload: 0, processing: 1, review: 3, generated: 6 };

@Component({
  selector: 'app-stepper',
  standalone: true,
  template: `
    <ol class="stepper">
      @for (s of steps; track s; let i = $index) {
        <li [class.done]="i < active()" [class.active]="i === active()"><span class="n">{{ i + 1 }}</span>{{ s }}</li>
      }
    </ol>`,
})
export class StepperComponent {
  stage = input<Stage>('upload');
  steps = STEPS;
  active = computed(() => ACTIVE[this.stage()] ?? 0);
}
