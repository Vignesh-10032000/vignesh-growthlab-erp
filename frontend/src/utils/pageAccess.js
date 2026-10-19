export function pageKey(path) {
  if (/^\/billing\/customers\/\d+\/ledger$/.test(path)) return 'reports'
  if (path.startsWith('/billing/customers')) return 'customers'
  const root = path.split('/')[1]
  return ({ 'bank-statement': 'bank', 'audit-log': 'security' })[root] || root || 'dashboard'
}
