import { TestBed } from '@angular/core/testing';
import { StepperComponent } from './stepper.component';

describe('StepperComponent', () => {
  it('marks the active step with aria-current and earlier steps as done', () => {
    const fixture = TestBed.createComponent(StepperComponent);
    fixture.componentRef.setInput('stage', 'review');
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const current = el.querySelector('li[aria-current="step"]')!;
    expect(current.textContent).toContain('Review');
    expect(el.querySelectorAll('li.done').length).toBe(3);
    expect(el.querySelector('nav')!.getAttribute('aria-label')).toBe('Workflow progress');
  });
});
