import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildConceptMapMermaid,
  buildSequenceTimelineSvg,
  buildRelationalSvg,
} from '../../../src/asset-builder/providers/diagramTemplates.js';

const analysis = {
  mainTopic: 'Ecuaciones lineales',
  subtopics: ['Introducción', 'Propiedades'],
  concepts: ['incógnita', 'igualdad'],
  keywords: ['ecuacion', 'lineal'],
};

describe('diagram templates', () => {
  test('buildConceptMapMermaid produces valid mermaid graph syntax', () => {
    const mermaid = buildConceptMapMermaid(analysis);
    assert.match(mermaid, /^graph TD/);
    assert.match(mermaid, /root\[/);
    assert.ok(mermaid.includes('Introducción') || mermaid.includes('Introduccion'));
  });

  test('buildConceptMapMermaid never fabricates content beyond what analysis provided', () => {
    const emptyAnalysis = { mainTopic: 'X', subtopics: [], concepts: [] };
    const mermaid = buildConceptMapMermaid(emptyAnalysis);
    // Only the root node — no invented subtopics/concepts.
    assert.equal((mermaid.match(/-->/g) || []).length, 0);
    assert.equal((mermaid.match(/-\.->/g) || []).length, 0);
  });

  test('buildSequenceTimelineSvg produces a well-formed SVG document', () => {
    const svg = buildSequenceTimelineSvg(analysis);
    assert.match(svg, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
    assert.match(svg, /<\/svg>/);
    assert.equal((svg.match(/<circle/g) || []).length, analysis.subtopics.length);
  });

  test('buildRelationalSvg centers the main topic and spokes out to concepts', () => {
    const svg = buildRelationalSvg(analysis);
    assert.match(svg, /<svg/);
    // One spoke line per concept, plus the center circle.
    assert.equal((svg.match(/<line/g) || []).length, analysis.concepts.length);
    assert.ok(svg.includes('Ecuaciones'));
  });

  test('SVG output escapes text content (no raw XSS-able characters from labels)', () => {
    const svg = buildRelationalSvg({ mainTopic: 'A <script>', concepts: ['b & c'], keywords: [] });
    assert.ok(!svg.includes('<script>'));
    assert.ok(svg.includes('&amp;'));
  });
});
