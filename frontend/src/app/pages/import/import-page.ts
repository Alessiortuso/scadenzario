import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { ImportMapping, ImportPreview, ImportResult } from '../../core/models';
import { ToastService } from '../../core/toast.service';

interface FieldSpec {
  key: keyof ImportMapping;
  label: string;
  required: boolean;
}

const FIELDS: FieldSpec[] = [
  { key: 'title', label: 'Titolo', required: true },
  { key: 'due_date', label: 'Data di scadenza', required: true },
  { key: 'description', label: 'Note / descrizione', required: false },
  { key: 'amount', label: 'Importo', required: false },
  { key: 'owner', label: 'Cliente / responsabile', required: false },
  { key: 'reference', label: 'Riferimento', required: false },
  { key: 'category', label: 'Categoria', required: false },
  { key: 'external_id', label: 'ID esterno (per aggiornare senza duplicare)', required: false },
];

@Component({
  selector: 'app-import',
  imports: [FormsModule],
  templateUrl: './import-page.html',
  styleUrl: './import-page.scss',
})
export class ImportPage {
  private readonly api = inject(ApiService);
  private readonly toasts = inject(ToastService);

  readonly fields = FIELDS;

  readonly file = signal<File | null>(null);
  readonly preview = signal<ImportPreview | null>(null);
  readonly mapping = signal<Record<string, string>>({});
  readonly source = signal('import');
  readonly dateFormat = signal('');
  readonly busy = signal(false);
  readonly result = signal<ImportResult | null>(null);

  async onFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.file.set(file);
    this.preview.set(null);
    this.result.set(null);
    if (!file) {
      return;
    }

    this.busy.set(true);
    try {
      const preview = await firstValueFrom(this.api.importPreview(file));
      this.preview.set(preview);
      this.mapping.set({ ...preview.suggested_mapping });
      this.source.set(file.name.replace(/\.[^.]+$/, '').slice(0, 40) || 'import');
    } catch (err) {
      this.toasts.error('Lettura del file non riuscita: ' + describe(err));
    } finally {
      this.busy.set(false);
    }
  }

  setMapping(field: string, column: string): void {
    this.mapping.update((current) => {
      const next = { ...current };
      if (column) {
        next[field] = column;
      } else {
        delete next[field];
      }
      return next;
    });
  }

  get canApply(): boolean {
    const map = this.mapping();
    return Boolean(this.file() && map['title'] && map['due_date']);
  }

  private buildMapping(): ImportMapping {
    return {
      ...(this.mapping() as unknown as ImportMapping),
      source: this.source().trim() || 'import',
      date_format: this.dateFormat().trim() || null,
    };
  }

  async refreshPreview(): Promise<void> {
    const file = this.file();
    if (!file || !this.canApply) {
      return;
    }
    this.busy.set(true);
    try {
      this.preview.set(await firstValueFrom(this.api.importPreview(file, this.buildMapping())));
    } catch (err) {
      this.toasts.error('Anteprima non riuscita: ' + describe(err));
    } finally {
      this.busy.set(false);
    }
  }

  async apply(): Promise<void> {
    const file = this.file();
    if (!file || !this.canApply) {
      return;
    }
    this.busy.set(true);
    try {
      const result = await firstValueFrom(this.api.importApply(file, this.buildMapping()));
      this.result.set(result);
      this.toasts.success(`Import completato: ${result.created} create, ${result.updated} aggiornate`);
    } catch (err) {
      this.toasts.error('Import non riuscito: ' + describe(err));
    } finally {
      this.busy.set(false);
    }
  }

  previewValue(row: Record<string, string>, key: string): string {
    const value = row[key];
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }
}

function describe(err: unknown): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' ? detail : 'errore imprevisto';
}
