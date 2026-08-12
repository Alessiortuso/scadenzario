import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { Category, Deadline, DeadlineQuery, DeadlineStatus } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { DueBadge } from '../../shared/due-badge';
import { PriorityBadge } from '../../shared/priority-badge';

type RangeKey = '' | 'overdue' | 'today' | '7' | '30' | '90';

@Component({
  selector: 'app-deadline-list',
  imports: [RouterLink, FormsModule, DatePipe, CurrencyPipe, DueBadge, PriorityBadge],
  templateUrl: './deadline-list.html',
  styleUrl: './deadline-list.scss',
})
export class DeadlineListPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly toasts = inject(ToastService);

  readonly items = signal<Deadline[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly loading = signal(false);
  readonly categories = signal<Category[]>([]);

  readonly q = signal('');
  readonly status = signal<DeadlineStatus | ''>('open');
  readonly categoryId = signal<number | null>(null);
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

    this.categories.set(await firstValueFrom(this.api.listCategories()));
    await this.search();
  }

  private buildQuery(): DeadlineQuery {
    const query: DeadlineQuery = {
      q: this.q().trim() || undefined,
      status: this.status() || undefined,
      category_id: this.categoryId() ?? undefined,
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
      const result = await firstValueFrom(this.api.listDeadlines(this.buildQuery()));
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
    this.categoryId.set(null);
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

  async complete(deadline: Deadline): Promise<void> {
    await firstValueFrom(this.api.completeDeadline(deadline.id));
    this.toasts.success(
      deadline.recurrence === 'none'
        ? `«${deadline.title}» evasa`
        : `«${deadline.title}» evasa: creata l'occorrenza successiva`,
    );
    await this.search();
  }

  async reopen(deadline: Deadline): Promise<void> {
    await firstValueFrom(this.api.reopenDeadline(deadline.id));
    this.toasts.show(`«${deadline.title}» riaperta`);
    await this.search();
  }

  async remove(deadline: Deadline): Promise<void> {
    if (!confirm(`Eliminare definitivamente «${deadline.title}»?`)) {
      return;
    }
    await firstValueFrom(this.api.deleteDeadline(deadline.id));
    this.toasts.show('Scadenza eliminata');
    await this.search();
  }
}
