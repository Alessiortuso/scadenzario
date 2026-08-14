import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import {
  CalendarDay,
  KIND_COLORS,
  KIND_LABELS,
  Reminder,
  ReminderKind,
  YearDay,
} from '../../core/models';
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

const MESI_BREVI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

/** Una casella della vista annuale: un giorno del mese, o un buco allineante. */
interface CasellaAnno {
  data: string | null;
  giorno: number;
  conteggi: YearDay | null;
}

interface MeseInMiniatura {
  mese: number;
  nome: string;
  caselle: CasellaAnno[];
}

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
  private readonly destroyRef = inject(DestroyRef);

  readonly giorniSettimana = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];
  readonly kindLabels = KIND_LABELS;
  readonly maxPerGiorno = MAX_PER_GIORNO;

  readonly year = signal(new Date().getFullYear());
  readonly month = signal(new Date().getMonth() + 1);
  readonly days = signal<CalendarDay[]>([]);
  readonly loading = signal(false);

  readonly kind = signal<ReminderKind | ''>('');
  readonly includeDone = signal(true);

  /** Mese o anno: la vista annuale serve a vedere la distribuzione, non i titoli. */
  readonly vista = signal<'mese' | 'anno'>('mese');
  readonly anno = signal<YearDay[]>([]);

  /** Giorno aperto nel pannello laterale; null = nessuno. */
  readonly selected = signal<CalendarDay | null>(null);

  readonly monthLabel = computed(() =>
    this.vista() === 'anno' ? String(this.year()) : `${MESI[this.month() - 1]} ${this.year()}`,
  );

  /**
   * I dodici mesi in miniatura, ognuno con le sue caselle.
   *
   * Le caselle vuote in testa allineano il primo giorno alla sua colonna:
   * senza, ogni mese comincerebbe di lunedì e il colpo d'occhio sulle
   * settimane — che è tutto il senso di questa vista — andrebbe perso.
   */
  readonly mesiDellAnno = computed<MeseInMiniatura[]>(() => {
    const perData = new Map(this.anno().map((g) => [g.date, g]));
    const anno = this.year();

    return MESI_BREVI.map((nome, indice) => {
      const mese = indice + 1;
      const primo = new Date(anno, indice, 1);
      const quanti = new Date(anno, mese, 0).getDate();
      // getDay(): 0 è domenica; qui la settimana comincia di lunedì.
      const vuote = (primo.getDay() + 6) % 7;

      const caselle: CasellaAnno[] = Array.from({ length: vuote }, () => ({
        data: null,
        giorno: 0,
        conteggi: null,
      }));

      for (let giorno = 1; giorno <= quanti; giorno += 1) {
        const data = `${anno}-${String(mese).padStart(2, '0')}-${String(giorno).padStart(2, '0')}`;
        caselle.push({ data, giorno, conteggi: perData.get(data) ?? null });
      }
      return { mese, nome, caselle };
    });
  });

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
    this.ricaricaQuandoTornaInPrimoPiano();
  }

  /** Rilegge il mese ogni volta che si torna a guardare questa pagina.
   *
   * Il calendario è l'unica schermata che si tiene aperta e si guarda a
   * lungo, e da sola non si aggiorna mai: un promemoria eliminato — qui o su
   * un'altra postazione — resta disegnato nella sua casella finché non si
   * cambia pagina. Tornare sulla finestra è il momento in cui uno si aspetta
   * di vedere le cose come stanno adesso.
   */
  private ricaricaQuandoTornaInPrimoPiano(): void {
    const rileggi = () => {
      if (document.visibilityState === 'visible') {
        void this.load();
      }
    };

    // `focus` copre il rientro nella finestra, `visibilitychange` il ritorno
    // sulla scheda: nell'app desktop scatta il primo, nel browser il secondo.
    window.addEventListener('focus', rileggi);
    document.addEventListener('visibilitychange', rileggi);
    this.destroyRef.onDestroy(() => {
      window.removeEventListener('focus', rileggi);
      document.removeEventListener('visibilitychange', rileggi);
    });
  }

  async load(): Promise<void> {
    if (this.vista() === 'anno') {
      await this.loadAnno();
      return;
    }

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

  private async loadAnno(): Promise<void> {
    this.loading.set(true);
    try {
      const anno = await firstValueFrom(
        this.api.calendarYear(this.year(), this.kind() || undefined, this.includeDone()),
      );
      this.anno.set(anno.days);
    } catch {
      this.toasts.error('Caricamento del calendario non riuscito');
    } finally {
      this.loading.set(false);
    }
  }

  async cambiaVista(vista: 'mese' | 'anno'): Promise<void> {
    this.vista.set(vista);
    this.selected.set(null);
    await this.load();
  }

  /** Dalla miniatura al mese vero, sul giorno cliccato. */
  async apriGiorno(casella: CasellaAnno): Promise<void> {
    if (casella.data === null) {
      return;
    }
    const [, mese] = casella.data.split('-').map(Number);
    this.vista.set('mese');
    await this.goTo(this.year(), mese);
    this.selected.set(this.days().find((d) => d.date === casella.data) ?? null);
  }

  /** Dalla miniatura al mese intero, cliccando il nome. */
  async apriMese(mese: number): Promise<void> {
    this.vista.set('mese');
    await this.goTo(this.year(), mese);
  }

  /** Il colore del pallino: il tipo più urgente presente in quel giorno. */
  coloreGiorno(conteggi: YearDay): string {
    if (conteggi.deadline > 0) return KIND_COLORS.deadline;
    if (conteggi.appointment > 0) return KIND_COLORS.appointment;
    return KIND_COLORS.other;
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
    if (this.vista() === 'anno') {
      await this.goTo(this.year() - 1, this.month());
      return;
    }
    const m = this.month() - 1;
    await (m < 1 ? this.goTo(this.year() - 1, 12) : this.goTo(this.year(), m));
  }

  async nextMonth(): Promise<void> {
    if (this.vista() === 'anno') {
      await this.goTo(this.year() + 1, this.month());
      return;
    }
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
