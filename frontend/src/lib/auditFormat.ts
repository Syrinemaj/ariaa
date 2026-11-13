// Color-codes by what the action does, not literal prefix matching — new
// action names outside these buckets just fall through to the neutral
// default rather than breaking.
export function actionColor(action: string): string {
  if (/DELETE|DEACTIVAT|REJECT|FAIL|REVOKE/.test(action)) return '#dc2626'
  if (/CREATE|ACTIVAT|APPROV|COMPLET/.test(action)) return '#16a34a'
  if (/UPDATE|CHANGE|RENAME|RESTORE/.test(action)) return '#d97706'
  return 'var(--ink-2)'
}

export function formatAction(action: string): string {
  return action.toLowerCase().replace(/_/g, ' ')
}
