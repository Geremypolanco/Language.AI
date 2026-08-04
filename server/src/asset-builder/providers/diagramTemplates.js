/**
 * Pure, dependency-free generators that turn real lesson-analysis data
 * (topic, subtopics, concepts, keywords) into diagram source. These never
 * fabricate content the analyzer didn't produce — no invented dates,
 * numbers, or data points — they visualize *structure and relationships*,
 * which is honestly derivable from any lesson's analysis.
 */

function sanitizeMermaidLabel(text) {
  return text.replace(/"/g, "'").slice(0, 60);
}

function escapeXml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Star-topology concept map: main topic in the center, subtopics/concepts as branches. */
export function buildConceptMapMermaid(analysis) {
  const rootId = 'root';
  const lines = ['graph TD', `${rootId}["${sanitizeMermaidLabel(analysis.mainTopic)}"]`];

  analysis.subtopics.slice(0, 8).forEach((subtopic, i) => {
    const nodeId = `sub${i}`;
    lines.push(`${nodeId}["${sanitizeMermaidLabel(subtopic)}"]`);
    lines.push(`${rootId} --> ${nodeId}`);
  });

  analysis.concepts.slice(0, 6).forEach((concept, i) => {
    const nodeId = `concept${i}`;
    lines.push(`${nodeId}("${sanitizeMermaidLabel(concept)}")`);
    lines.push(`${rootId} -.-> ${nodeId}`);
  });

  return lines.join('\n');
}

/** Sequential milestone timeline (order = subtopic order in the lesson, not fabricated dates). */
export function buildSequenceTimelineSvg(analysis) {
  const milestones = (analysis.subtopics.length ? analysis.subtopics : analysis.concepts).slice(0, 8);
  const width = Math.max(480, milestones.length * 160);
  const height = 200;
  const y = height / 2;
  const step = milestones.length > 1 ? (width - 120) / (milestones.length - 1) : 0;

  const nodes = milestones
    .map((label, i) => {
      const x = 60 + step * i;
      return `
        <circle cx="${x}" cy="${y}" r="10" fill="#6366f1" />
        <text x="${x}" y="${y + 34}" font-size="13" text-anchor="middle" font-family="system-ui,sans-serif">${escapeXml(
          label.slice(0, 24)
        )}</text>`;
    })
    .join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <line x1="60" y1="${y}" x2="${width - 60}" y2="${y}" stroke="#c7d2fe" stroke-width="3" />
    ${nodes}
  </svg>`;
}

/** Hub-and-spoke relational diagram: main topic in the center, related concepts/keywords around it. */
export function buildRelationalSvg(analysis) {
  const spokes = (analysis.concepts.length ? analysis.concepts : analysis.keywords).slice(0, 6);
  const size = 420;
  const center = size / 2;
  const radius = 150;

  const spokeElements = spokes
    .map((label, i) => {
      const angle = (2 * Math.PI * i) / spokes.length - Math.PI / 2;
      const x = center + radius * Math.cos(angle);
      const y = center + radius * Math.sin(angle);
      return `
        <line x1="${center}" y1="${center}" x2="${x}" y2="${y}" stroke="#c7d2fe" stroke-width="2" />
        <circle cx="${x}" cy="${y}" r="34" fill="#eef2ff" stroke="#6366f1" stroke-width="2" />
        <text x="${x}" y="${y + 4}" font-size="11" text-anchor="middle" font-family="system-ui,sans-serif">${escapeXml(
          label.slice(0, 16)
        )}</text>`;
    })
    .join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    ${spokeElements}
    <circle cx="${center}" cy="${center}" r="50" fill="#6366f1" />
    <text x="${center}" y="${center + 5}" font-size="13" fill="white" text-anchor="middle" font-family="system-ui,sans-serif">${escapeXml(
      analysis.mainTopic.slice(0, 18)
    )}</text>
  </svg>`;
}
