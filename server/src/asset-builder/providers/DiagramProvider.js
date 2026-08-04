import { AssetProvider } from './AssetProvider.js';
import { buildConceptMapMermaid, buildSequenceTimelineSvg, buildRelationalSvg } from './diagramTemplates.js';

/**
 * Generates diagrams/illustrations procedurally from the lesson's own
 * analysis data — no network call, no external dependency, never fails for
 * lack of connectivity. This is deliberately high in the priority chain in
 * practice (via the Planner preferring 'diagram'/'illustration' resource
 * types for technical content) so technical concepts get a diagram instead
 * of a stock photo, per the spec.
 */
export class DiagramProvider extends AssetProvider {
  constructor() {
    super('diagram-generator');
  }

  async find(planItem, analysis) {
    // Diagrams are always ours to generate. For 'illustration' we only claim
    // it when the plan explicitly asked for a synthetic-diagram format
    // (svg/mermaid/timeline-svg) — e.g. engineering/generic rules. A request
    // for a photo-style illustration (preferredFormat 'scientific-illustration',
    // 'photo', 'historical-photo') is left to the sourced-image providers
    // instead of being silently swapped for a generic concept map.
    const diagramFormats = ['svg', 'mermaid', 'timeline-svg'];
    const claimsDiagram = planItem.resourceType === 'diagram';
    const claimsIllustration = planItem.resourceType === 'illustration' && diagramFormats.includes(planItem.preferredFormat);
    if (!claimsDiagram && !claimsIllustration) return [];

    const format = planItem.preferredFormat || 'mermaid';
    let bytes;
    let mimeFormat;

    if (format === 'timeline-svg') {
      bytes = Buffer.from(buildSequenceTimelineSvg(analysis), 'utf8');
      mimeFormat = 'svg';
    } else if (format === 'svg') {
      bytes = Buffer.from(buildRelationalSvg(analysis), 'utf8');
      mimeFormat = 'svg';
    } else {
      bytes = Buffer.from(buildConceptMapMermaid(analysis), 'utf8');
      mimeFormat = 'mermaid';
    }

    return [
      {
        provider: this.name,
        resourceType: planItem.resourceType,
        format: mimeFormat,
        title: `${analysis.mainTopic} — ${format}`,
        license: 'proprietary-generated',
        keywords: analysis.keywords,
        bytes,
        raw: { generatedFrom: 'analysis', preferredFormat: format },
      },
    ];
  }
}
