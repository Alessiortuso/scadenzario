import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { AppNotification } from './models';

const POLL_MS = 60_000;

/** Stato condiviso del centro notifiche, aggiornato anche in polling. */
@Injectable({ providedIn: 'root' })
export class NotificationStore {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);

  readonly items = signal<AppNotification[]>([]);
  readonly unread = signal(0);
  readonly loading = signal(false);

  private timer: ReturnType<typeof setInterval> | null = null;

  startPolling(): void {
    if (this.timer !== null) {
      return;
    }
    void this.refresh();
    this.timer = setInterval(() => void this.refreshCounts(), POLL_MS);
    this.destroyRef.onDestroy(() => this.stopPolling());

    // Quando il service worker consegna un push, aggiorniamo subito il badge.
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', () => void this.refresh());
    }
  }

  stopPolling(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    try {
      const [items, counts] = await Promise.all([
        firstValueFrom(this.api.listNotifications(50)),
        firstValueFrom(this.api.notificationCounts()),
      ]);
      this.items.set(items);
      this.unread.set(counts.unread);
    } finally {
      this.loading.set(false);
    }
  }

  async refreshCounts(): Promise<void> {
    const counts = await firstValueFrom(this.api.notificationCounts());
    if (counts.unread !== this.unread()) {
      this.unread.set(counts.unread);
      await this.refresh();
    }
  }

  async markRead(id: number): Promise<void> {
    await firstValueFrom(this.api.markRead(id));
    this.items.update((list) =>
      list.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)),
    );
    this.unread.update((n) => Math.max(0, n - 1));
  }

  async markAllRead(): Promise<void> {
    await firstValueFrom(this.api.markAllRead());
    const now = new Date().toISOString();
    this.items.update((list) => list.map((n) => ({ ...n, read_at: n.read_at ?? now })));
    this.unread.set(0);
  }
}
