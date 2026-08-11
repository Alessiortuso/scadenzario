import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AppNotification,
  AppSettings,
  Category,
  Deadline,
  DeadlinePage,
  DeadlineQuery,
  DeadlineStats,
  ImportMapping,
  ImportPreview,
  ImportResult,
  NotificationCounts,
  PushSubscriptionInfo,
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

  // ------------------------------------------------------------- scadenze
  listDeadlines(query: DeadlineQuery = {}): Observable<DeadlinePage> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined && value !== '' && value !== false) {
        params = params.set(key, String(value));
      }
    }
    return this.http.get<DeadlinePage>(`${BASE}/deadlines`, { params });
  }

  getDeadline(id: number): Observable<Deadline> {
    return this.http.get<Deadline>(`${BASE}/deadlines/${id}`);
  }

  upcoming(days = 30, limit = 50): Observable<Deadline[]> {
    return this.http.get<Deadline[]>(`${BASE}/deadlines/upcoming`, {
      params: new HttpParams().set('days', days).set('limit', limit),
    });
  }

  stats(): Observable<DeadlineStats> {
    return this.http.get<DeadlineStats>(`${BASE}/deadlines/stats`);
  }

  createDeadline(payload: Partial<Deadline>): Observable<Deadline> {
    return this.http.post<Deadline>(`${BASE}/deadlines`, payload);
  }

  updateDeadline(id: number, payload: Partial<Deadline>): Observable<Deadline> {
    return this.http.patch<Deadline>(`${BASE}/deadlines/${id}`, payload);
  }

  completeDeadline(id: number): Observable<Deadline> {
    return this.http.post<Deadline>(`${BASE}/deadlines/${id}/complete`, {});
  }

  reopenDeadline(id: number): Observable<Deadline> {
    return this.http.post<Deadline>(`${BASE}/deadlines/${id}/reopen`, {});
  }

  deleteDeadline(id: number): Observable<void> {
    return this.http.delete<void>(`${BASE}/deadlines/${id}`);
  }

  // ----------------------------------------------------------- categorie
  listCategories(): Observable<Category[]> {
    return this.http.get<Category[]>(`${BASE}/categories`);
  }

  createCategory(payload: Partial<Category>): Observable<Category> {
    return this.http.post<Category>(`${BASE}/categories`, payload);
  }

  updateCategory(id: number, payload: Partial<Category>): Observable<Category> {
    return this.http.patch<Category>(`${BASE}/categories/${id}`, payload);
  }

  deleteCategory(id: number): Observable<void> {
    return this.http.delete<void>(`${BASE}/categories/${id}`);
  }

  // ----------------------------------------------------------- notifiche
  listNotifications(limit = 50, onlyUnread = false): Observable<AppNotification[]> {
    return this.http.get<AppNotification[]>(`${BASE}/notifications`, {
      params: new HttpParams().set('limit', limit).set('only_unread', onlyUnread),
    });
  }

  /** Storico + avvisi ancora programmati per una singola scadenza. */
  deadlineNotifications(deadlineId: number): Observable<AppNotification[]> {
    return this.http.get<AppNotification[]>(`${BASE}/notifications`, {
      params: new HttpParams()
        .set('deadline_id', deadlineId)
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
