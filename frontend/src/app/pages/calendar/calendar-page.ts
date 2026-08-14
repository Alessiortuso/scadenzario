import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { CalendarDay, KIND_COLORS, KIND_LABELS, Reminder, ReminderKind } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { KindIcon } from '../../shared/kind-icon';
import { TimeLabelPipe } from '../../shared/time-label.pipe';

const MESI = [
  'Gennaio',
  'Febbraio',
  'Marzo',
  'Aprile',
  'Maggio',
  'Giugno',
  'Luglio',
  'Agosto',
  'Settembre',
  'Ottobre',
  'Novembre',
  'Dicembre',
];

/** Quanti promemoria stanno in una cella prima di riassumere il resto. */
const MAX_PER_GIORNO = 3;

@Component({
  selector: 'app-calendar',
  imports: [RouterLink, FormsModule, DatePipe, KindIcon, TimeLabelPipe],
  templateUrl: './calendar-page.html',
  styleUrl: './calendar-page.scss',
})
export class CalendarPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly toasts = inject(ToastService);

  readonly giorniSettimana = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];
  readonly kindLabels = KIND_LABELS;
  readonly maxPerGiorno = MAX_PER_GIORNO;

  readonly year = signal(new Date().getFullYear());
  readonly month = signal(new Date().getMonth() + 1);
  readonly days = signal<CalendarDay[]>([]);
  readonly loading = signal(false);

  readonly kind = signal<ReminderKind | ''>('');
  readonly includeDone = signal(true);

  /** Giorno aperto nel pannello laterale; null = nessuno. */
  readonly selected = signal<CalendarDay | null>(null);

  readonly monthLabel = computed(() => `${MESI[this.month() - 1]} ${this.year()}`);

  /** Le celle divise in righe da sette: la griglia si legge per settimane. */
  readonly weeks = computed(() => {
    const out: CalendarDay[][] = [];
    const all = this.days();
    for (let i = 0; i < all.length; i += 7) {
      out.push(all.slice(i, i + 7));
    }
    return out;
  });

  readonly todayIso = new Date().toLocaleDateString('sv');

  async ngOnInit(): Promise<void> {
    const params = this.route.snapshot.queryParamMap;
    const y = Number(params.get('anno'));
    const m = Number(params.get('mese'));
    if (Number.isInteger(y) && y > 1970 && Number.isInteger(m) && m >= 1 && m <= 12) {
      this.year.set(y);
      this.month.set(m);
    }

    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const mese = await firstValueFrom(
        this.api.calendar({
          year: this.year(),
          month: this.month(),
          kind: this.kind() || undefined,
          include_done: this.includeDone(),
        }),
      );
      this.days.set(mese.days);

      // Il giorno aperto va riletto dai dati nuovi, altrimenti il pannello
      // resterebbe fermo su una fotografia vecchia dopo un filtro o un salvataggio.
      const aperto = this.selected();
      if (aperto) {
        this.selected.set(mese.days.find((d) => d.date === aperto.date) ?? null);
      }
    } catch {
      this.toasts.error('Caricamento del calendario non riuscito');
    } finally {
      this.loading.set(false);
    }
  }

  private async goTo(year: number, month: number): Promise<void> {
    this.year.set(year);
    this.month.set(month);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { anno: year, mese: month },
      replaceUrl: true,
    });
    await this.load();
  }

  async previousMonth(): Promise<void> {
    const m = this.month() - 1;
    await (m < 1 ? this.goTo(this.year() - 1, 12) : this.goTo(this.year(), m));
  }

  async nextMonth(): Promise<void> {
    const m = this.month() + 1;
    await (m > 12 ? this.goTo(this.year() + 1, 1) : this.goTo(this.year(), m));
  }

  async goToday(): Promise<void> {
    const now = new Date();
    await this.goTo(now.getFullYear(), now.getMonth() + 1);
    this.selected.set(this.days().find((d) => d.date === this.todayIso) ?? null);
  }

  isToday(day: CalendarDay): boolean {
    return day.date === this.todayIso;
  }

  dayNumber(day: CalendarDay): number {
    return Number(day.date.slice(8, 10));
  }

  /** Il colore con cui il tipo si riconosce a colpo d'occhio nella griglia. */
  colorOf(reminder: Reminder): string {
    return KIND_COLORS[reminder.kind];
  }

  select(day: CalendarDay): void {
    this.selected.set(this.selected()?.date === day.date ? null : day);
  }

  open(reminder: Reminder, event: Event): void {
    // Senza questo il click aprirebbe anche il pannello del giorno sotto.
    event.stopPropagation();
    void this.router.navigate(['/promemoria', reminder.id]);
  }

  /** Nuovo promemoria già datato al giorno scelto. */
  newOn(day: CalendarDay, event?: Event): void {
    event?.stopPropagation();
    void this.router.navigate(['/promemoria/nuovo'], { queryParams: { data: day.date } });
  }

  async complete(reminder: Reminder, event: Event): Promise<void> {
    event.stopPropagation();
    await firstValueFrom(this.api.completeReminder(reminder.id));
    this.toasts.success(`«${reminder.title}» completato`);
    await this.load();
  }
}
