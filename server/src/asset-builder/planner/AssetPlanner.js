import { RULES_BY_FAMILY } from './rules.js';
import { assetPlanItemSchema } from '../schemas.js';

/**
 * Decides what resources a lesson actually needs, based on the Analyzer's
 * output — never a fixed "every lesson gets N photos" default. The rule
 * table lives in rules.js; this function just looks up the right rules,
 * validates them, and drops anything with zero quantity.
 */
export function planLessonAssets(analysis) {
  const ruleFn = RULES_BY_FAMILY[analysis.disciplineFamily] || RULES_BY_FAMILY.generic;
  const rawItems = ruleFn(analysis);

  return rawItems
    .filter((item) => item.quantity > 0)
    .map((item) => assetPlanItemSchema.parse(item));
}
