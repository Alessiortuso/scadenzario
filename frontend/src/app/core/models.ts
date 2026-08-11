export type DeadlineStatus = 'open' | 'done' | 'cancelled';
export type Priority = 'low' | 'normal' | 'high' | 'critical';
export type Recurrence = 'none' | 'monthly' | 'quarterly' | 'semiannual' | 'yearly';
export type NotificationStatus = 'pending' | 'sent' | 'failed' | 'cancelled';

export interface Category {
  id: number;
  name: string;
  color: string;
  alert_offsets: number[] | null;
}

export interface Deadline {
  id: number;
  title: string;
  description: string | null;
  due_date: string;
  status: DeadlineStatus;
  priority: Priority;
  recurrence: Recurrence;
  amount: number | null;
  owner: string | null;
  reference: string | null;
  category_id: number | null;
  category: Category | null;
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

export interface DeadlinePage {
  items: Deadline[];
  total: number;
  page: number;
  page_size: number;
}

export interface CategoryStat {
  category_id: number | null;
  name: string;
  color: string;
  count: number;
}

export interface DeadlineStats {
  overdue: number;
  due_today: number;
  due_in_7_days: number;
  due_in_30_days: number;
  open_total: number;
  done_total: number;
  amount_open: number;
  by_category: CategoryStat[];
}

export interface AppNotification {
  id: number;
  deadline_id: number;
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
  description?: string | null;
  amount?: string | null;
  owner?: string | null;
  reference?: string | null;
  category?: string | null;
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

export interface DeadlineQuery {
  q?: string;
  status?: DeadlineStatus | '';
  category_id?: number | null;
  due_from?: string;
  due_to?: string;
  overdue_only?: boolean;
  page?: number;
  page_size?: number;
  sort?: string;
}
