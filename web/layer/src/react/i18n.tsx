import { createContext, useContext, useMemo, type ReactNode } from 'react';

import {
  intlLocale,
  makeTranslator,
  type Locale,
  type Messages,
  type Translate,
} from '../core/i18n';

interface I18n {
  locale: Locale;
  intl: string;
  t: Translate;
  timeZone: string;
}

const Ctx = createContext<I18n>({
  locale: 'nb',
  intl: 'nb-NO',
  t: makeTranslator('nb'),
  timeZone: 'Europe/Oslo',
});

export function WeatherI18nProvider(props: {
  locale?: Locale;
  messages?: Messages;
  timeZone?: string;
  children: ReactNode;
}) {
  const { locale = 'nb', messages, timeZone = 'Europe/Oslo' } = props;
  const value = useMemo(
    () => ({ locale, intl: intlLocale(locale), t: makeTranslator(locale, messages), timeZone }),
    [locale, messages, timeZone],
  );
  return <Ctx.Provider value={value}>{props.children}</Ctx.Provider>;
}

export function useWeatherI18n(): I18n {
  return useContext(Ctx);
}
