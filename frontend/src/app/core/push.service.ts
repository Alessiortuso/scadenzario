import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';

export type PushState = 'unsupported' | 'not-configured' | 'denied' | 'off' | 'on' | 'loading' | 'native';

/**
 * Gestione delle notifiche desktop (Web Push).
 *
 * Il service worker resta registrato nel browser: gli avvisi arrivano anche a
 * scheda chiusa, finché il browser è in esecuzione (anche solo in background).
 */
@Injectable({ providedIn: 'root' })
export class PushService {
  private readonly api = inject(ApiService);

  readonly state = signal<PushState>('loading');
  readonly error = signal<string | null>(null);

  private publicKey: string | null = null;

  get supported(): boolean {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  }

  async init(): Promise<void> {
    // Nell'app desktop le notifiche le mostra Electron con le API native di
    // Windows: il Web Push non serve e non va proposto all'utente.
    if ((window as unknown as { scadenzario?: { isDesktop?: boolean } }).scadenzario?.isDesktop) {
      this.state.set('native');
      return;
    }
    if (!this.supported) {
      this.state.set('unsupported');
      return;
    }
    try {
      const { public_key, enabled } = await firstValueFrom(this.api.pushPublicKey());
      if (!enabled) {
        this.state.set('not-configured');
        return;
      }
      this.publicKey = public_key;
      await navigator.serviceWorker.register('/sw.js');
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (Notification.permission === 'denied') {
        this.state.set('denied');
      } else {
        this.state.set(subscription ? 'on' : 'off');
      }
    } catch (err) {
      this.error.set(String(err));
      this.state.set('off');
    }
  }

  async enable(): Promise<boolean> {
    this.error.set(null);
    if (!this.supported || !this.publicKey) {
      return false;
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      this.state.set(permission === 'denied' ? 'denied' : 'off');
      return false;
    }

    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription =
        (await registration.pushManager.getSubscription()) ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(this.publicKey),
        }));

      const json = subscription.toJSON() as { endpoint?: string; keys?: Record<string, string> };
      await firstValueFrom(
        this.api.pushSubscribe({
          endpoint: json.endpoint,
          keys: { p256dh: json.keys?.['p256dh'], auth: json.keys?.['auth'] },
          label: navigator.userAgent.slice(0, 180),
        }),
      );
      this.state.set('on');
      return true;
    } catch (err) {
      this.error.set(String(err));
      return false;
    }
  }

  async disable(): Promise<void> {
    if (!this.supported) {
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await firstValueFrom(this.api.pushUnsubscribe(subscription.endpoint));
      await subscription.unsubscribe();
    }
    this.state.set('off');
  }

  async sendTest(): Promise<string> {
    const result = await firstValueFrom(this.api.pushTest());
    return `Inviate ${result.sent}, fallite ${result.failed}`;
  }
}

/** La chiave VAPID viaggia in base64url e va convertita in Uint8Array. */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}
