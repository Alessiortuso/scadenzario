'use strict';

const { contextBridge, ipcRenderer } = require('electron');

/**
 * Ponte minimo fra processo principale e interfaccia: serve solo a portare
 * l'utente sul promemoria giusto quando clicca una notifica di Windows.
 */
contextBridge.exposeInMainWorld('promemoria', {
  isDesktop: true,
  /**
   * L'utente ha aperto l'elenco o la scheda di un promemoria: la
   * segnalazione sulla barra può spegnersi subito, senza aspettare il
   * prossimo giro di interrogazione del backend.
   */
  segnalaLettura: () => ipcRenderer.send('promemoria-guardati'),
  onNavigate: (callback) => {
    ipcRenderer.on('navigate', (_event, route) => callback(route));
    // Il processo principale può chiedere una rotta prima che l'interfaccia
    // sia avviata — è il caso normale: la finestra viene creata proprio in
    // risposta al click sulla notifica. Finché nessuno ascolta, quel messaggio
    // si perderebbe; qui si segnala che da adesso c'è chi lo raccoglie.
    ipcRenderer.send('interfaccia-pronta');
  },
});
