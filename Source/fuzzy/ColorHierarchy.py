"""Semantic composition of existing fuzzy colors, independent of geometry.

Base categories own atomic granules. Aggregate nodes refer to base categories,
other aggregate nodes or individual atomic granules. A node may have multiple
parents, but cycles are forbidden. No t-conorm is persisted: the runtime
operator applies at every level. Shared paths follow Java's union semantics
(a repeated leaf along different paths is evaluated once per occurrence).
"""
from collections import Counter, deque
from collections.abc import Mapping

from Source.fuzzy.GranularFuzzyColor import GranularFuzzyColor


class ColorHierarchy:
    def __init__(self, categories, nodes=None):
        self._base = {cat.label: tuple(p.label for p in cat.prototypes)
                      for cat in categories}
        self._granules = {g for values in self._base.values() for g in values}
        if nodes is None:
            nodes = {}
        if not isinstance(nodes, Mapping):
            raise ValueError("hierarchy must be a mapping of names to child references.")
        self._nodes = {}
        for name, children in nodes.items():
            if (not isinstance(name, str) or not name.strip() or name != name.strip()
                    or len(name) > 24 or name in self._base):
                raise ValueError(f"Invalid or conflicting hierarchy category '{name}'.")
            if not isinstance(children, (list, tuple)) or not children:
                raise ValueError(f"Hierarchy category '{name}' needs at least one child.")
            refs = []
            seen_refs = set()
            for ref in children:
                if not isinstance(ref, Mapping) or len(ref) != 1:
                    raise ValueError(f"Invalid child reference in '{name}'.")
                kind, target = next(iter(ref.items()))
                if kind not in ("category", "granule") or not isinstance(target, str):
                    raise ValueError(f"Invalid child reference in '{name}'.")
                if kind == "category" and target not in self._base and target not in nodes:
                    raise ValueError(f"Unknown category '{target}' in '{name}'.")
                if kind == "granule" and target not in self._granules:
                    raise ValueError(f"Unknown granule '{target}' in '{name}'.")
                pair = (kind, target)
                if pair in seen_refs:
                    raise ValueError(f"Duplicate child '{target}' in '{name}'.")
                refs.append(pair)
                seen_refs.add(pair)
            self._nodes[name] = tuple(refs)
        # Kahn traversal: each edge is processed once, even for long chains.
        dependents = {name: [] for name in self._nodes}
        pending = {}
        for name, children in self._nodes.items():
            dependencies = [child for kind, child in children
                            if kind == "category" and child in self._nodes]
            pending[name] = len(dependencies)
            for child in dependencies:
                dependents[child].append(name)
        ready = deque(name for name, count in pending.items() if not count)
        order = []
        while ready:
            name = ready.popleft()
            order.append(name)
            for parent in dependents[name]:
                pending[parent] -= 1
                if not pending[parent]:
                    ready.append(parent)
        if len(order) != len(self._nodes):
            raise ValueError("The hierarchy contains a cycle.")
        self._order = tuple(order)
        self._unique_cache = {}
        self._count_cache = {}

    def granule_occurrence_counts(self, label):
        """Exact multiplicities without allocating one entry per shared path."""
        if label not in self._base and label not in self._nodes:
            raise ValueError(f"Unknown category '{label}'.")
        if label not in self._count_cache:
            # Evaluate just the reachable subgraph, children before parents.
            reachable = set()
            stack = [label]
            while stack:
                name = stack.pop()
                if name in reachable or name in self._count_cache:
                    continue
                reachable.add(name)
                stack.extend(child for kind, child in self.children(name)
                             if kind == "category")
            for name in (*self._base, *self._order):
                if name not in reachable:
                    continue
                counts = Counter()
                for kind, child in self.children(name):
                    if kind == "granule":
                        counts[child] += 1
                    else:
                        counts.update(self._count_cache[child])
                self._count_cache[name] = counts
        return self._count_cache[label].copy()

    def __bool__(self):
        return bool(self._nodes)

    @property
    def labels(self):
        return tuple(self._nodes)

    def to_dict(self):
        return {name: [{kind: target} for kind, target in children]
                for name, children in self._nodes.items()}

    @property
    def category_labels(self):
        return tuple(self._base) + tuple(self._nodes)

    def children(self, label):
        """Typed immediate references, in model order."""
        if label in self._base:
            return tuple(("granule", g) for g in self._base[label])
        if label in self._nodes:
            return self._nodes[label]
        raise ValueError(f"Unknown category '{label}'.")

    def roots(self):
        referenced = {target for refs in self._nodes.values()
                      for kind, target in refs if kind == "category"}
        return tuple(label for label in self.category_labels if label not in referenced)

    def unique_granules(self, label):
        """Unique geometric leaves; unlike membership, repeated paths don't count."""
        if label not in self._base and label not in self._nodes:
            raise ValueError(f"Unknown category '{label}'.")
        if label not in self._unique_cache:
            visited, leaves = set(), {}
            stack = [("category", label)]
            while stack:
                kind, name = stack.pop()
                if kind == "granule":
                    leaves.setdefault(name, None)
                elif name not in visited:
                    visited.add(name)
                    stack.extend(reversed(self.children(name)))
            self._unique_cache[label] = tuple(leaves)
        return self._unique_cache[label]

    def categories_at_level(self, level):
        """A category frontier, retaining terminal categories on shorter branches.

        A DAG may expose a parent along a shorter path and its descendant along
        a longer path: suppress descendants of any selected ancestor. Direct
        granule references remain represented by their containing category.
        """
        if type(level) is not int or level < 0:
            raise ValueError("Hierarchy level must be a nonnegative integer.")
        current = self.roots()
        for _ in range(level):
            next_level = []
            for name in current:
                children = self.children(name)
                # Mixed nodes cannot be split into categories alone without
                # losing direct granule members; leave them intact here.
                if children and all(kind == "category" for kind, _ in children):
                    next_level.extend(target for _, target in children)
                else:
                    next_level.append(name)
            candidate = tuple(dict.fromkeys(next_level))
            if candidate == current:
                break
            current = candidate
        descendants = set()
        for name in current:
            stack = [target for kind, target in self.children(name) if kind == "category"]
            seen = set()
            while stack:
                child = stack.pop()
                if child in seen:
                    continue
                seen.add(child)
                stack.extend(target for kind, target in self.children(child) if kind == "category")
            descendants.update(seen)
        return tuple(name for name in current if name not in descendants)

    def granule_labels(self, label):
        """Leaf occurrences, in traversal order; may repeat across paths."""
        if label not in self._base and label not in self._nodes:
            raise ValueError(f"Unknown category '{label}'.")
        # This API promises an explicitly expanded tuple. Refuse impractical
        # allocations; membership and unique visual leaves have no such limit.
        if sum(self.granule_occurrence_counts(label).values()) > 100_000:
            raise ValueError("Too many repeated granule occurrences to expand. "
                             "Use occurrence counts or unique granules instead.")
        stack = [("category", label)]
        leaves = []
        while stack:
            kind, target = stack.pop()
            if kind == "granule":
                leaves.append(target)
            elif target in self._base:
                leaves.extend(self._base[target])
            else:
                stack.extend(reversed(self._nodes[target]))
        return tuple(leaves)

    def evaluate(self, atomic_degrees, tconorm="bounded_sum"):
        aggregate = GranularFuzzyColor.aggregate
        values = {label: aggregate((atomic_degrees[g] for g in granules), tconorm)
                  for label, granules in self._base.items()}
        for name in self._order:
            values[name] = aggregate((atomic_degrees[target] if kind == "granule"
                                      else values[target]
                                      for kind, target in self._nodes[name]), tconorm)
        return {name: values[name] for name in (*self._base, *self._nodes)}
