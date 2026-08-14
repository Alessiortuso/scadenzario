import { Pipe, PipeTransform } from '@angular/core';

/** L'ora di inizio come si scrive: "09:30:00" → "09:30", niente → stringa vuota.
 *
 * Il backend serializza un `time` con i secondi, che qui non dicono nulla: un
 * appuntamento non è mai «alle 09:30:00».
 */
@Pipe({ name: 'timeLabel' })
export class TimeLabelPipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    return value ? value.slice(0, 5) : '';
  }
}
