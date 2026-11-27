import en from '../i18n/en.json';
import nb from '../i18n/nb.json';

export type Messages = Record<string, string>;
export type Locale = 'nb' | 'en';

export const MESSAGES: Record<Locale, Messages> = { nb, en };

/** Intl locale tag used for number/date formatting. */
export function intlLocale(locale: Locale): string {
  return locale === 'nb' ? 'nb-NO' : 'en-GB';
}

export type Translate = (key: string, params?: Record<string, string | number>) => string;

export function makeTranslator(locale: Locale, overrides?: Messages): Translate {
  const table = { ...MESSAGES[locale], ...(overrides ?? {}) };
  return (key, params) => {
    const template = table[key] ?? MESSAGES.en[key] ?? key;
    return template.replace(/\{(\w+)\}/g, (_, k: string) =>
      params && k in params ? String(params[k]) : `{${k}}`,
    );
  };
}
