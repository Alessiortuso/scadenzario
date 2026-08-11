import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { AppNotification, Category, Deadline } from '../../core/models';
import { NotificationStore } from '../../core/notification.store';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-deadline-form',
  imports: [ReactiveFormsModule, RouterLink, DatePipe],
  templateUrl: './deadline-form.html',
  styleUrl: './deadline-form.scss',
})
export class DeadlineFormPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly toasts = inject(ToastService);
  private readonly notifications = inject(NotificationStore);

  /** Popolato dal router per la rotta /scadenze/:id. */
  readonly id = input<string | undefined>();

  readonly categories = signal<Category[]>([]);
  readonly current = signal<Deadline | null>(null);
  readonly alerts = signal<AppNotification[]>([]);
  readonly saving = signal(false);
  readonly loading = signal(false);

  readonly isEdit = computed(() => this.current() !== null);

  readonly form = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.maxLength(255)]],
    due_date: ['', Validators.required],
    category_id: this.fb.control<number | null>(null),
    priority: ['normal'],
    recurrence: ['none'],
    amount: this.fb.control<number | null>(null),
    owner: [''],
    reference: [''],
    description: [''],
    alert_offsets: [''],
    notify_emails: [''],
  });

  async ngOnInit(): Promise<void> {
    this.loading.set(true);
    try {
      this.categories.set(await firstValueFrom(this.api.listCategories()));

      const id = Number(this.id());
      if (Number.isFinite(id) && id > 0) {
        const deadline = await firstValueFrom(this.api.getDeadline(id));
        this.current.set(deadline);
        this.form.patchValue({
          title: deadline.title,
          due_date: deadline.due_date,
          category_id: deadline.category_id,
          priority: deadline.priority,
          recurrence: deadline.recurrence,
          amount: deadline.amount,
          owner: deadline.owner ?? '',
          reference: deadline.reference ?? '',
          description: deadline.description ?? '',
          alert_offsets: (deadline.alert_offsets ?? []).join(', '),
          notify_emails: (deadline.notify_emails ?? []).join(', '),
        });
        this.alerts.set(await firstValueFrom(this.api.deadlineNotifications(id)));
      } else {
        this.form.patchValue({ due_date: new Date().toISOString().slice(0, 10) });
      }
    } catch {
      this.toasts.error('Scadenza non trovata');
      void this.router.navigate(['/scadenze']);
    } finally {
      this.loading.set(false);
    }
  }

  private payload(): Partial<Deadline> {
    const raw = this.form.getRawValue();
    const offsets = raw.alert_offsets
      .split(/[,\s]+/)
      .map((v) => Number(v))
      .filter((v) => Number.isFinite(v) && v >= 0);
    const emails = raw.notify_emails
      .split(/[,;\s]+/)
      .map((v) => v.trim())
      .filter(Boolean);

    return {
      title: raw.title.trim(),
      due_date: raw.due_date,
      category_id: raw.category_id,
      priority: raw.priority as Deadline['priority'],
      recurrence: raw.recurrence as Deadline['recurrence'],
      amount: raw.amount === null || String(raw.amount) === '' ? null : Number(raw.amount),
      owner: raw.owner.trim() || null,
      reference: raw.reference.trim() || null,
      description: raw.description.trim() || null,
      alert_offsets: offsets.length ? offsets : null,
      notify_emails: emails.length ? emails : null,
    };
  }

  async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    try {
      const existing = this.current();
      const saved = existing
        ? await firstValueFrom(this.api.updateDeadline(existing.id, this.payload()))
        : await firstValueFrom(this.api.createDeadline(this.payload()));
      this.toasts.success(existing ? 'Scadenza aggiornata' : 'Scadenza creata');
      void this.notifications.refresh();
      if (existing) {
        this.current.set(saved);
        this.alerts.set(await firstValueFrom(this.api.deadlineNotifications(saved.id)));
      } else {
        void this.router.navigate(['/scadenze', saved.id]);
      }
    } catch (err) {
      this.toasts.error('Salvataggio non riuscito: ' + describe(err));
    } finally {
      this.saving.set(false);
    }
  }

  async complete(): Promise<void> {
    const deadline = this.current();
    if (!deadline) {
      return;
    }
    const updated = await firstValueFrom(this.api.completeDeadline(deadline.id));
    this.current.set(updated);
    this.toasts.success(
      deadline.recurrence === 'none' ? 'Scadenza evasa' : "Scadenza evasa: creata l'occorrenza successiva",
    );
  }

  async reopen(): Promise<void> {
    const deadline = this.current();
    if (!deadline) {
      return;
    }
    this.current.set(await firstValueFrom(this.api.reopenDeadline(deadline.id)));
    this.alerts.set(await firstValueFrom(this.api.deadlineNotifications(deadline.id)));
  }

  async remove(): Promise<void> {
    const deadline = this.current();
    if (!deadline || !confirm(`Eliminare definitivamente «${deadline.title}»?`)) {
      return;
    }
    await firstValueFrom(this.api.deleteDeadline(deadline.id));
    this.toasts.show('Scadenza eliminata');
    void this.router.navigate(['/scadenze']);
  }
}

function describe(err: unknown): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' ? detail : 'errore imprevisto';
}
