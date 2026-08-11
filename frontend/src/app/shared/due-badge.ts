import { Component, computed, input } from '@angular/core';

/** Etichetta colorata che riassume quanto manca a una scadenza. */
@Component({
  selector: 'app-due-badge',
  template: `<span class="badge" [class]="'badge badge-' + tone()">{{ label() }}</span>`,
})
export class DueBadge {
  readonly days = input.required<number>();
  readonly done = input(false);

  readonly tone = computed(() => {
    if (this.done()) return 'neutral';
    const d = this.days();
    if (d < 0) return 'danger';
    if (d <= 1) return 'danger';
    if (d <= 7) return 'warning';
    if (d <= 30) return 'info';
    return 'neutral';
  });

  readonly label = computed(() => {
    if (this.done()) return 'Evasa';
    const d = this.days();
    if (d < 0) return `Scaduta da ${Math.abs(d)} gg`;
    if (d === 0) return 'Scade oggi';
    if (d === 1) return 'Scade domani';
    return `Tra ${d} gg`;
  });
}
