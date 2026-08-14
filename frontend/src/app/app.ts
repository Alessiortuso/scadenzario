import { Component, OnInit, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { NotificationStore } from './core/notification.store';
import { PushService } from './core/push.service';
import { ToastService } from './core/toast.service';
import { NotificationBell } from './shared/notification-bell';

/** API esposta dal preload di Electron quando si gira come app desktop. */
interface DesktopBridge {
  isDesktop: boolean;
  onNavigate: (callback: (route: string) => void) => void;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NotificationBell],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private readonly router = inject(Router);
  readonly store = inject(NotificationStore);
  readonly push = inject(PushService);
  readonly toasts = inject(ToastService);

  readonly menuOpen = signal(false);
  /** Sulla schermata di configurazione il menu porterebbe a pagine bloccate. */
  readonly bare = signal(false);

  ngOnInit(): void {
    this.bare.set(this.router.url.startsWith('/configurazione'));
    this.router.events.subscribe((event) => {
      if (event instanceof NavigationEnd) {
        this.bare.set(event.urlAfterRedirects.startsWith('/configurazione'));
      }
    });

    this.store.startPolling();
    void this.push.init();

    // Click su una notifica nativa di Windows (applicazione desktop Electron).
    const desktop = (window as unknown as { promemoria?: DesktopBridge }).promemoria;
    if (desktop?.onNavigate) {
      desktop.onNavigate((route) => void this.router.navigateByUrl(route));
    }

    // Click su una notifica Web Push (quando si usa dal browser).
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', (event: MessageEvent) => {
        if (event.data?.type === 'navigate' && typeof event.data.url === 'string') {
          void this.router.navigateByUrl(event.data.url);
        }
      });
    }
  }

  async togglePush(): Promise<void> {
    if (this.push.state() === 'on') {
      await this.push.disable();
      this.toasts.show('Notifiche desktop disattivate su questo dispositivo');
      return;
    }
    const ok = await this.push.enable();
    if (ok) {
      this.toasts.success('Notifiche desktop attive su questo dispositivo');
    } else if (this.push.state() === 'denied') {
      this.toasts.error('Permesso negato dal browser: riabilitalo dalle impostazioni del sito');
    } else {
      this.toasts.error('Attivazione non riuscita' + (this.push.error() ? `: ${this.push.error()}` : ''));
    }
  }
}
