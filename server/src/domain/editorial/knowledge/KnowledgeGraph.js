import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { KnowledgeNode } from '../valueObjects/KnowledgeNode.js';

/**
 * The graph of concepts/competencies/objectives and their prerequisite
 * relationships. `relatedNodeIds` on a node means "this node depends on" —
 * the same direction a Prerequisite edge points.
 */
export class KnowledgeGraph extends DomainEntity {
  static schema = z.object({
    nodes: z.array(z.instanceof(KnowledgeNode)).default([]),
  });

  getNode(id) {
    return this.nodes.find((n) => n.id === id) ?? null;
  }

  getPrerequisitesFor(nodeId) {
    const node = this.getNode(nodeId);
    if (!node) return [];
    return node.relatedNodeIds.map((id) => this.getNode(id)).filter(Boolean);
  }

  /** True if the dependency graph has a cycle (a curriculum authoring error — no node can prerequisite itself transitively). */
  hasCycle() {
    const visiting = new Set();
    const visited = new Set();

    const visit = (nodeId) => {
      if (visited.has(nodeId)) return false;
      if (visiting.has(nodeId)) return true;
      visiting.add(nodeId);
      const node = this.getNode(nodeId);
      for (const dep of node?.relatedNodeIds ?? []) {
        if (visit(dep)) return true;
      }
      visiting.delete(nodeId);
      visited.add(nodeId);
      return false;
    };

    return this.nodes.some((n) => visit(n.id));
  }

  /** Kahn's algorithm — nodes with no unresolved prerequisites first. Throws if the graph has a cycle. */
  topologicalOrder() {
    if (this.hasCycle()) {
      throw new Error('KnowledgeGraph contains a cycle; no valid topological order exists.');
    }

    const remaining = new Map(this.nodes.map((n) => [n.id, new Set(n.relatedNodeIds)]));
    const ordered = [];

    while (remaining.size > 0) {
      const ready = [...remaining.entries()].filter(([, deps]) => deps.size === 0).map(([id]) => id);
      for (const id of ready) {
        ordered.push(this.getNode(id));
        remaining.delete(id);
      }
      for (const deps of remaining.values()) {
        for (const id of ready) deps.delete(id);
      }
    }

    return ordered;
  }
}
