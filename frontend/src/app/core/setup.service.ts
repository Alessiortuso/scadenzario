import { Injectable, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { SetupStatus } from './models';

@Injectable({ providedIn: 'root' })
export class SetupService {
  private readonly api = inject(ApiService);

  readonly status = signal<SetupStatus | null>(null);

  async refresh(): Promise<SetupStatus | null> {
    try {
      const status = await firstValueFrom(this.api.setupStatus());
      this.status.set(status);
      return status;
    } catch {
      // Backend non ancora pronto: si riproverà al prossimo giro.
      return null;
    }
  }

  async isConfigured(): Promise<boolean> {
    const known = this.status();
    if (known?.configured) {
      return true;
    }
    return (await this.refresh())?.configured ?? false;
  }
}

/**
 * Finché il database condiviso non è configurato, ogni pagina rimanda alla
 * schermata di primo avvio: senza connessione non c'è nulla da mostrare.
 */
export const setupGuard: CanActivateFn = async () => {
  const setup = inject(SetupService);
  const router = inject(Router);

  if (await setup.isConfigured()) {
    return true;
  }
  return router.createUrlTree(['/configurazione']);
};
