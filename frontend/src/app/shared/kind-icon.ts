import { Component, computed, input } from '@angular/core';

import { KIND_LABELS, ReminderKind } from '../core/models';

/** Il simbolo del tipo di promemoria: sveglia, calendario, pallino.
 *
 * Disegnate a mano invece che con le emoji perché le emoji portano con sé i
 * propri colori — un rosso e un azzurro accesi che nel mezzo di una riga di
 * testo saltano all'occhio più del titolo. Queste usano `currentColor`, quindi
 * prendono il colore di chi le contiene e stanno in riga con le etichette.
 */
@Component({
  selector: 'app-kind-icon',
  template: `
    <svg
      class="kind-icon"
      viewBox="0 0 16 16"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
      stroke-linejoin="round"
      role="img"
      [attr.aria-label]="label()"
    >
      @switch (kind()) {
        @case ('deadline') {
          <!-- Sveglia: quadrante, lancette e i due piedini che la distinguono
               da un orologio qualunque anche a 14 pixel. -->
          <circle cx="8" cy="9" r="5.2" />
          <path d="M8 6.4V9l1.8 1.1" />
          <path d="M3.4 3.6 1.9 5.1M12.6 3.6l1.5 1.5" />
        }
        @case ('appointment') {
          <!-- Calendario: foglio, anelli e la riga dell'intestazione. -->
          <rect x="2.2" y="3.4" width="11.6" height="10.4" rx="1.6" />
          <path d="M2.2 6.6h11.6M5.6 2.2v2.4M10.4 2.2v2.4" />
        }
        @default {
          <circle cx="8" cy="8" r="4.4" />
        }
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
    }
    .kind-icon {
      /* Allineata al testo: senza, l'icona "galleggia" sopra la riga. */
      vertical-align: -0.15em;
    }
  `,
})
export class KindIcon {
  readonly kind = input.required<ReminderKind>();

  readonly label = computed(() => KIND_LABELS[this.kind()]);
}
