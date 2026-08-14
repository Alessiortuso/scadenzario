export type ReminderStatus = 'open' | 'done' | 'cancelled';
export type ReminderKind = 'deadline' | 'appointment' | 'other';
export type Recurrence = 'none' | 'monthly' | 'quarterly' | 'semiannual' | 'yearly';
export type NotificationStatus = 'pending' | 'sent' | 'failed' | 'cancelled';

/** Etichette dei tipi, in un posto solo. */
export const KIND_LABELS: Record<ReminderKind, string> = {
  deadline: 'Scadenza',
  appointment: 'Appuntamento',
  other: 'Altro',
};

/** Il colore con cui un tipo si riconosce nel calendario.
 *
 * Serve solo a distinguere i pallini a colpo d'occhio, non a gridare: il rosso
 * sta alle scadenze perché sono le uniche che possono farti perdere qualcosa.
 */
export const KIND_COLORS: Record<ReminderKind, string> = {
  deadline: '#ef4444',
  appointment: '#3b82f6',
  other: '#94a3b8',
};

export const KIND_ORDER: ReminderKind[] = ['deadline', 'appointment', 'other'];

export interface Reminder {
  id: number;
  title: string;
  description: string | null;
  due_date: string;
  /** "HH:MM:SS", oppure null per un impegno di giornata. */
  start_time: string | null;
  kind: ReminderKind;
  status: ReminderStatus;
  recurrence: Recurrence;
  /** Fino a quando si ripete. Vuoto = ricorrenza aperta, senza fine. */
  recurrence_until: string | null;
  /** Lega fra loro le occorrenze nate insieme. */
  series_id: string | null;
  /** Posizione nella serie, es. [3, 12]. Solo leggendo il singolo promemoria. */
  series_position: [number, number] | null;
  amount: number | null;
  owner: string | null;
  reference: string | null;
  alert_offsets: number[] | null;
  notify_emails: string[] | null;
  source: string;
  external_id: string | null;
  extra: Record<string, unknown> | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  days_left: number;
  is_overdue: boolean;
}

export interface Occurrence {
  due_date: string;
  amount: number | null;
}

export interface YearDay {
  date: string;
  deadline: number;
  appointment: number;
  other: number;
  total: number;
}

export interface CalendarYear {
  year: number;
  days: YearDay[];
}

export interface ReminderPage {
  items: Reminder[];
  total: number;
  page: number;
  page_size: number;
}

export interface KindStat {
  kind: ReminderKind;
  count: number;
}

export interface ReminderStats {
  overdue: number;
  due_today: number;
  due_in_7_days: number;
  due_in_30_days: number;
  open_total: number;
  done_total: number;
  amount_open: number;
  by_kind: KindStat[];
}

export interface CalendarDay {
  date: string;
  in_month: boolean;
  items: Reminder[];
}

export interface CalendarMonth {
  year: number;
  month: number;
  grid_start: string;
  grid_end: string;
  days: CalendarDay[];
}

export interface AppNotification {
  id: number;
  reminder_id: number;
  offset_days: number;
  title: string;
  body: string;
  severity: 'info' | 'warning' | 'critical' | 'danger';
  scheduled_for: string;
  status: NotificationStatus;
  sent_at: string | null;
  read_at: string | null;
  displayed_at: string | null;
  channel_results: Record<string, { ok: boolean; detail: string }> | null;
}

export interface NotificationCounts {
  unread: number;
  total: number;
}

export interface AttentionState {
  count: number;
  days: number;
  title: string | null;
}

export interface AppSettings {
  channel_inapp: boolean;
  channel_push: boolean;
  channel_email: boolean;
  default_alert_offsets: number[];
  overdue_repeat_days: number;
  overdue_max_reminders: number;
  daily_send_time: string;
  notify_emails: string[];
  quiet_until_next_day: boolean;
  /** Entro quanti giorni un avviso ignorato continua a segnalarsi. 0 = mai. */
  insistent_alert_days: number;
}

export interface SettingsRead extends AppSettings {
  push_configured: boolean;
  email_configured: boolean;
  timezone: string;
}

export interface PushSubscriptionInfo {
  id: number;
  endpoint: string;
  label: string | null;
  active: boolean;
  created_at: string;
}

export interface ImportPreviewRow {
  row: number;
  data: Record<string, string>;
  errors: string[];
}

export interface ImportPreview {
  columns: string[];
  suggested_mapping: Record<string, string>;
  rows: ImportPreviewRow[];
  total_rows: number;
}

export interface ImportMapping {
  title: string;
  due_date: string;
  kind?: ReminderKind;
  description?: string | null;
  amount?: string | null;
  owner?: string | null;
  reference?: string | null;
  external_id?: string | null;
  date_format?: string | null;
  source: string;
  default_alert_offsets?: number[] | null;
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
}

export interface SetupStatus {
  configured: boolean;
  database_url_masked: string | null;
  source: 'config' | 'env' | 'none';
  device_name: string;
  email_sender_device: boolean;
}

export interface ConnectionTestResult {
  ok: boolean;
  detail: string;
}

export interface SetupPayload {
  database_url: string;
  device_name?: string | null;
  email_sender_device: boolean;
}

export interface ReminderQuery {
  q?: string;
  status?: ReminderStatus | '';
  kind?: ReminderKind | '';
  due_from?: string;
  due_to?: string;
  overdue_only?: boolean;
  page?: number;
  page_size?: number;
  sort?: string;
}

export interface CalendarQuery {
  year: number;
  month: number;
  kind?: ReminderKind | '';
  include_done?: boolean;
}
