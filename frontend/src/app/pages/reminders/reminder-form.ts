import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AttentionService } from '../../core/attention.service';
import { describeError } from '../../core/describe-error';
import { AppNotification, Occurrence, Reminder, ReminderKind } from '../../core/models';
import { NotificationStore } from '../../core/notification.store';
import { ToastService } from '../../core/toast.service';
import { KindIcon } from '../../shared/kind-icon';

@Component({
  selector: 'app-reminder-form',
  imports: [ReactiveFormsModule, RouterLink, DatePipe, CurrencyPipe, KindIcon],
  templateUrl: './reminder-form.html',
  styleUrl: './reminder-form.scss',
})
export class ReminderFormPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly toasts = inject(ToastService);
  private readonly notifications = inject(NotificationStore);
  private readonly attention = inject(AttentionService);

  /** Popolato dal router per la rotta /promemoria/:id. */
  readonly id = input<string | undefined>();

  readonly current = signal<Reminder | null>(null);
  readonly alerts = signal<AppNotification[]>([]);
  readonly saving = signal(false);
  readonly loading = signal(false);

  readonly isEdit = computed(() => this.current() !== null);

  readonly form = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.maxLength(255)]],
    kind: ['deadline'],
    due_date: ['', Validators.required],
    start_time: [''],
    recurrence: ['none'],
    recurrence_until: [''],
    amount: this.fb.control<number | null>(null),
    owner: [''],
    reference: [''],
    description: [''],
    alert_offsets: [''],
    notify_emails: [''],
  });

  /** Il tipo scelto ora, non quello salvato: le etichette cambiano subito. */
  readonly kind = signal<ReminderKind>('deadline');

  readonly dateLabel = computed(() =>
    this.kind() === 'appointment' ? 'Data appuntamento *' : 'Data *',
  );

  /** Una scadenza cade in un giorno, non a un'ora: il campo non la riguarda. */
  readonly showTime = computed(() => this.kind() !== 'deadline');

  /** Ricorrenza scelta ora, per far comparire i campi che la riguardano. */
  readonly recurrence = signal<Reminder['recurrence']>('none');
  readonly isRecurring = computed(() => this.recurrence() !== 'none');

  /** Le occorrenze della serie, con l'importo modificabile una per una. */
  readonly occurrences = signal<Occurrence[]>([]);
  readonly loadingOccurrences = signal(false);

  readonly totaleOccorrenze = computed(() =>
    this.occurrences().reduce((somma, o) => somma + (o.amount ?? 0), 0),
  );

  async ngOnInit(): Promise<void> {
    this.form.controls.recurrence.valueChanges.subscribe((r) => {
      this.recurrence.set(r as Reminder['recurrence']);
      if (r === 'none') {
        this.form.controls.recurrence_until.setValue('');
        this.occurrences.set([]);
      } else {
        void this.aggiornaOccorrenze();
      }
    });

    // Le occorrenze dipendono anche da data e importo di partenza.
    this.form.controls.recurrence_until.valueChanges.subscribe(() => void this.aggiornaOccorrenze());
    this.form.controls.due_date.valueChanges.subscribe(() => void this.aggiornaOccorrenze());

    this.form.controls.kind.valueChanges.subscribe((k) => {
      const kind = k as ReminderKind;
      this.kind.set(kind);
      // Passando a «scadenza» il campo sparisce: lasciarci dentro un orario
      // significherebbe salvarlo senza che nessuno lo veda più.
      if (kind === 'deadline') {
        this.form.controls.start_time.setValue('');
      }
    });

    this.loading.set(true);
    try {
      const id = Number(this.id());
      if (Number.isFinite(id) && id > 0) {
        const reminder = await firstValueFrom(this.api.getReminder(id));
        this.current.set(reminder);
        this.kind.set(reminder.kind);
        this.form.patchValue({
          title: reminder.title,
          kind: reminder.kind,
          due_date: reminder.due_date,
          // L'input orario vuole "HH:MM": con i secondi resta vuoto.
          start_time: reminder.start_time ? reminder.start_time.slice(0, 5) : '',
          recurrence: reminder.recurrence,
          recurrence_until: reminder.recurrence_until ?? '',
          amount: reminder.amount,
          owner: reminder.owner ?? '',
          reference: reminder.reference ?? '',
          description: reminder.description ?? '',
          alert_offsets: (reminder.alert_offsets ?? []).join(', '),
          notify_emails: (reminder.notify_emails ?? []).join(', '),
        });
        this.alerts.set(await firstValueFrom(this.api.reminderNotifications(id)));
        // Il promemoria è stato aperto: il suo avviso ha fatto il suo lavoro.
        void this.attention.segnalaGuardato(id);
      } else {
        // Arrivando da un giorno del calendario la data è già decisa: chiederla
        // di nuovo sarebbe farla scegliere due volte.
        const richiesta = this.route.snapshot.queryParamMap.get('data');
        const valida = richiesta !== null && /^\d{4}-\d{2}-\d{2}$/.test(richiesta);
        this.form.patchValue({
          due_date: valida ? richiesta : new Date().toLocaleDateString('sv'),
        });
      }
    } catch {
      this.toasts.error('Promemoria non trovato');
      void this.router.navigate(['/promemoria']);
    } finally {
      this.loading.set(false);
    }
  }

  /**
   * Chiede al server dove cadranno le occorrenze e prepara la tabella.
   *
   * Il calcolo delle date resta di là — mesi corti, fine mese, tetto massimo —
   * invece di essere riscritto qui e divergere alla prima differenza.
   *
   * Gli importi già digitati si conservano: cambiare la data di fine per
   * aggiungere una rata non deve cancellare le cifre inserite a mano.
   */
  private async aggiornaOccorrenze(): Promise<void> {
    const raw = this.form.getRawValue();
    if (raw.recurrence === 'none' || !raw.recurrence_until || !raw.due_date) {
      this.occurrences.set([]);
      return;
    }

    this.loadingOccurrences.set(true);
    try {
      const gia = new Map(this.occurrences().map((o) => [o.due_date, o.amount]));
      const calcolate = await firstValueFrom(
        this.api.occurrences({
          due_date: raw.due_date,
          recurrence: raw.recurrence as Reminder['recurrence'],
          recurrence_until: raw.recurrence_until,
          amount: raw.amount === null || String(raw.amount) === '' ? null : Number(raw.amount),
        }),
      );
      this.occurrences.set(
        calcolate.map((o) => ({ ...o, amount: gia.has(o.due_date) ? gia.get(o.due_date)! : o.amount })),
      );
    } catch {
      this.occurrences.set([]);
    } finally {
      this.loadingOccurrences.set(false);
    }
  }

  /** Importo di una singola occorrenza, digitato nella tabella. */
  setImporto(indice: number, valore: string): void {
    const importo = valore.trim() === '' ? null : Number(valore);
    this.occurrences.update((elenco) =>
      elenco.map((o, i) => (i === indice ? { ...o, amount: Number.isFinite(importo!) ? importo : null } : o)),
    );
  }

  private payload(): Partial<Reminder> {
    const raw = this.form.getRawValue();
    // Lo split di una stringa vuota dà [''], e Number('') è 0: senza scartare
    // i pezzi vuoti un campo lasciato in bianco salverebbe il preavviso [0] —
    // «avvisa il giorno stesso» — al posto di nessun preavviso proprio,
    // zittendo quelli generali invece di ereditarli.
    const offsets = raw.alert_offsets
      .split(/[,\s]+/)
      .filter((v) => v.trim() !== '')
      .map((v) => Number(v))
      .filter((v) => Number.isFinite(v) && v >= 0);
    const emails = raw.notify_emails
      .split(/[,;\s]+/)
      .map((v) => v.trim())
      .filter(Boolean);

    return {
      title: raw.title.trim(),
      kind: raw.kind as ReminderKind,
      due_date: raw.due_date,
      start_time: raw.start_time || null,
      recurrence: raw.recurrence as Reminder['recurrence'],
      recurrence_until: raw.recurrence_until || null,
      amount: raw.amount === null || String(raw.amount) === '' ? null : Number(raw.amount),
      owner: raw.owner.trim() || null,
      reference: raw.reference.trim() || null,
      description: raw.description.trim() || null,
      alert_offsets: offsets.length ? offsets : null,
      notify_emails: emails.length ? emails : null,
    };
  }

  /** Come si colloca un avviso rispetto alla data del promemoria.
   *
   * Non si mostra il titolo della notifica: quello è scritto dal punto di
   * vista del giorno in cui partirà («Tra 7 giorni»), e letto oggi accanto a
   * una data del 2027 sembra semplicemente sbagliato. Qui serve la distanza
   * dalla scadenza, che è quello che si è impostato.
   *
   * `offset_days` è positivo per i preavvisi, negativo per i solleciti.
   */
  preavviso(avviso: AppNotification): string {
    const giorni = avviso.offset_days;
    if (giorni > 0) {
      return giorni === 1 ? 'il giorno prima' : `${giorni} giorni prima`;
    }
    if (giorni === 0) {
      return 'il giorno stesso';
    }
    const dopo = Math.abs(giorni);
    return dopo === 1 ? 'il giorno dopo' : `${dopo} giorni dopo`;
  }

  async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    try {
      const existing = this.current();
      // Gli importi per occorrenza valgono solo alla creazione: dopo, ogni
      // occorrenza è un promemoria a sé e si modifica dalla sua scheda.
      const corpo = existing
        ? this.payload()
        : { ...this.payload(), occurrences: this.occurrences() };
      const saved = existing
        ? await firstValueFrom(this.api.updateReminder(existing.id, this.payload()))
        : await firstValueFrom(this.api.createReminder(corpo));
      this.toasts.success(existing ? 'Promemoria aggiornato' : 'Promemoria creato');
      void this.notifications.refresh();
      if (existing) {
        this.current.set(saved);
        this.alerts.set(await firstValueFrom(this.api.reminderNotifications(saved.id)));
      } else {
        void this.router.navigate(['/promemoria', saved.id]);
      }
    } catch (err) {
      this.toasts.error('Salvataggio non riuscito: ' + describeError(err));
    } finally {
      this.saving.set(false);
    }
  }

  async complete(): Promise<void> {
    const reminder = this.current();
    if (!reminder) {
      return;
    }
    const updated = await firstValueFrom(this.api.completeReminder(reminder.id));
    this.current.set(updated);
    this.toasts.success(
      reminder.recurrence === 'none'
        ? 'Promemoria completato'
        : "Promemoria completato: creata l'occorrenza successiva",
    );
  }

  async reopen(): Promise<void> {
    const reminder = this.current();
    if (!reminder) {
      return;
    }
    this.current.set(await firstValueFrom(this.api.reopenReminder(reminder.id)));
    this.alerts.set(await firstValueFrom(this.api.reminderNotifications(reminder.id)));
  }

  async remove(): Promise<void> {
    const reminder = this.current();
    if (!reminder || !confirm(`Eliminare definitivamente «${reminder.title}»?`)) {
      return;
    }
    await firstValueFrom(this.api.deleteReminder(reminder.id));
    this.toasts.show('Promemoria eliminato');
    void this.router.navigate(['/promemoria']);
  }

  /** Disdire l'intera rateizzazione, invece di cancellarne dodici a mano. */
  async removeSeries(): Promise<void> {
    const reminder = this.current();
    const posizione = reminder?.series_position;
    if (!reminder || !posizione) {
      return;
    }
    if (!confirm(`Eliminare tutte le ${posizione[1]} occorrenze di «${reminder.title}»?`)) {
      return;
    }
    await firstValueFrom(this.api.deleteReminder(reminder.id, true));
    this.toasts.show(`Serie eliminata: ${posizione[1]} occorrenze`);
    void this.router.navigate(['/promemoria']);
  }
}
