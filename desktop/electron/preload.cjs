const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('workpulse', {
  platform: 'electron',
  saveSecureToken: (key, value) => ipcRenderer.invoke('wp:saveSecureToken', key, value),
  getSecureToken: (key) => ipcRenderer.invoke('wp:getSecureToken', key),
  deleteSecureToken: (key) => ipcRenderer.invoke('wp:deleteSecureToken', key),
  getDeviceInfo: () => ipcRenderer.invoke('wp:getDeviceInfo'),
  getConnectedWifi: () => ipcRenderer.invoke('wp:getConnectedWifi'),
  getWifiEvents: (since) => ipcRenderer.invoke('wp:getWifiEvents', since),
  setPresenceSession: (session) => ipcRenderer.invoke('wp:setPresenceSession', session),
  drainPowerEvents: () => ipcRenderer.invoke('wp:drainPowerEvents'),
  peekPowerEvents: () => ipcRenderer.invoke('wp:peekPowerEvents'),
  drainBreakAwayQueue: () => ipcRenderer.invoke('wp:drainBreakAwayQueue'),
  getSystemIdleSeconds: () => ipcRenderer.invoke('wp:getSystemIdleSeconds'),
  showNotification: (payload) => ipcRenderer.invoke('wp:showNotification', payload),
  onPowerEventQueued: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('power-presence:queued', handler);
    return () => ipcRenderer.removeListener('power-presence:queued', handler);
  },
  onBreakAwayQueued: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('break-away:queued', handler);
    return () => ipcRenderer.removeListener('break-away:queued', handler);
  },
  checkForUpdates: () => ipcRenderer.invoke('wp:checkForUpdates'),
  installUpdateNow: () => ipcRenderer.invoke('wp:installUpdateNow'),
  getAppVersion: () => ipcRenderer.invoke('wp:getAppVersion'),
  setUpdateContext: (ctx) => ipcRenderer.invoke('wp:setUpdateContext', ctx),
  onUpdateStatus: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('wp:update-status', handler);
    return () => ipcRenderer.removeListener('wp:update-status', handler);
  },
});
