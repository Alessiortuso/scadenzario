import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { ConnectionTestResult, SetupStatus } from '../../core/models';
import { SetupService } from '../../core/setup.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-setup',
  imports: [FormsModule],
  templateUrl: './setup-page.html',
  styleUrl: './setup-page.scss',
})
export class SetupPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly toasts = inject(ToastService);
  private readonly setup = inject(SetupService);

  readonly status = signal<SetupStatus | null>(null);
  readonly databaseUrl = signal('');
  readonly deviceName = signal('');
  readonly emailSender = signal(false);
  readonly testing = signal(false);
  readonly saving = signal(false);
  readonly testResult = signal<ConnectionTestResult | null>(null);

  readonly canSubmit = computed(() => this.databaseUrl().trim().length > 20 && !this.saving());

  async ngOnInit(): Promise<void> {
    const status = await this.setup.refresh();
    this.status.set(status);
    if (status) {
      this.deviceName.set(status.device_name);
      this.emailSender.set(status.email_sender_device);
    }
  }

  async test(): Promise<void> {
    this.testing.set(true);
    this.testResult.set(null);
    try {
      this.testResult.set(await firstValueFrom(this.api.setupTest(this.databaseUrl().trim())));
    } catch {
      this.testResult.set({ ok: false, detail: 'Il servizio locale non risponde' });
    } finally {
      this.testing.set(false);
    }
  }

  async save(): Promise<void> {
    this.saving.set(true);
    try {
      const status = await firstValueFrom(
        this.api.setupSave({
          database_url: this.databaseUrl().trim(),
          device_name: this.deviceName().trim() || null,
          email_sender_device: this.emailSender(),
        }),
      );
      this.status.set(status);
      await this.setup.refresh();
      this.toasts.success('Collegamento configurato su questa postazione');
      void this.router.navigate(['/dashboard']);
    } catch (err) {
      const detail = (err as { error?: { detail?: string } })?.error?.detail;
      this.toasts.error(detail || 'Configurazione non riuscita');
    } finally {
      this.saving.set(false);
    }
  }

  skip(): void {
    void this.router.navigate(['/dashboard']);
  }
}
