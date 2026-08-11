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
  },
});
