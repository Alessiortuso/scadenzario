import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { Deadline, DeadlineStats } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { DueBadge } from '../../shared/due-badge';

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, DatePipe, CurrencyPipe, DueBadge],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toasts = inject(ToastService);

  readonly stats = signal<DeadlineStats | null>(null);
  readonly upcoming = signal<Deadline[]>([]);
  readonly loading = signal(true);

  readonly maxCategoryCount = computed(() =>
    Math.max(1, ...(this.stats()?.by_category ?? []).map((c) => c.count)),
  );

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  async reload(): Promise<void> {
    this.loading.set(true);
    try {
      const [stats, upcoming] = await Promise.all([
        firstValueFrom(this.api.stats()),
        firstValueFrom(this.api.upcoming(60, 12)),
      ]);
      this.stats.set(stats);
      this.upcoming.set(upcoming);
    } catch {
      this.toasts.error('Impossibile caricare i dati: il backend è avviato?');
    } finally {
      this.loading.set(false);
    }
  }

  async complete(deadline: Deadline): Promise<void> {
    await firstValueFrom(this.api.completeDeadline(deadline.id));
    this.toasts.success(`«${deadline.title}» segnata come evasa`);
    await this.reload();
  }
}
