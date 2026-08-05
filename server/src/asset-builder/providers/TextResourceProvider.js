import { AssetProvider } from './AssetProvider.js';

/**
 * Builds structured, no-network resources (glossary, flashcards, formula
 * sheet, worked examples, reference table) directly from what the Analyzer
 * already pulled out of the lesson's real text — sentence excerpts tied to
 * each term, extracted formula expressions, and sections whose heading
 * marks them as a worked example. Nothing here is fabricated: every field
 * traces back to an actual sentence/section in the lesson content.
 */
export class TextResourceProvider extends AssetProvider {
  constructor() {
    super('text-extractor');
  }

  async find(planItem, analysis) {
    switch (planItem.resourceType) {
      case 'glossary':
        return this.#glossary(analysis);
      case 'flashcards':
        return this.#flashcards(analysis);
      case 'formula':
        return this.#formulas(analysis);
      case 'example':
        return this.#examples(planItem, analysis);
      case 'table':
        return this.#referenceTable(analysis);
      default:
        return [];
    }
  }

  #glossary(analysis) {
    const terms = Object.entries(analysis.excerpts || {});
    if (terms.length === 0) return [];
    const content = {
      lessonTopic: analysis.mainTopic,
      terms: terms.map(([term, excerpt]) => ({ term, definition: excerpt })),
    };
    return [this.#jsonCandidate('glossary', `${analysis.mainTopic} — glosario`, content, analysis.keywords)];
  }

  #flashcards(analysis) {
    const terms = Object.entries(analysis.excerpts || {});
    if (terms.length === 0) return [];
    const content = terms.map(([term, excerpt]) => ({ front: term, back: excerpt }));
    return [this.#jsonCandidate('flashcards', `${analysis.mainTopic} — flashcards`, content, analysis.keywords)];
  }

  #formulas(analysis) {
    if (!analysis.formulas?.length) return [];
    const content = { lessonTopic: analysis.mainTopic, expressions: analysis.formulas };
    return [this.#jsonCandidate('formula', `${analysis.mainTopic} — fórmulas`, content, analysis.keywords)];
  }

  #examples(planItem, analysis) {
    if (!analysis.workedExamples?.length) return [];
    return analysis.workedExamples
      .slice(0, planItem.quantity)
      .map((ex) =>
        this.#jsonCandidate('example', ex.heading, { heading: ex.heading, body: ex.body }, analysis.keywords)
      );
  }

  #referenceTable(analysis) {
    const terms = Object.entries(analysis.excerpts || {});
    if (terms.length === 0) return [];
    const content = { headers: ['Término', 'Referencia'], rows: terms.map(([term, excerpt]) => [term, excerpt]) };
    return [this.#jsonCandidate('table', `${analysis.mainTopic} — tabla de referencia`, content, analysis.keywords)];
  }

  #jsonCandidate(resourceType, title, content, keywords) {
    return {
      provider: this.name,
      resourceType,
      format: 'json',
      title,
      license: 'proprietary-generated',
      keywords,
      bytes: Buffer.from(JSON.stringify(content, null, 2), 'utf8'),
      raw: { extractedFrom: 'lesson-content' },
    };
  }
}
