import { DatePipe } from '@angular/common';
import { Component, HostListener, ElementRef, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { NotificationStore } from '../core/notification.store';
import { AppNotification } from '../core/models';

@Component({
  selector: 'app-notification-bell',
  imports: [DatePipe],
  templateUrl: './notification-bell.html',
  styleUrl: './notification-bell.scss',
})
export class NotificationBell {
  private readonly router = inject(Router);
  private readonly host = inject(ElementRef<HTMLElement>);
  readonly store = inject(NotificationStore);

  readonly open = signal(false);

  toggle(): void {
    const next = !this.open();
    this.open.set(next);
    if (next) {
      void this.store.refresh();
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) {
      this.open.set(false);
    }
  }

  async openNotification(notification: AppNotification): Promise<void> {
    if (!notification.read_at) {
      await this.store.markRead(notification.id);
    }
    this.open.set(false);
    void this.router.navigate(['/promemoria', notification.reminder_id]);
  }

  severityTone(severity: string): string {
    switch (severity) {
      case 'danger':
        return 'danger';
      case 'critical':
        return 'danger';
      case 'warning':
        return 'warning';
      default:
        return 'info';
    }
  }
}
