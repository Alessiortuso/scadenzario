import { Injectable, signal } from '@angular/core';

/**
 * A che punto è l'aggiornamento dell'applicazione.
 *
 * - `inattivo` — non è stato chiesto niente;
 * - `controllo` — si sta guardando se esiste una versione più recente;
 * - `scaricamento` — pacchetto in arrivo, con la percentuale quando si sa;
 * - `pronto` — scaricato, manca solo il riavvio;
 * - `riavvio` — l'installer sta partendo, l'applicazione si sta chiudendo;
 * - `nessuno` — questa è già l'ultima versione pubblicata;
 * - `errore` — non si è riusciti, il motivo è in `dettaglio`;
 * - `non-disponibile` — non siamo nell'app installata (sviluppo, o browser).
 */
export type FaseAggiornamento =
  | 'inattivo'
  | 'controllo'
  | 'scaricamento'
  | 'pronto'
  | 'riavvio'
  | 'nessuno'
  | 'errore'
  | 'non-disponibile';

export interface StatoAggiornamento {
  fase: FaseAggiornamento;
  versione?: string;
  percento?: number;
  dettaglio?: string;
}

interface PonteAggiornamento {
  stato(): Promise<{
    disponibile: boolean;
    versioneCorrente: string;
    stato: StatoAggiornamento | null;
  }>;
  avvia(): Promise<StatoAggiornamento>;
  onStato(callback: (stato: StatoAggiornamento) => void): () => void;
}

interface PonteDesktop {
  aggiornamento?: PonteAggiornamento;
}

/**
 * Comanda l'aggiornamento dell'applicazione dall'interfaccia.
 *
 * Esiste per una situazione precisa: una postazione che non si collega più
 * perché il database condiviso è stato migrato da un'altra, già aggiornata.
 * Il rimedio è aggiornare, e va offerto lì dove il guasto si vede — chiedere
 * a chi usa il programma di andare su GitHub a cercare un installer è un
 * passaggio che si perde per strada, e intanto quel computer non lavora.
 *
 * Fuori dall'applicazione installata il ponte non c'è: nel browser, o in
 * sviluppo, resta `non-disponibile` e la schermata non mostra il pulsante
 * invece di mostrarne uno che non farebbe niente.
 */
@Injectable({ providedIn: 'root' })
export class AggiornamentoService {
  readonly stato = signal<StatoAggiornamento>({ fase: 'inattivo' });
  readonly disponibile = signal(false);
  readonly versioneCorrente = signal<string | null>(null);

  private ponte: PonteAggiornamento | null = null;
  private annullaAscolto: (() => void) | null = null;

  /**
   * Si lega al processo principale e recupera quello che è già successo.
   *
   * Il recupero non è un dettaglio: il controllo automatico parte all'avvio e
   * finisce molto prima che qualcuno arrivi su questa schermata. Senza
   * chiederlo, la pagina mostrerebbe un pulsante da premere accanto a un
   * pacchetto già scaricato e pronto.
   */
  async collega(): Promise<void> {
    this.ponte =
      (window as unknown as { promemoria?: PonteDesktop }).promemoria?.aggiornamento ?? null;

    if (this.ponte === null) {
      this.stato.set({ fase: 'non-disponibile' });
      return;
    }

    this.annullaAscolto?.();
    this.annullaAscolto = this.ponte.onStato((stato) => this.stato.set(stato));

    try {
      const corrente = await this.ponte.stato();
      this.disponibile.set(corrente.disponibile);
      this.versioneCorrente.set(corrente.versioneCorrente);
      this.stato.set(
        corrente.disponibile
          ? (corrente.stato ?? { fase: 'inattivo' })
          : { fase: 'non-disponibile' },
      );
    } catch {
      this.stato.set({ fase: 'non-disponibile' });
    }
  }

  scollega(): void {
    this.annullaAscolto?.();
    this.annullaAscolto = null;
  }

  /**
   * Cerca l'aggiornamento e, se c'è già ed è pronto, riavvia per applicarlo.
   *
   * Da qui in avanti l'avanzamento arriva dagli eventi: questo ritorno serve
   * per i casi che eventi non ne producono — non c'è niente da scaricare, o il
   * controllo stesso è fallito.
   */
  async avvia(): Promise<void> {
    if (this.ponte === null) return;
    this.stato.set({ fase: 'controllo' });
    try {
      this.stato.set(await this.ponte.avvia());
    } catch (err) {
      this.stato.set({ fase: 'errore', dettaglio: String(err) });
    }
  }
}
