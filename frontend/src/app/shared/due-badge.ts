import { Component, computed, input } from '@angular/core';

import { ReminderKind } from '../core/models';

/** Etichetta colorata che riassume quanto manca a un promemoria.
 *
 * Il verbo segue il tipo: una scadenza «scade», un appuntamento no. Dire
 * «scade domani» di una riunione è italiano sbagliato, non una sfumatura.
 */
@Component({
  selector: 'app-due-badge',
  template: `<span class="badge" [class]="'badge badge-' + tone()">{{ label() }}</span>`,
})
export class DueBadge {
  readonly days = input.required<number>();
  readonly done = input(false);
  readonly kind = input<ReminderKind>('deadline');

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
    const scadenza = this.kind() === 'deadline';
    if (this.done()) return scadenza ? 'Evasa' : 'Fatto';

    const d = this.days();
    if (d < 0) {
      const gg = Math.abs(d);
      return scadenza ? `Scaduta da ${gg} gg` : `${gg} gg fa`;
    }
    if (d === 0) return scadenza ? 'Scade oggi' : 'Oggi';
    if (d === 1) return scadenza ? 'Scade domani' : 'Domani';
    return `Tra ${d} gg`;
  });
}
