// Format API Decimal strings without converting money to floating point.
export function money(value: string, currency = 'RUB') {
  const [whole, raw = ''] = value.split('.')
  const fraction = raw.replace(/0+$/, '')
  const amount = `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0')}${fraction ? `,${fraction.padEnd(2, '0')}` : ''}`
  return `${amount} ${currency === 'RUB' ? '₽' : currency}`.trim()
}
