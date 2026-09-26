"""
Unit tests for RepoGraph.find_cycles(), in_degree(), and out_degree()
defined in autopsy/graph.py.

All tests build a RepoGraph directly (bypassing build_graph / ingest) so
they remain isolated from the file-system and the ingest layer.
"""

import pytest
from autopsy.graph import RepoGraph
from autopsy.ingest import ModuleInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module(path: str) -> ModuleInfo:
    """Create a minimal ModuleInfo for use as a graph node."""
    return ModuleInfo(path=path, docstring=None)


def _graph(*paths: str) -> RepoGraph:
    """Create a RepoGraph whose node set is exactly *paths* with no edges."""
    modules = {p: _module(p) for p in paths}
    return RepoGraph(modules=modules)


# ---------------------------------------------------------------------------
# in_degree
# ---------------------------------------------------------------------------

class TestInDegree:
    def test_no_edges_returns_zero(self):
        g = _graph("a.py", "b.py", "c.py")
        assert g.in_degree("a.py") == 0
        assert g.in_degree("b.py") == 0

    def test_single_incoming_edge(self):
        g = _graph("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        assert g.in_degree("b.py") == 1

    def test_multiple_incoming_edges(self):
        g = _graph("a.py", "b.py", "c.py", "d.py")
        g.add_edge("a.py", "d.py")
        g.add_edge("b.py", "d.py")
        g.add_edge("c.py", "d.py")
        assert g.in_degree("d.py") == 3

    def test_source_node_has_zero_in_degree(self):
        g = _graph("a.py", "b.py", "c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "c.py")
        assert g.in_degree("a.py") == 0

    def test_node_not_in_any_edge_set(self):
        g = _graph("a.py", "b.py", "c.py")
        g.add_edge("a.py", "b.py")
        assert g.in_degree("c.py") == 0

    def test_duplicate_add_edge_counts_once(self):
        """add_edge stores destinations in a set, so duplicates are ignored."""
        g = _graph("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        assert g.in_degree("b.py") == 1

    def test_path_not_a_node_still_counted(self):
        """in_degree counts occurrences in edge-sets regardless of modules dict."""
        g = _graph("a.py")
        g.add_edge("a.py", "external.py")
        assert g.in_degree("external.py") == 1


# ---------------------------------------------------------------------------
# out_degree
# ---------------------------------------------------------------------------

class TestOutDegree:
    def test_no_edges_returns_zero(self):
        g = _graph("a.py", "b.py")
        assert g.out_degree("a.py") == 0

    def test_single_outgoing_edge(self):
        g = _graph("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        assert g.out_degree("a.py") == 1

    def test_multiple_outgoing_edges(self):
        g = _graph("a.py", "b.py", "c.py", "d.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "c.py")
        g.add_edge("a.py", "d.py")
        assert g.out_degree("a.py") == 3

    def test_sink_node_has_zero_out_degree(self):
        g = _graph("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        assert g.out_degree("b.py") == 0

    def test_duplicate_add_edge_counts_once(self):
        g = _graph("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        assert g.out_degree("a.py") == 1

    def test_node_with_no_outgoing_entry_in_edges(self):
        """Node present in modules but never used as a src should return 0."""
        g = _graph("a.py", "b.py")
        assert g.out_degree("b.py") == 0


# ---------------------------------------------------------------------------
# find_cycles
# ---------------------------------------------------------------------------

class TestFindCycles:
    def test_empty_graph_no_cycles(self):
        g = _graph()
        assert g.find_cycles() == []

    def test_single_node_no_self_loop_no_cycles(self):
        g = _graph("a.py")
        assert g.find_cycles() == []

    def test_self_loop_is_a_cycle(self):
        g = _graph("a.py")
        g.add_edge("a.py", "a.py")
        cycles = g.find_cycles()
        assert len(cycles) == 1
        assert cycles[0][0] == cycles[0][-1] == "a.py"

    def test_no_cycle_in_linear_chain(self):
        g = _graph("a.py", "b.py", "c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        assert g.find_cycles() == []

    def test_simple_two_node_cycle(self):
        g = _graph("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "a.py")
        cycles = g.find_cycles()
        assert len(cycles) == 1
        cycle = cycles[0]
        # First and last node are the same (the cycle closes back).
        assert cycle[0] == cycle[-1]
        assert set(cycle[:-1]) == {"a.py", "b.py"}

    def test_three_node_cycle(self):
        g = _graph("a.py", "b.py", "c.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        g.add_edge("c.py", "a.py")
        cycles = g.find_cycles()
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle[0] == cycle[-1]
        assert set(cycle[:-1]) == {"a.py", "b.py", "c.py"}

    def test_dag_with_diamond_no_cycle(self):
        """A diamond-shaped DAG must not produce a false positive."""
        g = _graph("a.py", "b.py", "c.py", "d.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "c.py")
        g.add_edge("b.py", "d.py")
        g.add_edge("c.py", "d.py")
        assert g.find_cycles() == []

    def test_two_independent_cycles(self):
        """Two disjoint cycles are both reported."""
        g = _graph("a.py", "b.py", "c.py", "d.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "a.py")
        g.add_edge("c.py", "d.py")
        g.add_edge("d.py", "c.py")
        cycles = g.find_cycles()
        assert len(cycles) == 2

    def test_isolated_node_alongside_cycle(self):
        """An isolated node must not prevent cycle detection elsewhere."""
        g = _graph("a.py", "b.py", "isolated.py")
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "a.py")
        cycles = g.find_cycles()
        assert len(cycles) == 1

    def test_cycle_nodes_appear_in_reported_path(self):
        """Every node of the cycle must appear in the reported path list."""
        nodes = ["x.py", "y.py", "z.py"]
        g = _graph(*nodes)
        g.add_edge("x.py", "y.py")
        g.add_edge("y.py", "z.py")
        g.add_edge("z.py", "x.py")
        cycles = g.find_cycles()
        assert len(cycles) == 1
        reported = set(cycles[0])
        for n in nodes:
            assert n in reported
