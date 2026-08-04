/**
 * Discipline/content-type -> asset plan rule table. This is the single
 * place that decides "does this lesson actually need photos, or does a
 * diagram teach the concept better" — the Planner's whole job per the spec
 * ("no asumir que todas las lecciones necesitan fotografías").
 *
 * Each rule function receives the lesson `analysis` and returns an array of
 * plan items (validated against assetPlanItemSchema by the caller).
 */
export const RULES_BY_FAMILY = {
  languages(analysis) {
    const terms = analysis.keywords.slice(0, 8);
    return [
      {
        resourceType: 'image',
        quantity: Math.min(5, Math.max(3, terms.length)),
        priority: 'required',
        preferredFormat: 'photo',
        rationale: 'Vocabulary is learned faster with concrete visual references for each term.',
        searchTerms: terms,
      },
      {
        resourceType: 'audio',
        quantity: terms.length || 1,
        priority: 'required',
        preferredFormat: 'pronunciation',
        rationale: 'Spoken pronunciation of each vocabulary term is core to language acquisition.',
        searchTerms: terms,
      },
      {
        resourceType: 'flashcards',
        quantity: 1,
        priority: 'required',
        rationale: 'Flashcards drive spaced-repetition practice of the lesson vocabulary.',
        searchTerms: terms,
      },
      {
        resourceType: 'glossary',
        quantity: 1,
        priority: 'required',
        rationale: 'A glossary anchors term definitions for reference during practice.',
        searchTerms: analysis.keywords,
      },
    ];
  },

  mathematics(analysis) {
    return [
      {
        resourceType: 'formula',
        quantity: 1, // one structured document bundling every formula found in the lesson
        priority: 'required',
        rationale: 'Quantitative content is defined by its formulas, not by photographs.',
        searchTerms: analysis.concepts,
      },
      {
        resourceType: 'diagram',
        quantity: 2,
        priority: 'recommended',
        preferredFormat: 'svg',
        rationale: 'Graphs/plots of the functions or relationships taught aid comprehension better than stock photos.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'example',
        quantity: 3,
        priority: 'required',
        rationale: 'Worked examples are the primary learning aid for procedural/quantitative topics.',
        searchTerms: analysis.concepts,
      },
      {
        resourceType: 'table',
        quantity: 1,
        priority: 'optional',
        rationale: 'A reference table (values, identities) is useful but not always applicable.',
        searchTerms: analysis.keywords,
      },
    ];
  },

  science(analysis) {
    return [
      {
        resourceType: 'illustration',
        quantity: Math.max(2, analysis.concepts.length),
        priority: 'required',
        preferredFormat: 'scientific-illustration',
        rationale: 'Scientific illustrations (labeled diagrams of structures/processes) teach mechanism better than photos.',
        searchTerms: analysis.concepts,
      },
      {
        resourceType: 'diagram',
        quantity: 2,
        priority: 'recommended',
        preferredFormat: 'mermaid',
        rationale: 'Processes and cycles (e.g. metabolic pathways) are clearer as flow/process diagrams.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'glossary',
        quantity: 1,
        priority: 'recommended',
        rationale: 'Scientific terminology benefits from an accompanying glossary.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'image',
        quantity: 2,
        priority: 'optional',
        preferredFormat: 'photo',
        rationale: 'Real specimen/phenomenon photography is a useful supplement, not a substitute for illustration.',
        searchTerms: analysis.keywords,
      },
    ];
  },

  engineering(analysis) {
    return [
      {
        resourceType: 'diagram',
        quantity: Math.max(2, analysis.concepts.length),
        priority: 'required',
        preferredFormat: 'mermaid',
        rationale: 'System/process/architecture diagrams are the primary way to explain engineering concepts.',
        searchTerms: analysis.concepts,
      },
      {
        resourceType: 'illustration',
        quantity: 1,
        priority: 'recommended',
        preferredFormat: 'svg',
        rationale: 'Vector illustrations of components/circuits scale cleanly and stay technically precise.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'example',
        quantity: 2,
        priority: 'required',
        rationale: 'Applied examples ground abstract technical concepts.',
        searchTerms: analysis.concepts,
      },
      {
        resourceType: 'interactive',
        quantity: 1,
        priority: 'optional',
        rationale: 'An interactive model/simulation deepens understanding when available.',
        searchTerms: analysis.keywords,
      },
    ];
  },

  history(analysis) {
    return [
      {
        resourceType: 'diagram',
        quantity: 1,
        priority: 'required',
        preferredFormat: 'timeline-svg',
        rationale: 'A timeline is the primary way to situate events in historical narrative content.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'image',
        quantity: 3,
        priority: 'recommended',
        preferredFormat: 'historical-photo',
        rationale: 'Period photographs/artwork give historical content authenticity that diagrams cannot.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'gallery',
        quantity: 1,
        priority: 'optional',
        rationale: 'A curated gallery supports deeper visual exploration of the period/event.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'table',
        quantity: 1,
        priority: 'optional',
        rationale: 'A chronology table complements the timeline for reference.',
        searchTerms: analysis.keywords,
      },
    ];
  },

  arts(analysis) {
    return [
      {
        resourceType: 'gallery',
        quantity: 1,
        priority: 'required',
        rationale: 'Arts content is inherently visual/auditory — a curated gallery is the core resource.',
        searchTerms: analysis.keywords,
      },
      {
        resourceType: 'image',
        quantity: 4,
        priority: 'recommended',
        preferredFormat: 'photo',
        rationale: 'Reference images of works/technique support the lesson.',
        searchTerms: analysis.keywords,
      },
    ];
  },

  generic(analysis) {
    return [
      {
        resourceType: 'diagram',
        quantity: 1,
        priority: 'recommended',
        preferredFormat: 'mermaid',
        rationale: 'A concept map helps orient the lesson topic regardless of discipline.',
        searchTerms: analysis.concepts.length ? analysis.concepts : analysis.keywords,
      },
      {
        resourceType: 'glossary',
        quantity: 1,
        priority: 'optional',
        rationale: 'Key terminology benefits from a glossary even in generic content.',
        searchTerms: analysis.keywords,
      },
    ];
  },
};
