import { HttpErrorResponse } from '@angular/common/http';

/** Traduce l'errore di una chiamata in una frase che dice cosa è successo.
 *
 * Nasce da un «errore imprevisto» mostrato per un backend spento: il caso più
 * comune — l'applicazione non risponde — finiva nello stesso messaggio muto
 * degli altri, e chi lo leggeva non aveva modo di capire se il problema era
 * nel dato inserito o nel collegamento.
 *
 * Angular usa `status: 0` quando la richiesta non è mai arrivata a
 * destinazione: server fermo, rete assente, indirizzo sbagliato.
 */
export function describeError(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0) {
      return 'impossibile contattare il server (applicazione non in esecuzione?)';
    }
    // Il backend spiega i suoi rifiuti in `detail`: quando c'è, vince su tutto.
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (err.status === 503) {
      return 'database condiviso non raggiungibile';
    }
    return `errore del server (${err.status})`;
  }

  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' ? detail : 'errore imprevisto';
}
