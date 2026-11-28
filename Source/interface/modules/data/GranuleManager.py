
"""Granule editing and shared creation hierarchy management for PyFCS.

All edits are temporary until a new fuzzy color space is created. The class
keeps UI responsibilities small: PaletteBasedCreationManager owns the table
and category selection, while this adapter handles add / edit / remove.
"""

from collections import OrderedDict, Counter
import copy
import tkinter as tk
from tkinter import ttk, messagebox


import numpy as np

import Source.interface.modules.common.UtilsTools as UtilsTools


class GranuleManager:
    """Add, edit or remove positive granules for a palette category."""

    def __init__(self, palette, category_label):
        self.palette = palette
        self.category_label = category_label

    @property
    def granules(self):
        return self.palette.colors[self.category_label]["granules"]

    def _next_label(self):
        used = self.palette._used_granule_labels()
        number = len(self.granules) + 1
        while True:
            proposal = self.palette._auto_granule_label(self.category_label, number - 1)
            if proposal not in used:
                return proposal
            number += 1

    def _check(self, label, lab, exclude_index=None):
        """Return a recoverable validation result for a prospective site.

        A name-only edit of an imported site must not be blocked because that
        site already shares its LAB with a different imported category.
        """
        same_category = [
            (category, item["label"], item["lab"])
            for category, data in self.palette.colors.items()
            if category == self.category_label
            for index, item in enumerate(data.get("granules", []))
            if index != exclude_index
        ]
        cleaned, point, error = UtilsTools.check_granule_site(
            label, lab, same_category,
        )
        if error:
            return cleaned, point, error

        others = [
            (category, item["label"], item["lab"])
            for category, data in self.palette.colors.items()
            if category != self.category_label
            for item in data.get("granules", [])
        ]
        if any(other_name == cleaned for _, other_name, _ in others):
            return None, None, f"Granule name '{cleaned}' is already in use."

        # Preserve a pre-existing imported overlap on a label-only edit.
        if exclude_index is not None and 0 <= exclude_index < len(self.granules):
            old_lab = tuple(float(v) for v in self.granules[exclude_index]["lab"])
            if point == old_lab:
                return cleaned, point, None

        _, _, error = UtilsTools.check_granule_site(cleaned, point, others)
        if error:
            return None, None, error
        return cleaned, point, None

    def _validate(self, label, lab, exclude_index=None):
        """Compatibility validator for non-UI code; UI uses ``_check``."""
        name, point, message = self._check(label, lab, exclude_index)
        if message:
            raise ValueError(message)
        return name, point

    def add(self):
        """Create a granule directly in the shared precise Color Picker."""
        suggested = self._next_label()

        def on_submit(name, lab, _rgb, _hex, _dialog, status_var):
            try:
                label, point, error = self._check(name, lab)
                if error:
                    status_var.set(error)
                    return False
                entries = [dict(item) for item in self.granules]
                entries.append({"label": label, "lab": point,
                                "native_rgb": UtilsTools.matching_native_rgb(point, _rgb),
                                "enabled": True})
                ok, error = self.palette._set_category_granules(self.category_label, entries)
                if not ok:
                    status_var.set(error)
                    return False
            except (ValueError, TypeError) as exc:
                status_var.set(str(exc))
                return False
            return True

        return self.palette.app._open_square_color_picker(
            parent=self.palette.win,
            title=f"Add granule — {self.category_label}",
            granule_name=suggested,
            submit_text="Add granule",
            on_granule_submit=on_submit,
        )

    def edit(self, index):
        """Edit label and exact LAB directly in the shared Color Picker."""
        if not 0 <= index < len(self.granules):
            return
        item = dict(self.granules[index])
        display_label = self.palette._granule_display_label(
            self.category_label, item, index)

        def on_submit(name, lab, _rgb, _hex, _dialog, status_var):
            try:
                label, point, error = self._check(name, lab, exclude_index=index)
                if error:
                    status_var.set(error)
                    return False
                entries = [dict(g) for g in self.granules]
                entries[index] = {
                    "label": label,
                    "lab": point,
                    "native_rgb": (item.get("native_rgb") if all(abs(a-b) <= 1e-10 for a, b in zip(point, item["lab"]))
                                   else UtilsTools.matching_native_rgb(point, _rgb)),
                    "enabled": item.get("enabled", True),
                }
                ok, error = self.palette._set_category_granules(self.category_label, entries)
                if not ok:
                    status_var.set(error)
                    return False
            except (ValueError, TypeError) as exc:
                status_var.set(str(exc))
                return False
            return True

        return self.palette.app._open_square_color_picker(
            parent=self.palette.win,
            title=f"Edit granule — {self.category_label}",
            granule_name=display_label,
            initial_lab=item["lab"],
            submit_text="Save changes",
            on_granule_submit=on_submit,
        )

    def rename(self, index, requested):
        """Rename an existing site in place; return the name displayed in Data."""
        if not 0 <= index < len(self.granules):
            raise ValueError("Granule no longer exists.")
        current = self.granules[index]
        shown = self.palette._granule_display_label(self.category_label, current, index)
        requested = str(requested or "").strip()
        if not requested:
            self.palette.app.custom_warning(
                "Invalid Granule Name", "Granule name cannot be empty.",
                parent=self.palette.win)
            return shown
        if requested == shown:
            return shown
        label, _point, error = self._check(requested, current["lab"], exclude_index=index)
        if error:
            # Preserve the actual label; give the table a recoverable warning.
            self.palette.app.custom_warning(
                "Invalid Granule Name", error, parent=self.palette.win)
            return shown
        current["label"] = label
        self.palette.colors[self.category_label].pop("_search_key_cache", None)
        return label

    def remove(self, index):
        if not 0 <= index < len(self.granules):
            return
        if len(self.granules) <= 1:
            self.palette.app.custom_warning(
                "Cannot Remove Granule",
                "Every category must contain at least one granule.",
                parent=self.palette.win,
            )
            return
        granule = self.granules[index]
        if not messagebox.askyesno(
            "Remove Granule",
            f"Remove '{granule['label']}' from '{self.category_label}'?\n"
            "This only changes the temporary palette.",
            parent=self.palette.win,
        ):
            return
        entries = [dict(g) for i, g in enumerate(self.granules) if i != index]
        ok, error = self.palette._set_category_granules(self.category_label, entries)
        if not ok:
            self.palette.app.custom_warning(
                "Cannot Remove Granule", error, parent=self.palette.win)


# Shared inline hierarchy management for Palette Based and Image Based.
# Keep the geometry construction deferred until the final configuration.
def importable_tree(space):
    """Creators use single-owner trees, not arbitrary imported DAGs."""
    nodes = getattr(space, "hierarchy", {}) or {}
    parents = Counter()
    for children in nodes.values():
        for ref in children:
            if set(ref) != {"category"}:
                return False
            parents[ref["category"]] += 1
    return all(count == 1 for count in parents.values())


def confirm_tree_import(owner, space):
    if importable_tree(space):
        return True
    return messagebox.askyesno(
        "Import base colors",
        "This source shares components across branches. New spaces use a tree "
        "with one owner per component. Import only its base colors?",
        parent=owner.win,
    )


def source_colors_with_native_rgb(loaded):
    """Retain original RGB rather than recovering it from a display preview."""
    space = loaded.get("fuzzy_color_space")
    colors = copy.deepcopy(loaded.get("color_data", {}))
    mode = loaded.get("source_color_space") or getattr(space, "color_space", "LAB")
    if str(mode).upper() != "RGB":
        return colors
    if space is None:
        for row in colors.values():
            if isinstance(row, dict) and row.get("Color") is not None:
                row["native_rgb"] = copy.deepcopy(row["Color"])
        return colors
    if getattr(space, "is_granular", False):
        sites = {cat.label: {g.label: g.positive for g in cat.prototypes}
                 for cat in space.categories}
    else:
        sites = {g.label: {g.label: g.positive} for g in space.prototypes}
    for cat, row in colors.items():
        if cat not in sites or not isinstance(row, dict):
            continue
        row["native_rgb"] = copy.deepcopy(next(iter(sites[cat].values())))
        for g in row.get("granules", ()):
            if g.get("label") in sites[cat]:
                g["native_rgb"] = copy.deepcopy(sites[cat][g["label"]])
    return colors


def remember_import_tree(owner, space, mapping):
    nodes = getattr(space, "hierarchy", {}) or {}
    if not nodes or not importable_tree(space):
        return
    batches = getattr(owner, "_imported_trees", None)
    if batches is None:
        batches = owner._imported_trees = []
    batch = len(batches)
    batches.append(copy.deepcopy(nodes))
    for original, current in mapping.items():
        if current in owner.colors:
            owner.colors[current]["_tree_origin"] = (batch, original)


def selected_draft(owner):
    """Collect selected actual records, not a dict that hides duplicate labels."""
    categories = OrderedDict()
    for category, data in owner.colors.items():
        check = owner.color_checks.get(category)
        if not check or not check["var"].get():
            continue
        items = []
        for granule in data.get("granules", ()):
            if not granule.get("enabled", True):
                continue
            items.append({"label": granule["label"],
                          "lab": copy.deepcopy(granule["lab"]),
                          "native_rgb": copy.deepcopy(granule.get("native_rgb")),
                          "original_label": None})
        if items:
            categories[category] = {"source": None, "granules": items}
    return categories


def selected_hierarchy(owner, categories):
    """Prune unselected branches and remap imported names after local renames."""
    result = OrderedDict()
    used = set(categories)
    for batch, nodes in enumerate(getattr(owner, "_imported_trees", ())):
        names = {data["_tree_origin"][1]: current
                 for current, data in owner.colors.items()
                 if current in categories and data.get("_tree_origin", (-1,))[0] == batch}
        pending = dict(nodes)
        while pending:
            ready = [name for name, refs in pending.items()
                     if all(ref["category"] not in pending for ref in refs)]
            if not ready:
                raise ValueError("Imported hierarchy contains a cycle.")
            for original in ready:
                refs = [{"category": names[ref["category"]]}
                        for ref in pending.pop(original) if ref["category"] in names]
                if not refs:
                    continue
                label = UtilsTools.unique_import_label(original, used, 24)
                used.add(label)
                names[original] = label
                result[label] = refs
    return result


def creation_request(categories, hierarchy, options):
    """Validate final draft, choose legacy atomic or granular writer options."""
    from Source.interface.modules.data.DataManager import validate_draft, draft_graph
    problem = validate_draft(categories)
    if problem:
        raise ValueError(problem)
    draft_graph(categories, hierarchy)
    selected = {cat: {g["label"]: np.asarray(g["lab"], dtype=float)
                      for g in data["granules"]} for cat, data in categories.items()}
    native = {cat: {g["label"]: g["native_rgb"] for g in data["granules"]
                    if g.get("native_rgb") is not None}
              for cat, data in categories.items()}
    representatives = {cat: next(iter(sites.values())) for cat, sites in selected.items()}
    prepared = UtilsTools.prepare_granular_creation_options(selected, options, native_rgb=native)
    granular = bool(hierarchy) or any(len(g) != 1 or next(iter(g)) != cat
                                     for cat, g in selected.items())
    if granular:
        prepared["hierarchy"] = copy.deepcopy(hierarchy)
    else:
        # Keep the historical atomic membership semantics and string negative
        # references; the granular helper was used only for native validation.
        native_sites = prepared.pop("_granular_categories")
        prepared = dict(options)
        if prepared["color_space"] == "RGB":
            prepared["model_points"] = {cat: sites[cat] for cat, sites in native_sites.items()}
    return representatives, prepared


class InlineCreationTree:
    """Semantic tree in the existing creator's scrollable color list.

    Leaves remain the creator's original rows and records (including selection,
    image provenance and native coordinates). Only structural edits rebuild rows.
    The two creators share this controller and the Edit FCS component dialogs.
    """
    def __init__(self, owner):
        self.owner = owner
        self.app, self.win = owner.app, owner.win
        self.hierarchy = OrderedDict()
        self.categories = OrderedDict()
        self.expanded = set()
        self.group_rows = {}
        self.group_vars = {}
        self._batch_selection = False
        self.geometry_locked = False
        self.model_var = tk.StringVar(master=self.win, value='LAB')
        self.file_var = tk.StringVar(master=self.win, value='')
        self.search_var = owner.search_var

    def _warning(self, message, title='Invalid Modification'):
        self.app.custom_warning(title, message, parent=self.win)

    def _geometry_allowed(self):
        return not getattr(self.owner, '_detection_running', False)

    def _ready(self):
        if not self._geometry_allowed() or self.app._has_any_active_job():
            self._warning('Finish the active process first.')
            return False
        flush = getattr(self.owner, '_commit_pending_granule_names', lambda: True)
        return bool(flush() and self.commit_pending_group_names() and self.owner._commit_pending_color_names())

    def _snapshot(self):
        result = OrderedDict()
        for name, data in self.owner.colors.items():
            active = bool(self.owner.color_checks[name]['var'].get())
            items = copy.deepcopy(data['granules'])
            for item in items:
                item['enabled'] = active and bool(item.get('enabled', True))
            result[name] = {'source': name, 'granules': items}
        return result

    def graph(self):
        from Source.interface.modules.data.DataManager import draft_graph
        return draft_graph(self.owner.colors, self.hierarchy)

    def ancestors(self, name):
        parents = {r['category']: group for group, refs in self.hierarchy.items() for r in refs}
        result = []
        while name in parents:
            name = parents[name]
            result.append(name)
        return result

    def ancestor_match(self, name, tokens):
        return any(all(t in p.casefold() for t in tokens) for p in self.ancestors(name))

    def leaf_names(self, name):
        stack, result = [name], []
        while stack:
            node = stack.pop()
            if node in self.hierarchy:
                stack.extend(reversed([r['category'] for r in self.hierarchy[node]]))
            elif node in self.owner.colors:
                result.append(node)
        return result

    def allow_remove(self, names):
        removed = set(names)
        for parent, refs in self.hierarchy.items():
            if refs and all(r['category'] in removed for r in refs):
                self._warning(f"'{parent}' would be empty. Delete the group first, or keep a child.")
                return False
        return True

    def drop_missing(self):
        # Explicit base deletions/moves have already been checked by allow_remove.
        available = set(self.owner.colors) | set(self.hierarchy)
        for parent, refs in self.hierarchy.items():
            self.hierarchy[parent] = [r for r in refs if r['category'] in available]
        # Defensive recovery for an external change to the creator's records.
        from Source.interface.modules.data.DataManager import prune_empty_groups
        prune_empty_groups(self.hierarchy)

    def rename_leaf(self, old, new):
        if old == new:
            return
        from Source.interface.modules.data.DataManager import remap_references
        self.hierarchy = remap_references(self.hierarchy, {old: new})

    def add_import(self, space, mapping):
        if not importable_tree(space):
            return
        nodes = getattr(space, 'hierarchy', {}) or {}
        names = {old: new for old, new in mapping.items() if new in self.owner.colors}
        pending = dict(nodes)
        used = set(self.owner.colors) | set(self.hierarchy)
        result = OrderedDict()
        while pending:
            ready = [n for n, refs in pending.items() if all(r['category'] not in pending for r in refs)]
            if not ready:
                self._warning('Imported hierarchy contains a cycle. Only base colors were imported.')
                return
            for name in ready:
                refs = [{'category': names[r['category']]} for r in pending.pop(name) if r['category'] in names]
                if refs:
                    label = UtilsTools.unique_import_label(name, used, 24)
                    used.add(label)
                    names[name] = label
                    result[label] = refs
        if result:
            self.hierarchy.update(result)
            self.expanded.update(result)
            self.refresh()

    def _commit_draft(self, categories, nodes):
        from Source.interface.modules.data.DataManager import draft_graph
        draft_graph(categories, nodes)
        old = self.owner.colors
        old_checks = self.owner.color_checks
        new, checks = OrderedDict(), OrderedDict()
        dirty = set(getattr(self, '_dirty_leaf_rows', ()))
        for name, draft in categories.items():
            source = draft.get('source')
            items = copy.deepcopy(draft['granules'])
            # Keep the actual data object (Palette callbacks capture it) and
            # Tk variable for unchanged leaves, including unchecked granules.
            previous = old.get(name) if source == name else None
            if previous is not None:
                enabled = bool(old_checks[name]['var'].get())
                before = previous['granules']
                def equal(a, b):
                    keys = (set(a) | set(b)) - {'enabled'}
                    return (all(k in a and k in b and np.array_equal(a[k], b[k]) for k in keys)
                            and bool(enabled and a.get('enabled', True)) == bool(b.get('enabled', True)))
                if len(before) == len(items) and all(equal(a,b) for a,b in zip(before,items)):
                    new[name], checks[name] = previous, old_checks[name]
                    continue
            dirty.add(name)
            data = copy.deepcopy(old.get(source, {}))
            data.pop('_search_key_cache', None)
            if not items:
                raise ValueError('A category must contain a granule.')
            active = any(g.get('enabled', True) for g in items)
            first = next((g for g in items if g.get('enabled', True)), items[0])
            lab = tuple(float(x) for x in first['lab'])
            rgb = tuple(UtilsTools.safe_rgb_tuple(UtilsTools.lab_to_rgb(lab)))
            data.update(granules=items, lab=lab, rgb=rgb, hex=UtilsTools.rgb_to_hex(rgb).upper())
            if source is None:
                data['custom'] = True
            new[name] = data
            checks[name] = dict(var=tk.BooleanVar(master=self.win, value=active), lab=lab, rgb=rgb,
                                native_rgb=first.get('native_rgb'))
        # Image Based hides multi-granule Move until another destination exists.
        if getattr(self.owner, '_filter_cached_rows', False) and len(old) == 1 and len(new) > 1:
            previous = next(iter(old))
            if previous in new and previous in self.owner._expanded_categories and len(new[previous]['granules']) > 1:
                dirty.add(previous)
        self._dirty_leaf_rows = dirty | (set(old) - set(new))
        self.owner.colors, self.owner.color_checks = new, checks
        self.hierarchy = OrderedDict(nodes)
        self.categories = categories
        self.owner._expanded_categories.intersection_update(new)
        self.expanded.intersection_update(nodes)

    def refresh(self):
        """Reconcile structural edits without rebuilding unrelated leaf rows."""
        owner = self.owner
        if not hasattr(owner, 'colors_inner') or not owner.colors_inner.winfo_exists():
            return
        top = owner.colors_canvas.yview()[0]
        cached = getattr(owner, '_filter_cached_rows', False)
        wanted = [n for n in owner.colors if cached or owner._matches_search(n)]
        dirty = set(getattr(self, '_dirty_leaf_rows', ()))
        self._dirty_leaf_rows = set()
        # Palette search is debounced; the current query is already applied
        # here, so do not let an old queued refresh rebuild all the rows.
        pending = getattr(owner, '_search_refresh_after_id', None)
        if pending is not None:
            owner.win.after_cancel(pending)
            owner._search_refresh_after_id = None
        if not wanted:
            owner._refresh_color_list()
            return
        wanted_set = set(wanted)
        removed = set()
        for name, rec in list(owner._row_details.items()):
            if name in dirty or name not in wanted_set or not rec['wrapper'].winfo_exists():
                removed.add(name)
                owner._row_details.pop(name, None)
                if not cached:
                    owner._row_widgets.pop(name, None)
                if rec['wrapper'].winfo_exists():
                    rec['wrapper'].destroy()
        owner._name_editors = [(n,v) for n,v in owner._name_editors if n not in removed]
        # Clear an old empty-state hint, not the existing rows or group widgets.
        for widget in owner.colors_inner.winfo_children():
            if isinstance(widget, tk.Label) and widget is not getattr(owner, '_no_color_matches', None):
                widget.destroy()
        for index, name in enumerate(wanted):
            if name not in owner._row_details:
                if cached:
                    owner._create_color_row(name)
                else:
                    owner._create_color_row(name, index)
        self.layout()
        if cached:
            owner._update_selected_count()
            owner._refresh_sample_destinations()
        else:
            owner._update_counts(visible=len(wanted))
        owner.colors_canvas.configure(scrollregion=owner.colors_canvas.bbox('all'))
        owner.colors_canvas.yview_moveto(top)

    def _choose_members(self, *args, **kwargs):
        from Source.interface.modules.data.DataManager import ModifyFCSDialog
        return ModifyFCSDialog._choose_members(self, *args, **kwargs)

    def add_group(self, parent=None):
        if not self._ready():
            return
        from Source.interface.modules.data.DataManager import group_tree_draft
        self.categories = self._snapshot()
        graph = self.graph()
        if parent in self.categories:
            choices = list(graph.children(parent))
        elif parent in self.hierarchy:
            choices = list(graph.children(parent))
        elif parent is None:
            choices = [('category', n) for n in graph.roots()]
        else:
            return
        def commit(name, refs, remaining_name=None):
            candidate, nodes = group_tree_draft(self.categories, self.hierarchy, name, refs, parent,
                                                remaining_name=remaining_name, validate_sites=False)
            self._commit_draft(candidate, nodes)
            self.expanded.add(name)
            if parent:
                self.expanded.add(parent)
        self._choose_members('Create color group' if parent is None else 'Group existing components',
                             choices, commit, group=True,
                             description='Move existing components into a group.',
                             accept_text='Create group',
                             remaining_parent=parent if parent in self.categories else None)

    def choose_subcategory(self, parent):
        if not self._ready():
            return
        from Source.interface.modules.data.DataManager import ModifyFCSDialog
        self.categories = self._snapshot()
        ModifyFCSDialog._choose_subcategory_action(self, parent)

    def add_category(self, parent=None):
        if not self._ready():
            return
        from Source.interface.modules.data.DataManager import _CategoryHost
        self.categories = self._snapshot()
        host = _CategoryHost(self)
        host.parent_category = parent
        host.original_child_parent = parent if parent in self.categories else None
        UtilsTools.CustomCategoryDialog(host)

    def _add_subcategory(self, parent):
        self.add_category(parent)

    def _insert_category(self, name, granules, parent=None, *, original_child_name=None):
        from Source.interface.modules.data.DataManager import prepare_parent_draft, draft_graph
        try:
            candidate, nodes = self._snapshot(), copy.deepcopy(self.hierarchy)
            name, problem = UtilsTools.check_label_name(name, max_length=UtilsTools.MAX_CATEGORY_NAME_CHARS, kind='Category')
            if problem or name in candidate or name in nodes:
                self._warning(problem or 'Choose a unique category name.')
                return False
            if parent is not None:
                candidate, nodes, _ = prepare_parent_draft(candidate, nodes, parent,
                                                            reserved=(name,), child_name=original_child_name)
            occupied = [(cat, g['label'], g['lab']) for cat,data in candidate.items()
                        for g in data['granules']]
            validated = []
            for g in granules:
                label, point, problem = UtilsTools.check_granule_site(g.get('label'), g.get('lab'), occupied)
                if problem:
                    self._warning(problem); return False
                occupied.append((name, label, point))
                validated.append({**g, 'label': label, 'lab': point})
            if not validated:
                self._warning('Add at least one granule.'); return False
            candidate[name] = {'source': None, 'granules': validated}
            if parent is not None:
                nodes[parent].append({'category': name})
            draft_graph(candidate, nodes)
            self._commit_draft(candidate, nodes)
        except (ValueError, KeyError, TypeError) as exc:
            self._warning(str(exc)); return False
        if parent:
            self.expanded.add(parent)
        self.owner._expanded_categories.add(name)
        if self.search_var.get():
            self.search_var.set('')
        self.refresh()
        return True

    def can_move(self, name):
        ancestors = self.ancestors(name)
        current = ancestors[0] if ancestors else None
        if current:
            return len(self.hierarchy[current]) > 1
        return any(n != name and name not in self.ancestors(n) for n in self.hierarchy)

    def move_category(self, name):
        if not self._ready():
            return
        self.categories = self._snapshot()
        ancestors = self.ancestors(name)
        current = ancestors[0] if ancestors else None
        if current and len(self.hierarchy[current]) == 1:
            self._warning(f"'{current}' would be empty. Delete the group first, or keep a child.")
            return
        choices = [('root', 'Top level')] if current else []
        choices += [('category', n) for n in self.hierarchy
                    if n != name and n != current and name not in self.ancestors(n)]
        def commit(refs):
            dest = refs[0].get('category')
            nodes = copy.deepcopy(self.hierarchy)
            if current:
                nodes[current].remove({'category': name})
            if dest:
                nodes[dest].append({'category': name})
            from Source.interface.modules.data.DataManager import draft_graph
            draft_graph(self.categories, nodes)
            self.hierarchy = nodes
            if dest:
                self.expanded.add(dest)
        self._choose_members('Move category', choices, commit, single=True,
                             description=f'Choose a new parent for {name}.', accept_text='Move')

    def delete_group(self, name):
        if not self._ready() or name not in self.hierarchy:
            return
        if not messagebox.askyesno('Delete group', f"Delete '{name}' and keep its children at the parent level?", parent=self.win):
            return
        refs = self.hierarchy.pop(name)
        for parent, children in self.hierarchy.items():
            if {'category': name} in children:
                i = children.index({'category': name})
                children[i:i+1] = refs
                break
        self.expanded.discard(name)
        self.refresh()

    def commit_group_name(self, name, variable):
        """Rename the semantic node, not its descendants or their prototypes."""
        if name not in self.hierarchy:
            return True
        if variable.get() == name:
            return True
        new, error = UtilsTools.check_label_name(variable.get(), max_length=UtilsTools.MAX_COLOR_NAME_CHARS, kind='Group')
        if new == name and not error:
            return True
        # Reset before displaying a modal warning or destroying a focused row.
        variable.set(name)
        if not self._geometry_allowed() or self.app._has_any_active_job():
            self._warning('Finish the active process first.')
            return False
        if error or new in set(self.owner.colors) | set(self.hierarchy):
            self._warning(error or f"Category '{new}' already exists.")
            return False
        from Source.interface.modules.data.DataManager import remap_references
        self.hierarchy = remap_references(self.hierarchy, {name: new})
        if name in self.expanded:
            self.expanded.remove(name)
            self.expanded.add(new)
        # Only the renamed group has stale callbacks. Filtering may also
        # change which leaf rows are visible, so use the existing filter path.
        if self.search_var.get().strip() and not getattr(self.owner, '_filter_cached_rows', False):
            self.refresh()
        else:
            self.layout()
        return True

    def commit_pending_group_names(self):
        for name, row in list(self.group_rows.items()):
            variable = row.get('name_var')
            if variable is not None and name in self.hierarchy:
                if not self.commit_group_name(name, variable):
                    return False
        return True

    def rename_group(self, name):
        # Compatibility for the older fallback row renderer.
        if not self._ready() or name not in self.hierarchy:
            return
        from tkinter import simpledialog
        proposed = simpledialog.askstring('Rename group', 'Group name', initialvalue=name, parent=self.win)
        if proposed is not None:
            self.commit_group_name(name, tk.StringVar(master=self.win, value=proposed))

    def selected_nodes(self, categories):
        # A deselected branch is omitted from the output, but never from the workspace.
        kept = set(categories)
        result = OrderedDict()
        pending = dict(self.hierarchy)
        while pending:
            ready = [label for label,refs in pending.items() if all(r['category'] not in pending for r in refs)]
            if not ready:
                raise ValueError('Hierarchy contains a cycle.')
            for label in ready:
                refs = [copy.deepcopy(ref) for ref in pending.pop(label) if ref['category'] in kept]
                if refs:
                    result[label] = refs; kept.add(label)
        return result

    def configure(self):
        if not self._ready():
            return
        from Source.interface.modules.data.DataManager import validate_draft, draft_graph
        categories = selected_draft(self.owner)
        problem = validate_draft(categories)
        if problem:
            self._warning(problem, 'Invalid Selection'); return
        try:
            nodes = self.selected_nodes(categories)
            draft_graph(categories, nodes)
            reps = {name: np.asarray(d['granules'][0]['lab'], dtype=float) for name,d in categories.items()}
            def accept(name, options):
                representatives, prepared = creation_request(categories, nodes, options)
                self.file_var.set(name); self.model_var.set(options['color_space'])
                # No secondary editor: the existing save pipeline closes the
                # creator on success; on failure its original tree is intact.
                return bool(self.app.save_cs(name, representatives, options=prepared))
            selected_sites={k:{g['label']:g['lab'] for g in d['granules']} for k,d in categories.items()}
            native_sites={k:{g['label']:g['native_rgb'] for g in d['granules'] if g.get('native_rgb') is not None} for k,d in categories.items()}
            signature=repr((selected_sites,native_sites))
            cached=getattr(self,'_negative_creation_cache',None)
            dialog = UtilsTools.FCSCreationDialog(self.win, reps, on_accept=accept,
                         warn=self.app.custom_warning, initial_color_space=self.model_var.get(),
                         initial_name=self.file_var.get(),selected_categories=selected_sites,native_rgb=native_sites,
                         initial_negatives=cached[1] if cached and cached[0]==signature else None,app=self.app,
                         initial_negative_names=cached[5] if cached and cached[0]==signature and len(cached)>5 else None)
            if cached and cached[0]==signature:
                dialog.disjoint_var.set(cached[2]);dialog.covering_var.set(cached[3]);dialog.negative_mode.set(cached[4]);dialog._update_typology()
            dialog.transient(self.win); dialog.grab_set()
            # Keep custom data if the asynchronous save fails; the creator
            # remains open and retrying configuration restores the draft.
            dialog.wait_window()
            if dialog.result:
                self._negative_creation_cache=(signature,copy.deepcopy(dialog._custom_sets),dialog.disjoint_var.get(),dialog.covering_var.get(),dialog.negative_mode.get(),copy.deepcopy(dialog._custom_names))
        except (ValueError, TypeError, KeyError, RuntimeError, tk.TclError) as exc:
            self._warning(str(exc), 'Cannot Create Color Space')

    def toggle_group(self, name):
        if name in self.expanded:
            self.expanded.remove(name)
        else:
            self.expanded.add(name)
        self.layout()

    def _group_selection(self, name):
        active = self.group_vars[name].get()
        self._batch_selection = True
        try:
            for leaf in self.leaf_names(name):
                self.owner.color_checks[leaf]['var'].set(active)
                toggle = getattr(self.owner, '_on_category_toggle', None) or self.owner._category_toggle
                toggle(leaf)
        finally:
            self._batch_selection = False
        update = getattr(self.owner, '_update_selection_counter', None) or self.owner._update_selected_count
        update()

    def update_checks(self):
        if self._batch_selection:
            return
        for name, variable in self.group_vars.items():
            leaves = self.leaf_names(name)
            total = sum(len(self.owner.colors[n]['granules']) for n in leaves)
            active = sum(sum(g.get('enabled', True) for g in self.owner.colors[n]['granules'])
                         for n in leaves if self.owner.color_checks[n]['var'].get())
            variable.set(1 if total and active == total else (-1 if active else 0))
            info = self.group_rows.get(name)
            if info and info['row'].winfo_exists():
                info['count'].configure(text=f'Group · {active}/{total}')
                if leaves:
                    info['swatch'].configure(bg=self.owner.colors[leaves[0]]['hex'])

    def _group_row(self, name):
        owner = self.owner
        bg = owner.PANEL
        row = tk.Frame(owner.colors_inner, bg=bg, highlightthickness=0)
        top = tk.Frame(row, bg=bg); top.pack(fill='x', pady=3)
        var = tk.IntVar(master=self.win, value=0); self.group_vars[name] = var
        tk.Checkbutton(top, variable=var, onvalue=1, offvalue=0, tristatevalue=-1,
                       bg=bg, activebackground=bg, bd=0,
                       command=lambda: self._group_selection(name)).pack(side='left')
        arrow = tk.Button(top, text='▾', command=lambda: self.toggle_group(name),
                          fg=UtilsTools.UI_ACCENT, bg=bg, relief='flat', bd=0, cursor='hand2')
        arrow.pack(side='left')
        leaves = self.leaf_names(name)
        swatch = tk.Label(top, bg=owner.colors[leaves[0]]['hex'] if leaves else bg, width=2, relief='solid', bd=1)
        swatch.pack(side='left', padx=(1,5))
        tk.Label(top, text=name, font=owner.FONT_BOLD, bg=bg, fg=owner.TEXT).pack(side='left')
        for label, command, color in [('Delete',lambda:self.delete_group(name),'#A43D3D'),
                                       ('Move',lambda:self.move_category(name),UtilsTools.UI_ACCENT),
                                       ('Rename',lambda:self.rename_group(name),UtilsTools.UI_ACCENT)]:
            if label == 'Move' and not self.can_move(name):
                continue
            tk.Button(top,text=label,command=command,font=owner.FONT_SMALL,fg=color,bg=bg,
                      relief='flat',bd=0,cursor='hand2').pack(side='right',padx=3)
        count = tk.Label(top, font=owner.FONT_SMALL, fg=UtilsTools.UI_ACCENT, bg=bg); count.pack(side='right',padx=4)
        action = tk.Button(row, text='+ Add subcategory', command=lambda:self.choose_subcategory(name),
                           fg=UtilsTools.UI_ACCENT,bg=bg,font=owner.FONT_SMALL,relief='flat',bd=0,cursor='hand2')
        record = dict(row=row, arrow=arrow, count=count, action=action, swatch=swatch)
        self.group_rows[name] = record
        return record

    def layout(self):
        """Repack existing widgets in depth-first order; no leaf rebuild on expand."""
        owner = self.owner
        custom_layout = getattr(owner, '_layout_inline_tree', None)
        if custom_layout is not None:
            return custom_layout()
        if not hasattr(owner, 'colors_inner') or not owner.colors_inner.winfo_exists():
            return
        self.drop_missing()
        for name, record in list(self.group_rows.items()):
            if name not in self.hierarchy or not record['row'].winfo_exists():
                if record['row'].winfo_exists(): record['row'].destroy()
                self.group_rows.pop(name); self.group_vars.pop(name, None)
        leaf_rows = {name: rec['wrapper'] for name,rec in owner._row_details.items()
                     if name in owner.colors and rec['wrapper'].winfo_exists()}
        # Existing source rows retain their selection controls and granule widgets.
        for name, wrapper in leaf_rows.items():
            rec = owner._row_details[name]
            action = rec.get('_tree_actions')
            if name not in owner._expanded_categories:
                if action is not None and action.winfo_exists():
                    action.pack_forget()
                continue
            if action is None or not action.winfo_exists():
                action = tk.Frame(wrapper, bg=owner.CARD); rec['_tree_actions'] = action
                tk.Button(action, text='+ Add subcategory', command=lambda n=name:self.choose_subcategory(n),
                          fg=UtilsTools.UI_ACCENT, bg=owner.CARD, font=owner.FONT_SMALL, relief='flat',bd=0,cursor='hand2').pack(side='left')
                move = tk.Button(action, text='Move category', command=lambda n=name:self.move_category(n),
                          fg=UtilsTools.UI_ACCENT, bg=owner.CARD, font=owner.FONT_SMALL, relief='flat',bd=0,cursor='hand2')
                rec['_tree_move'] = move
            if self.can_move(name):
                rec['_tree_move'].pack(side='left',padx=6)
            else:
                rec['_tree_move'].pack_forget()
            if name in owner._expanded_categories:
                action.pack(fill='x', padx=22, pady=(0,2))
            else:
                action.pack_forget()
        graph = self.graph()
        searching = bool(owner.search_var.get().strip())
        visible_leaves = set(leaf_rows)
        for wrapper in leaf_rows.values(): wrapper.pack_forget()
        for record in self.group_rows.values(): record['row'].pack_forget()
        stack = [(n,0) for n in reversed(graph.roots())]
        while stack:
            name, depth = stack.pop()
            if name in self.hierarchy:
                if not any(n in visible_leaves for n in self.leaf_names(name)):
                    continue
                record = self.group_rows.get(name) or self._group_row(name)
                opened = searching or name in self.expanded
                record['arrow'].configure(text='▾' if opened else '▸')
                record['row'].pack(fill='x', padx=(4+min(depth,12)*15,4), pady=2)
                guide = record.get('guide')
                if depth:
                    if guide is None:
                        guide = tk.Frame(record['row'], bg='#d0c3df', width=1)
                        record['guide'] = guide
                    guide.place(x=0, y=0, relheight=1)
                elif guide is not None:
                    guide.place_forget()
                if opened:
                    record['action'].pack(anchor='w',padx=30,pady=(0,2))
                    stack.extend((r['category'],depth+1) for r in reversed(self.hierarchy[name]))
                else: record['action'].pack_forget()
            elif name in leaf_rows:
                leaf_rows[name].pack(fill='x',padx=(4+min(depth,12)*15,4),pady=2)
                rec = owner._row_details[name]
                guide = rec.get('_tree_guide')
                if depth:
                    if guide is None:
                        guide = tk.Frame(leaf_rows[name], bg='#d0c3df', width=1)
                        rec['_tree_guide'] = guide
                    guide.place(x=0,y=0,relheight=1)
                elif guide is not None:
                    guide.place_forget()
        self.update_checks()
        owner.colors_canvas.configure(scrollregion=owner.colors_canvas.bbox('all'))
