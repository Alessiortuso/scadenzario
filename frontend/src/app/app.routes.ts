import { Routes } from '@angular/router';

import { setupGuard } from './core/setup.service';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'configurazione',
    title: 'Configurazione · Scadenzario',
    loadComponent: () => import('./pages/setup/setup-page').then((m) => m.SetupPage),
  },
  {
    path: 'dashboard',
    title: 'Dashboard · Scadenzario',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.DashboardPage),
  },
  {
    path: 'scadenze',
    title: 'Scadenze · Scadenzario',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/deadlines/deadline-list').then((m) => m.DeadlineListPage),
  },
  {
    path: 'scadenze/nuova',
    title: 'Nuova scadenza · Scadenzario',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/deadlines/deadline-form').then((m) => m.DeadlineFormPage),
  },
  {
    path: 'scadenze/:id',
    title: 'Scadenza · Scadenzario',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/deadlines/deadline-form').then((m) => m.DeadlineFormPage),
  },
  {
    path: 'import',
    title: 'Importazione · Scadenzario',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/import/import-page').then((m) => m.ImportPage),
  },
  {
    path: 'impostazioni',
    title: 'Impostazioni · Scadenzario',
    canActivate: [setupGuard],
    loadComponent: () => import('./pages/settings/settings-page').then((m) => m.SettingsPage),
  },
  { path: '**', redirectTo: 'dashboard' },
];
