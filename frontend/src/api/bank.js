import api from './index'

export const bankStmtAPI = {
  list: (params) => api.get('/api/v1/bank-stock-statement/', { params }),
  generate: (d) => api.post('/api/v1/bank-stock-statement/', d),
  get: (id) => api.get(`/api/v1/bank-stock-statement/${id}`),
}

export const bankReconAPI = {
  reconcile: (d) => api.post('/api/v1/bank-reconciliation/reconcile', d),
  create: (d) => api.post('/api/v1/bank-reconciliation/', d),
  list: (params) => api.get('/api/v1/bank-reconciliation/', { params }),
  get: (id) => api.get(`/api/v1/bank-reconciliation/${id}`),
  match: (id, d) => api.post(`/api/v1/bank-reconciliation/${id}/match`, d),
  unmatch: (id, d) => api.post(`/api/v1/bank-reconciliation/${id}/unmatch`, d),
  adjustment: (id, d) => api.post(`/api/v1/bank-reconciliation/${id}/adjustment`, d),
  finalize: (id) => api.post(`/api/v1/bank-reconciliation/${id}/finalize`),
  importFile: (formData) => api.post('/api/v1/bank-reconciliation/import-file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
}

export const notificationAPI = {
  list: () => api.get('/api/v1/notifications/'),
  markRead: (id) => api.patch(`/api/v1/notifications/${id}/read`),
  getSettings: () => api.get('/api/v1/notifications/settings'),
  updateSettings: (d) => api.put('/api/v1/notifications/settings', d),
  testEmail: (email) => api.post('/api/v1/notifications/test-email', { to_email: email }),
}

export const scheduledAPI = {
  status: () => api.get('/api/v1/scheduled-reports/status'),
  getSettings: () => api.get('/api/v1/scheduled-reports/settings'),
  updateSettings: (d) => api.put('/api/v1/scheduled-reports/settings', d),
}

export const backupAPI = {
  run: () => api.post('/api/v1/backup/run'),
  status: () => api.get('/api/v1/backup/status'),
}

// Alias for backward compatibility
export const bankStatementAPI = bankStmtAPI
