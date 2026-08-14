import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AttentionService } from '../../core/attention.service';
import { KIND_LABELS, Reminder, ReminderKind, ReminderQuery, ReminderStatus } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { DueBadge } from '../../shared/due-badge';
import { KindIcon } from '../../shared/kind-icon';
import { TimeLabelPipe } from '../../shared/time-label.pipe';

type RangeKey = '' | 'overdue' | 'today' | '7' | '30' | '90';

@Component({
  selector: 'app-reminder-list',
  imports: [RouterLink, FormsModule, DatePipe, CurrencyPipe, DueBadge, KindIcon, TimeLabelPipe],
  templateUrl: './reminder-list.html',
  styleUrl: './reminder-list.scss',
})
export class ReminderListPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly toasts = inject(ToastService);
  private readonly attention = inject(AttentionService);

  readonly kindLabels = KIND_LABELS;

  readonly items = signal<Reminder[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly loading = signal(false);

  readonly q = signal('');
  readonly status = signal<ReminderStatus | ''>('open');
  readonly kind = signal<ReminderKind | ''>('');
  readonly range = signal<RangeKey>('');
  readonly sort = signal('due_date');

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize())));

  async ngOnInit(): Promise<void> {
    const params = this.route.snapshot.queryParamMap;
    if (params.get('overdue') === '1') {
      this.range.set('overdue');
    }
    const range = params.get('range') as RangeKey | null;
    if (range) {
      this.range.set(range);
    }
    const kind = params.get('kind') as ReminderKind | null;
    if (kind) {
      this.kind.set(kind);
    }

    await this.search();
    // Aprire l'elenco vuol dire aver preso atto degli avvisi imminenti: la
    // segnalazione sulla barra delle applicazioni si spegne.
    void this.attention.segnalaGuardato();
  }

  private buildQuery(): ReminderQuery {
    const query: ReminderQuery = {
      q: this.q().trim() || undefined,
      status: this.status() || undefined,
      kind: this.kind() || undefined,
      page: this.page(),
      page_size: this.pageSize(),
      sort: this.sort(),
    };

    const today = new Date();
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    switch (this.range()) {
      case 'overdue':
        query.overdue_only = true;
        query.status = 'open';
        break;
      case 'today':
        query.due_from = iso(today);
        query.due_to = iso(today);
        break;
      case '7':
      case '30':
      case '90': {
        const to = new Date(today);
        to.setDate(to.getDate() + Number(this.range()));
        query.due_from = iso(today);
        query.due_to = iso(to);
        break;
      }
    }
    return query;
  }

  async search(resetPage = false): Promise<void> {
    if (resetPage) {
      this.page.set(1);
    }
    this.loading.set(true);
    try {
      const result = await firstValueFrom(this.api.listReminders(this.buildQuery()));
      this.items.set(result.items);
      this.total.set(result.total);
    } catch {
      this.toasts.error('Caricamento non riuscito');
    } finally {
      this.loading.set(false);
    }
  }

  resetFilters(): void {
    this.q.set('');
    this.status.set('open');
    this.kind.set('');
    this.range.set('');
    void this.search(true);
  }

  async goToPage(page: number): Promise<void> {
    if (page < 1 || page > this.totalPages()) {
      return;
    }
    this.page.set(page);
    await this.search();
  }

  sortBy(column: string): void {
    this.sort.update((current) => (current === column ? `-${column}` : column));
    void this.search(true);
  }

  async complete(reminder: Reminder): Promise<void> {
    await firstValueFrom(this.api.completeReminder(reminder.id));
    this.toasts.success(
      reminder.recurrence === 'none'
        ? `«${reminder.title}» completato`
        : `«${reminder.title}» completato: creata l'occorrenza successiva`,
    );
    await this.search();
  }

  async reopen(reminder: Reminder): Promise<void> {
    await firstValueFrom(this.api.reopenReminder(reminder.id));
    this.toasts.show(`«${reminder.title}» riaperto`);
    await this.search();
  }

  async remove(reminder: Reminder): Promise<void> {
    if (!confirm(`Eliminare definitivamente «${reminder.title}»?`)) {
      return;
    }
    await firstValueFrom(this.api.deleteReminder(reminder.id));
    this.toasts.show('Promemoria eliminato');
    await this.search();
  }
}
