import pytest

from backend.learning_engine import graph_algorithms as ga


def test_has_cycle_detects_a_real_cycle():
    nodes = ["A", "B", "C"]
    edges = [("A", "B"), ("B", "C"), ("C", "A")]
    assert ga.has_cycle(nodes, edges) is True


def test_has_cycle_false_for_a_dag():
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
    assert ga.has_cycle(nodes, edges) is False


def test_has_cycle_false_for_no_edges():
    assert ga.has_cycle(["A", "B"], []) is False


def test_topological_order_on_a_diamond():
    # A -> B -> D, A -> C -> D
    nodes = ["A", "B", "C", "D"]
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
    order = ga.topological_order(nodes, edges)
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")
    assert set(order) == set(nodes)


def test_topological_order_preserves_original_order_with_no_edges():
    nodes = ["c0", "c1", "c2", "c3"]
    assert ga.topological_order(nodes, []) == nodes


def test_topological_order_raises_on_cycle():
    nodes = ["A", "B"]
    edges = [("A", "B"), ("B", "A")]
    with pytest.raises(ValueError):
        ga.topological_order(nodes, edges)


def test_ancestors_multi_hop():
    # A -> B -> C -> D
    edges = [("A", "B"), ("B", "C"), ("C", "D")]
    assert ga.ancestors("D", edges) == {"A", "B", "C"}
    assert ga.ancestors("A", edges) == set()


def test_descendants_multi_hop_is_what_completing_a_course_unlocks():
    edges = [("A", "B"), ("B", "C"), ("C", "D")]
    assert ga.descendants("A", edges) == {"B", "C", "D"}
    assert ga.descendants("D", edges) == set()


def test_ancestors_and_descendants_on_a_diamond():
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
    assert ga.ancestors("D", edges) == {"A", "B", "C"}
    assert ga.descendants("A", edges) == {"B", "C", "D"}


def test_locked_courses_with_partial_completion():
    all_ids = {"c0", "c1", "c2"}
    edges = [("c0", "c1"), ("c1", "c2")]
    # Nothing completed yet: c1/c2 are locked, c0 (no prerequisites) is not.
    assert ga.locked_courses(all_ids, edges, completed_ids=set()) == {"c1", "c2"}
    # c0 completed: c1 unlocks, c2 still locked (needs c1 too).
    assert ga.locked_courses(all_ids, edges, completed_ids={"c0"}) == {"c2"}
    # Both prerequisites completed: nothing locked.
    assert ga.locked_courses(all_ids, edges, completed_ids={"c0", "c1"}) == set()


def test_locked_courses_nothing_locked_with_no_prerequisite_edges():
    all_ids = {"c0", "c1", "c2"}
    assert ga.locked_courses(all_ids, [], completed_ids=set()) == set()
