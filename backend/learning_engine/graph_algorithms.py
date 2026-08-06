"""Pure graph algorithms over a plain list of (from, to) edge tuples — no
database access, no async, nothing academy-specific. This is the layer
backend/learning_engine/knowledge_graph.py's academic_concept_relation
queries feed into: that module fetches edges as rows, this module answers
real structural questions about them (is it a DAG, what order can it be
studied in, what does finishing X unlock).

Kept separate from knowledge_graph.py on purpose — knowledge_graph.py owns
persistence (SQL), this module owns graph theory. Testing "does this detect
a cycle" should never require a database.
"""

from __future__ import annotations

Edge = tuple[str, str]


def has_cycle(nodes: list[str], edges: list[Edge]) -> bool:
    """True if the directed graph (nodes + edges) contains a cycle reachable
    from the given nodes. Edges whose endpoints aren't in `nodes` are still
    followed (a cycle can involve a node not explicitly listed), so this is
    safe to call with just "the edges I'm about to add" plus the existing
    node id set."""
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in nodes}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adjacency.get(node, ()):
            state = color.get(neighbor, WHITE)
            if state == GRAY:
                return True
            if state == WHITE and visit(neighbor):
                return True
        color[node] = BLACK
        return False

    for node in nodes:
        if color.get(node, WHITE) == WHITE:
            if visit(node):
                return True
    return False


def topological_order(nodes: list[str], edges: list[Edge]) -> list[str]:
    """Kahn's algorithm. Raises ValueError if the graph has a cycle (a
    curriculum's prerequisite graph must always be a DAG — see
    knowledge_graph.enrich_prerequisite_graph, which validates this before
    ever persisting an edge, so this should only raise on a genuine bug,
    not on real generated content). Nodes with no edges at all keep their
    original relative order (stable sort on in-degree-zero discovery), so a
    curriculum with no enriched prerequisites yet still returns its
    original course order unchanged."""
    in_degree: dict[str, int] = {n: 0 for n in nodes}
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        if src not in in_degree or dst not in in_degree:
            continue  # edge references a node outside this call's scope — ignore, not an error
        adjacency[src].append(dst)
        in_degree[dst] += 1

    # Stable: process nodes in their original list order whenever more than
    # one is ready, so output degrades gracefully to "original order" when
    # there's little or no real graph structure yet.
    ready = [n for n in nodes if in_degree[n] == 0]
    result: list[str] = []
    while ready:
        node = ready.pop(0)
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                ready.append(neighbor)

    if len(result) != len(nodes):
        raise ValueError("cannot compute a topological order: the graph has a cycle")
    return result


def ancestors(node: str, edges: list[Edge]) -> set[str]:
    """Every node that must come before `node`, transitively (multi-hop
    backward closure) — "what do I need to have completed to unlock this,
    including indirectly." Edges are (prerequisite, unlocks), i.e. (from,
    to) means `from` is a prerequisite of `to`."""
    incoming: dict[str, list[str]] = {}
    for src, dst in edges:
        incoming.setdefault(dst, []).append(src)

    seen: set[str] = set()
    stack = list(incoming.get(node, ()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(incoming.get(current, ()))
    return seen


def descendants(node: str, edges: list[Edge]) -> set[str]:
    """Every node that has `node` as a transitive prerequisite — "what does
    completing this unlock, including indirectly downstream.\""""
    outgoing: dict[str, list[str]] = {}
    for src, dst in edges:
        outgoing.setdefault(src, []).append(dst)

    seen: set[str] = set()
    stack = list(outgoing.get(node, ()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(outgoing.get(current, ()))
    return seen


def locked_courses(all_ids: set[str], edges: list[Edge], completed_ids: set[str]) -> set[str]:
    """A course is locked if it has at least one direct prerequisite (edges
    where it's the `to`) that isn't in completed_ids. A course with no
    prerequisite edges at all is never locked — same "nothing is ever
    locked by default" philosophy the language skill-tree already uses
    (see tests/test_api.py's `all(u["state"] in ("available", "mastered")
    for u in units)`), extended here only where a real prerequisite edge
    says otherwise."""
    prerequisites_of: dict[str, list[str]] = {}
    for src, dst in edges:
        prerequisites_of.setdefault(dst, []).append(src)

    return {
        course_id
        for course_id in all_ids
        if any(p not in completed_ids for p in prerequisites_of.get(course_id, ()))
    }
