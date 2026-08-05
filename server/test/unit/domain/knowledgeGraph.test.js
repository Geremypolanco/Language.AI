import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { KnowledgeGraph, KnowledgeNode } from '../../../src/domain/editorial/index.js';

describe('KnowledgeGraph', () => {
  test('getPrerequisitesFor returns the nodes a node depends on', () => {
    const graph = new KnowledgeGraph({
      nodes: [
        new KnowledgeNode({ id: 'algebra', type: 'concept', label: 'Algebra' }),
        new KnowledgeNode({ id: 'calculus', type: 'concept', label: 'Calculus', relatedNodeIds: ['algebra'] }),
      ],
    });
    const prereqs = graph.getPrerequisitesFor('calculus').map((n) => n.id);
    assert.deepEqual(prereqs, ['algebra']);
  });

  test('hasCycle is false for a valid DAG', () => {
    const graph = new KnowledgeGraph({
      nodes: [
        new KnowledgeNode({ id: 'a', type: 'concept', label: 'A' }),
        new KnowledgeNode({ id: 'b', type: 'concept', label: 'B', relatedNodeIds: ['a'] }),
        new KnowledgeNode({ id: 'c', type: 'concept', label: 'C', relatedNodeIds: ['b'] }),
      ],
    });
    assert.equal(graph.hasCycle(), false);
  });

  test('hasCycle detects a direct cycle', () => {
    const graph = new KnowledgeGraph({
      nodes: [
        new KnowledgeNode({ id: 'a', type: 'concept', label: 'A', relatedNodeIds: ['b'] }),
        new KnowledgeNode({ id: 'b', type: 'concept', label: 'B', relatedNodeIds: ['a'] }),
      ],
    });
    assert.equal(graph.hasCycle(), true);
  });

  test('hasCycle detects a longer transitive cycle (a -> b -> c -> a)', () => {
    const graph = new KnowledgeGraph({
      nodes: [
        new KnowledgeNode({ id: 'a', type: 'concept', label: 'A', relatedNodeIds: ['b'] }),
        new KnowledgeNode({ id: 'b', type: 'concept', label: 'B', relatedNodeIds: ['c'] }),
        new KnowledgeNode({ id: 'c', type: 'concept', label: 'C', relatedNodeIds: ['a'] }),
      ],
    });
    assert.equal(graph.hasCycle(), true);
  });

  test('topologicalOrder places dependencies before dependents', () => {
    const graph = new KnowledgeGraph({
      nodes: [
        new KnowledgeNode({ id: 'calculus', type: 'concept', label: 'Calculus', relatedNodeIds: ['algebra'] }),
        new KnowledgeNode({ id: 'algebra', type: 'concept', label: 'Algebra' }),
      ],
    });
    const order = graph.topologicalOrder().map((n) => n.id);
    assert.deepEqual(order, ['algebra', 'calculus']);
  });

  test('topologicalOrder throws on a cyclic graph instead of returning a bogus order', () => {
    const graph = new KnowledgeGraph({
      nodes: [
        new KnowledgeNode({ id: 'a', type: 'concept', label: 'A', relatedNodeIds: ['b'] }),
        new KnowledgeNode({ id: 'b', type: 'concept', label: 'B', relatedNodeIds: ['a'] }),
      ],
    });
    assert.throws(() => graph.topologicalOrder(), /cycle/);
  });
});
