"""Obligation graph (component 4.1): people, vendors, contracts, products, obligations and the
finance/HR objects that link them (purchase orders, approval limits, budget lines, headcount)."""
from __future__ import annotations

import networkx as nx

from .schema import Bundle


def dept_node(name: str) -> str:
    return f"dept:{name}"


def build_graph(bundle: Bundle) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    e = bundle.entities

    def link(u: str, v: str | None, rel: str, **attrs):
        if not v:
            return
        if v not in g:  # dangling reference: keep it visible, never crash
            g.add_node(v, type="missing", obj=None)
        g.add_edge(u, v, rel=rel, **attrs)

    for p in e.people:
        g.add_node(p.id, type="person", obj=p)
    for v in e.vendors:
        g.add_node(v.id, type="vendor", obj=v)
    for pr in e.products:
        g.add_node(pr.id, type="product", obj=pr)
    by_name = {pr.name: pr.id for pr in e.products}

    for c in e.contracts:
        g.add_node(c.id, type="contract", obj=c)
        link(c.id, c.vendor_id, "with_vendor")
        link(c.id, c.signed_by, "signed_by")
        link(c.id, c.legal_owner_id, "legal_owner")
        link(c.id, c.product_id, "for_product")

    for pr in e.products:
        if pr.approval:
            link(pr.id, pr.approval.accountable_senior_manager_id, "asm")
        link(pr.id, pr.owner_id, "product_owner")
        for f in pr.data_flows:
            link(pr.id, f.vendor_id, "data_flow", data_category=f.data_category)

    for s in e.staffing:
        link(s.person_id, by_name.get(s.product, s.product), "staffed_on", role=s.role, can_sell=s.can_sell)

    for al in e.approval_limits:
        g.add_node(al.id, type="approval_limit", obj=al)
        link(al.id, al.approver_id, "approver")
        link(al.id, al.delegate_id, "delegate")

    for po in e.purchase_orders:
        g.add_node(po.id, type="purchase_order", obj=po)
        link(po.id, po.vendor_id, "to_vendor")
        link(po.id, po.approver_id, "approver")
        link(po.id, by_name.get(po.product or ""), "for_product")

    for bl in e.budget_lines:
        g.add_node(bl.id, type="budget_line", obj=bl)
        link(bl.id, bl.owner_id, "budget_owner")
        link(bl.id, by_name.get(bl.product or ""), "for_product")

    for h in e.headcount:
        g.add_node(dept_node(h.department), type="department", obj=h)

    for r in bundle.records:
        g.add_node(r.id, type="obligation", obj=r)
        link(r.id, r.owner_id, "owned_by")
        link(r.id, r.product_id, "about_product")
        link(r.id, r.vendor_id, "about_vendor")
        link(r.id, r.contract_id, "about_contract")
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
