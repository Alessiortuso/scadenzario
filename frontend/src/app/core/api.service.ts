import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AppNotification,
  AppSettings,
  CalendarMonth,
  CalendarQuery,
  ImportMapping,
  ImportPreview,
  ImportResult,
  NotificationCounts,
  PushSubscriptionInfo,
  Reminder,
  ReminderPage,
  ReminderQuery,
  ReminderStats,
  SettingsRead,
  SetupPayload,
  SetupStatus,
  ConnectionTestResult,
} from './models';

const BASE = '/api';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  // -------------------------------------------------------- configurazione
  setupStatus(): Observable<SetupStatus> {
    return this.http.get<SetupStatus>(`${BASE}/setup/status`);
  }

  setupTest(databaseUrl: string): Observable<ConnectionTestResult> {
    return this.http.post<ConnectionTestResult>(`${BASE}/setup/test`, { database_url: databaseUrl });
  }

  setupSave(payload: SetupPayload): Observable<SetupStatus> {
    return this.http.post<SetupStatus>(`${BASE}/setup`, payload);
  }

  // ----------------------------------------------------------- promemoria
  /** I campi valorizzati diventano parametri; vuoti, nulli e `false` si omettono. */
  private toParams(query: object): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined && value !== '' && value !== false) {
        params = params.set(key, String(value));
      }
    }
    return params;
  }

  listReminders(query: ReminderQuery = {}): Observable<ReminderPage> {
    return this.http.get<ReminderPage>(`${BASE}/reminders`, { params: this.toParams(query) });
  }

  getReminder(id: number): Observable<Reminder> {
    return this.http.get<Reminder>(`${BASE}/reminders/${id}`);
  }

  /** Il mese pronto da disegnare: settimane intere, giorno per giorno. */
  calendar(query: CalendarQuery): Observable<CalendarMonth> {
    // `include_done` è l'unico flag che va mandato anche quando è false:
    // ometterlo significherebbe "mostrali", cioè il contrario di quel che vuole
    // chi ha tolto la spunta.
    const params = this.toParams({ ...query, include_done: undefined }).set(
      'include_done',
      query.include_done ?? true,
    );
    return this.http.get<CalendarMonth>(`${BASE}/reminders/calendar`, { params });
  }

  upcoming(days = 30, limit = 50): Observable<Reminder[]> {
    return this.http.get<Reminder[]>(`${BASE}/reminders/upcoming`, {
      params: new HttpParams().set('days', days).set('limit', limit),
    });
  }

  stats(): Observable<ReminderStats> {
    return this.http.get<ReminderStats>(`${BASE}/reminders/stats`);
  }

  createReminder(payload: Partial<Reminder>): Observable<Reminder> {
    return this.http.post<Reminder>(`${BASE}/reminders`, payload);
  }

  updateReminder(id: number, payload: Partial<Reminder>): Observable<Reminder> {
    return this.http.patch<Reminder>(`${BASE}/reminders/${id}`, payload);
  }

  completeReminder(id: number): Observable<Reminder> {
    return this.http.post<Reminder>(`${BASE}/reminders/${id}/complete`, {});
  }

  reopenReminder(id: number): Observable<Reminder> {
    return this.http.post<Reminder>(`${BASE}/reminders/${id}/reopen`, {});
  }

  deleteReminder(id: number): Observable<void> {
    return this.http.delete<void>(`${BASE}/reminders/${id}`);
  }

  // ----------------------------------------------------------- notifiche
  listNotifications(limit = 50, onlyUnread = false): Observable<AppNotification[]> {
    return this.http.get<AppNotification[]>(`${BASE}/notifications`, {
      params: new HttpParams().set('limit', limit).set('only_unread', onlyUnread),
    });
  }

  /** Storico + avvisi ancora programmati per un singolo promemoria. */
  reminderNotifications(reminderId: number): Observable<AppNotification[]> {
    return this.http.get<AppNotification[]>(`${BASE}/notifications`, {
      params: new HttpParams()
        .set('reminder_id', reminderId)
        .set('include_pending', true)
        .set('limit', 100),
    });
  }

  notificationCounts(): Observable<NotificationCounts> {
    return this.http.get<NotificationCounts>(`${BASE}/notifications/counts`);
  }

  markRead(id: number): Observable<AppNotification> {
    return this.http.post<AppNotification>(`${BASE}/notifications/${id}/read`, {});
  }

  markAllRead(): Observable<NotificationCounts> {
    return this.http.post<NotificationCounts>(`${BASE}/notifications/read-all`, {});
  }

  // --------------------------------------------------------------- push
  pushPublicKey(): Observable<{ public_key: string; enabled: boolean }> {
    return this.http.get<{ public_key: string; enabled: boolean }>(`${BASE}/push/public-key`);
  }

  pushSubscriptions(): Observable<PushSubscriptionInfo[]> {
    return this.http.get<PushSubscriptionInfo[]>(`${BASE}/push/subscriptions`);
  }

  pushSubscribe(payload: unknown): Observable<PushSubscriptionInfo> {
    return this.http.post<PushSubscriptionInfo>(`${BASE}/push/subscribe`, payload);
  }

  pushUnsubscribe(endpoint: string): Observable<void> {
    return this.http.post<void>(`${BASE}/push/unsubscribe`, { endpoint });
  }

  pushTest(): Observable<{ sent: number; failed: number; details: string[] }> {
    return this.http.post<{ sent: number; failed: number; details: string[] }>(`${BASE}/push/test`, {});
  }

  // ------------------------------------------------------------- import
  importPreview(file: File, mapping?: ImportMapping): Observable<ImportPreview> {
    const form = new FormData();
    form.append('file', file);
    if (mapping) {
      form.append('mapping', JSON.stringify(mapping));
    }
    return this.http.post<ImportPreview>(`${BASE}/import/preview`, form);
  }

  importApply(file: File, mapping: ImportMapping): Observable<ImportResult> {
    const form = new FormData();
    form.append('file', file);
    form.append('mapping', JSON.stringify(mapping));
    return this.http.post<ImportResult>(`${BASE}/import/apply`, form);
  }

  // ------------------------------------------------------- impostazioni
  getSettings(): Observable<SettingsRead> {
    return this.http.get<SettingsRead>(`${BASE}/settings`);
  }

  saveSettings(payload: AppSettings): Observable<SettingsRead> {
    return this.http.put<SettingsRead>(`${BASE}/settings`, payload);
  }

  runScheduler(): Observable<{ processed: number; sent: number; failed: number; generated: number }> {
    return this.http.post<{ processed: number; sent: number; failed: number; generated: number }>(
      `${BASE}/scheduler/run`,
      {},
    );
  }
}
