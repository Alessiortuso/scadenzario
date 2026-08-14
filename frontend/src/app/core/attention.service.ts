import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';

/** Ponte verso il processo Electron, quando si gira come app desktop. */
interface DesktopBridge {
  segnalaLettura?: () => void;
}

/**
 * Spegne la segnalazione insistente sulla barra delle applicazioni.
 *
 * L'accensione la decide il processo Electron interrogando il backend; qui si
 * gestisce solo il momento in cui l'utente **guarda**, che è l'unica cosa che
 * la spegne. Aprire l'elenco dei promemoria o la scheda di uno di essi conta
 * come "preso atto": è la promessa fatta all'utente, cioè che un avviso
 * ignorato non sparisce da solo ma smette di insistere appena lo si affronta.
 */
@Injectable({ providedIn: 'root' })
export class AttentionService {
  private readonly api = inject(ApiService);

  /**
   * @param reminderId quando si apre un singolo promemoria: spegne solo il
   *   suo avviso, perché aver aperto una scheda non vuol dire aver guardato
   *   anche le altre.
   */
  async segnalaGuardato(reminderId?: number): Promise<void> {
    try {
      await firstValueFrom(this.api.attentionSeen(reminderId));
    } catch {
      // Non è un'operazione che l'utente ha chiesto: se fallisce, la
      // segnalazione resta accesa un giro in più e non si disturba nessuno.
      return;
    }

    // Senza questo il bollino resterebbe acceso fino al giro di controllo
    // successivo — fino a mezzo minuto dopo aver aperto l'elenco.
    const desktop = (window as unknown as { promemoria?: DesktopBridge }).promemoria;
    desktop?.segnalaLettura?.();
  }
}
