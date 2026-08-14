import { Routes } from '@angular/router';

import { setupGuard } from './core/setup.service';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'configurazione',
    title: 'Configurazione · Promemoria',
    loadComponent: () => import('./pages/setup/setup-page').then((m) => m.SetupPage),
  },
  {
    path: 'dashboard',
    title: 'Dashboard · Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.DashboardPage),
  },
  {
    path: 'calendario',
    title: 'Calendario · Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/calendar/calendar-page').then((m) => m.CalendarPage),
  },
  {
    path: 'promemoria',
    title: 'Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/reminders/reminder-list').then((m) => m.ReminderListPage),
  },
  {
    path: 'promemoria/nuovo',
    title: 'Nuovo promemoria · Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/reminders/reminder-form').then((m) => m.ReminderFormPage),
  },
  {
    path: 'promemoria/:id',
    title: 'Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/reminders/reminder-form').then((m) => m.ReminderFormPage),
  },
  {
    path: 'import',
    title: 'Importazione · Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/import/import-page').then((m) => m.ImportPage),
  },
  {
    path: 'impostazioni',
    title: 'Impostazioni · Promemoria',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/settings/settings-page').then((m) => m.SettingsPage),
  },
  // Le rotte della 1.0.x restano valide: una notifica di Windows già
  // consegnata, o un segnalibro, puntano ancora a /scadenze/12.
  { path: 'scadenze', pathMatch: 'full', redirectTo: 'promemoria' },
  { path: 'scadenze/nuova', redirectTo: 'promemoria/nuovo' },
  { path: 'scadenze/:id', redirectTo: 'promemoria/:id' },
  { path: '**', redirectTo: 'dashboard' },
];
