import { createContext, useContext } from 'react'

export const FeatureContext = createContext({ optional: [] as string[], timezone: 'Europe/Moscow' })
export function useFeatures() { return useContext(FeatureContext) }
export function dateTime(value: string, timezone: string) {
  return new Date(value).toLocaleString('ru-RU', { timeZone: timezone })
}
