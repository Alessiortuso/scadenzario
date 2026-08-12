import { Component, computed, input } from '@angular/core';

import { Priority } from '../core/models';

/** Etichetta della priorità di una scadenza.
 *
 * Bassa e normale restano volutamente smorzate: sono la maggioranza delle
 * scadenze, e colorarle tutte toglierebbe risalto proprio a quelle che devono
 * saltare all'occhio.
 */
@Component({
  selector: 'app-priority-badge',
  template: `<span class="badge" [class]="'badge badge-' + tone()">{{ label() }}</span>`,
})
export class PriorityBadge {
  readonly priority = input.required<Priority>();

  readonly tone = computed(() => {
    switch (this.priority()) {
      case 'critical':
        return 'danger';
      case 'high':
        return 'warning';
      default:
        return 'neutral';
    }
  });

  readonly label = computed(() => {
    switch (this.priority()) {
      case 'critical':
        return 'Critica';
      case 'high':
        return 'Alta';
      case 'low':
        return 'Bassa';
      default:
        return 'Normale';
    }
  });
}
