import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { Category, PushSubscriptionInfo, SettingsRead } from '../../core/models';
import { NotificationStore } from '../../core/notification.store';
import { PushService } from '../../core/push.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-settings',
  imports: [FormsModule, DatePipe, RouterLink],
  templateUrl: './settings-page.html',
  styleUrl: './settings-page.scss',
})
export class SettingsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toasts = inject(ToastService);
  private readonly notifications = inject(NotificationStore);
  readonly push = inject(PushService);

  readonly settings = signal<SettingsRead | null>(null);
  readonly offsetsText = signal('');
  readonly emailsText = signal('');
  readonly saving = signal(false);

  readonly devices = signal<PushSubscriptionInfo[]>([]);
  readonly categories = signal<Category[]>([]);
  readonly newCategory = signal({ name: '', color: '#6366f1', offsets: '' });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  async reload(): Promise<void> {
    const [settings, devices, categories] = await Promise.all([
      firstValueFrom(this.api.getSettings()),
      firstValueFrom(this.api.pushSubscriptions()),
      firstValueFrom(this.api.listCategories()),
    ]);
    this.settings.set(settings);
    this.offsetsText.set(settings.default_alert_offsets.join(', '));
    this.emailsText.set(settings.notify_emails.join(', '));
    this.devices.set(devices);
    this.categories.set(categories);
  }

  patch<K extends keyof SettingsRead>(key: K, value: SettingsRead[K]): void {
    this.settings.update((current) => (current ? { ...current, [key]: value } : current));
  }

  async save(): Promise<void> {
    const current = this.settings();
    if (!current) {
      return;
    }
    this.saving.set(true);
    try {
      const payload = {
        ...current,
        default_alert_offsets: parseNumbers(this.offsetsText()),
        notify_emails: parseList(this.emailsText()),
      };
      const saved = await firstValueFrom(this.api.saveSettings(payload));
      this.settings.set(saved);
      this.toasts.success('Impostazioni salvate: gli avvisi non ancora inviati sono stati riprogrammati');
    } catch {
      this.toasts.error('Salvataggio non riuscito');
    } finally {
      this.saving.set(false);
    }
  }

  async togglePush(): Promise<void> {
    if (this.push.state() === 'on') {
      await this.push.disable();
    } else {
      await this.push.enable();
    }
    this.devices.set(await firstValueFrom(this.api.pushSubscriptions()));
  }

  async testPush(): Promise<void> {
    try {
      this.toasts.success(await this.push.sendTest());
    } catch (err) {
      this.toasts.error('Invio di prova non riuscito: ' + describe(err));
    }
  }

  async removeDevice(device: PushSubscriptionInfo): Promise<void> {
    await firstValueFrom(this.api.pushUnsubscribe(device.endpoint));
    this.devices.set(await firstValueFrom(this.api.pushSubscriptions()));
    this.toasts.show('Dispositivo rimosso');
  }

  async runNow(): Promise<void> {
    const result = await firstValueFrom(this.api.runScheduler());
    await this.notifications.refresh();
    this.toasts.success(
      `Ciclo eseguito: ${result.generated} avvisi ricalcolati, ${result.sent} inviati, ${result.failed} falliti`,
    );
  }

  async addCategory(): Promise<void> {
    const value = this.newCategory();
    if (!value.name.trim()) {
      return;
    }
    try {
      await firstValueFrom(
        this.api.createCategory({
          name: value.name.trim(),
          color: value.color,
          alert_offsets: parseNumbers(value.offsets).length ? parseNumbers(value.offsets) : null,
        }),
      );
      this.newCategory.set({ name: '', color: '#6366f1', offsets: '' });
      this.categories.set(await firstValueFrom(this.api.listCategories()));
      this.toasts.success('Categoria creata');
    } catch (err) {
      this.toasts.error('Creazione non riuscita: ' + describe(err));
    }
  }

  async removeCategory(category: Category): Promise<void> {
    if (!confirm(`Eliminare la categoria «${category.name}»? Le scadenze resteranno senza categoria.`)) {
      return;
    }
    await firstValueFrom(this.api.deleteCategory(category.id));
    this.categories.set(await firstValueFrom(this.api.listCategories()));
  }

  pushLabel(): string {
    switch (this.push.state()) {
      case 'native':
        return 'Notifiche di Windows attive';
      case 'on':
        return 'Attive su questo dispositivo';
      case 'denied':
        return 'Bloccate dal browser';
      case 'unsupported':
        return 'Non supportate da questo browser';
      case 'not-configured':
        return 'Non configurate sul server';
      case 'loading':
        return 'Verifica in corso…';
      default:
        return 'Non attive su questo dispositivo';
    }
  }
}

function parseNumbers(text: string): number[] {
  return text
    .split(/[,;\s]+/)
    .map((v) => Number(v))
    .filter((v) => Number.isFinite(v) && v >= 0);
}

function parseList(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map((v) => v.trim())
    .filter(Boolean);
}

function describe(err: unknown): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' ? detail : 'errore imprevisto';
}
