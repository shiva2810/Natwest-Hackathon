"""Obligation graph (component 4.1): people, vendors, contracts, products and obligations."""
from __future__ import annotations

import networkx as nx

from .schema import Bundle


def build_graph(bundle: Bundle) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    e = bundle.entities

    for p in e.people:
        g.add_node(p.id, type="person", obj=p)
    for v in e.vendors:
        g.add_node(v.id, type="vendor", obj=v)
    for pr in e.products:
        g.add_node(pr.id, type="product", obj=pr)
    for c in e.contracts:
        g.add_node(c.id, type="contract", obj=c)
        g.add_edge(c.id, c.vendor_id, rel="with_vendor")
        if c.signed_by:
            g.add_edge(c.id, c.signed_by, rel="signed_by")
        if c.product_id:
            g.add_edge(c.id, c.product_id, rel="for_product")

    for r in bundle.records:
        g.add_node(r.id, type="obligation", obj=r)
        for target, rel in (
            (r.owner_id, "owned_by"),
            (r.product_id, "about_product"),
            (r.vendor_id, "about_vendor"),
            (r.contract_id, "about_contract"),
        ):
            if target:
                if target not in g:  # dangling reference: keep it visible, never crash
                    g.add_node(target, type="missing", obj=None)
                g.add_edge(r.id, target, rel=rel)
    return g


def nodes_of(g: nx.MultiDiGraph, kind: str):
    return [(n, d["obj"]) for n, d in g.nodes(data=True) if d["type"] == kind]


def neighbours(g: nx.MultiDiGraph, node: str, rel: str | None = None, incoming: bool = False):
    edges = g.in_edges(node, data=True) if incoming else g.out_edges(node, data=True)
    for u, v, d in edges:
        if rel is None or d["rel"] == rel:
            other = u if incoming else v
            yield other, g.nodes[other]["obj"]


def affected_nodes(g: nx.MultiDiGraph, changed: set[str], hops: int = 2) -> set[str]:
    """Nodes within `hops` of a change, ignoring edge direction. Used for selective re-check."""
    und = g.to_undirected(as_view=True)
    out: set[str] = set()
    for n in changed:
        if n in g:
            out |= set(nx.single_source_shortest_path_length(und, n, cutoff=hops))
    return out
