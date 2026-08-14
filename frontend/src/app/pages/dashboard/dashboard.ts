import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { KIND_LABELS, Reminder, ReminderKind, ReminderStats } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { DueBadge } from '../../shared/due-badge';
import { KindIcon } from '../../shared/kind-icon';
import { TimeLabelPipe } from '../../shared/time-label.pipe';

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, DatePipe, CurrencyPipe, DueBadge, KindIcon, TimeLabelPipe],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toasts = inject(ToastService);

  readonly kindLabels = KIND_LABELS;

  readonly stats = signal<ReminderStats | null>(null);
  readonly upcoming = signal<Reminder[]>([]);
  readonly loading = signal(true);

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

  kindLabel(kind: ReminderKind): string {
    return KIND_LABELS[kind];
  }

  async complete(reminder: Reminder): Promise<void> {
    await firstValueFrom(this.api.completeReminder(reminder.id));
    this.toasts.success(`«${reminder.title}» segnato come completato`);
    await this.reload();
  }
}
