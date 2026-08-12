'use strict';

const { contextBridge, ipcRenderer } = require('electron');

/**
 * Ponte minimo fra processo principale e interfaccia: serve solo a portare
 * l'utente sulla scadenza giusta quando clicca una notifica di Windows.
 */
contextBridge.exposeInMainWorld('scadenzario', {
  isDesktop: true,
  onNavigate: (callback) => {
    ipcRenderer.on('navigate', (_event, route) => callback(route));
    // Il processo principale può chiedere una rotta prima che l'interfaccia
    // sia avviata — è il caso normale: la finestra viene creata proprio in
    // risposta al click sulla notifica. Finché nessuno ascolta, quel messaggio
    // si perderebbe; qui si segnala che da adesso c'è chi lo raccoglie.
    ipcRenderer.send('interfaccia-pronta');
  },
});
