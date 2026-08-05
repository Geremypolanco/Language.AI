import { describe, test, expect } from 'vitest';
import { detectLanguage, localeForLanguageCode } from './languageDetect.js';

describe('detectLanguage', () => {
  test('detects Spanish from function-word frequency', () => {
    const result = detectLanguage('Hola, como esta usted por la manana');
    expect(result).toEqual({ code: 'es', locale: 'es-ES' });
  });

  test('detects English from function-word frequency', () => {
    const result = detectLanguage('Hello, how are you doing today my friend');
    expect(result).toEqual({ code: 'en', locale: 'en-US' });
  });

  test('returns null for text too short to guess reliably', () => {
    expect(detectLanguage('hola')).toBeNull();
    expect(detectLanguage('')).toBeNull();
  });

  test('returns null when no language markers match at all', () => {
    expect(detectLanguage('xyzzy qwzx vbnmk')).toBeNull();
  });

  test('is accent-insensitive', () => {
    const withAccents = detectLanguage('Qué tal está la mañana de hoy');
    const withoutAccents = detectLanguage('Que tal esta la manana de hoy');
    expect(withAccents).toEqual(withoutAccents);
    expect(withAccents.code).toBe('es');
  });
});

describe('localeForLanguageCode', () => {
  test('maps a known language code to its locale tag', () => {
    expect(localeForLanguageCode('fr')).toBe('fr-FR');
  });

  test('falls back to the raw code for an unknown language', () => {
    expect(localeForLanguageCode('xx')).toBe('xx');
  });
});
