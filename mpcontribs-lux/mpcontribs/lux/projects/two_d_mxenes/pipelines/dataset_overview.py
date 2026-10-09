"""Excel overview of which MXene structures are present, broken or missing.

The main sheet is a grid with one row per M-X system and one column per
structure that can exist for it, grouped by thickness n, then termination,
then stacking label. Each cell shows

- ``✓`` a CONTCAR that passed every check,
- ``✗`` a CONTCAR that failed (hover for the reason; details on "Problems"),
- ``○`` no CONTCAR for a structure that is in scope,

and combinations excluded from the scope are shaded grey. Rows are created for
every transition metal found in the data, in order of atomic number. All
combinations are in scope unless excluded with ``out_of_scope`` (on the command
line: ``--out-of-scope Hf:O``).

Generate it with the dataset check::

    python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions DATA_ROOT --overview overview.xlsx
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from datetime import datetime
from itertools import pairwise
from pathlib import Path

from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    CheckRecord,
    CheckResult,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import (
    MXeneLabel,
    parse_folder_label,
)
from pymatgen.core import Element

NONMETALS: tuple[str, ...] = ("C", "N")
TERMINATIONS: tuple[str | None, ...] = (None, "F", "O")

ScopeExclusion = tuple[str, str | None]
"""(metal, termination) to exclude; metal `*` means every metal, termination
None means pristine."""

GOOD, BAD, MISSING, OUT_OF_SCOPE = "✓", "✗", "○", ""

_STACKINGS = {1: ("t", "h"), 2: ("t", "h1a", "h1b", "h2"), 3: ("t", "h1a", "h1b", "h2")}
_N_NAMES = {1: "n = 1  (M₂X)", 2: "n = 2  (M₃X₂)", 3: "n = 3  (M₄X₃)"}
_T_NAMES = {None: "pristine", "F": "F-terminated", "O": "O-terminated"}

_COLORS = {
    GOOD: ("C6EFCE", "006100"),
    BAD: ("FFC7CE", "9C0006"),
    MISSING: ("FFEB9C", "9C5700"),
    OUT_OF_SCOPE: ("EDEDED", "808080"),
}


def grid_columns() -> list[tuple[int, str | None, str]]:
    """All (n, termination, folder label) columns of the grid, in order.

    Returns:
        One tuple per column: 50 for n = 1-3 and terminations none, F, O.
    """
    cols = []
    for n in (1, 2, 3):
        for term in TERMINATIONS:
            for stacking in _STACKINGS[n]:
                sites = (1, 2) if term else (None,)
                for site in sites:
                    label = stacking if site is None else f"{stacking}-{site}"
                    cols.append((n, term, label))
    return cols


def cell_id(metal: str, nonmetal: str, n: int, term: str | None, label: str) -> str:
    """The `mxeneId` a grid cell stands for.

    Args:
        metal: Transition metal M.
        nonmetal: C or N.
        n: Thickness index.
        term: Termination, or None for pristine.
        label: Folder label, e.g. `h1a-2`.

    Returns:
        The ID, e.g. `Ti3C2O2-h1a-2`.
    """
    stacking, site = parse_folder_label(label)
    lab = MXeneLabel(
        metal=metal,
        nonmetal=nonmetal,
        termination=term,
        n=n,
        stacking=stacking,
        terminationSite=site,
    )
    return f"{lab.formula}-{lab.label}"


def metals_in(result: CheckResult) -> list[str]:
    """Transition metals that appear in the checked files.

    Args:
        result: Output of `check_dataset`.

    Returns:
        Metal symbols ordered by atomic number.
    """
    found = {r.metal for r in result.records if r.metal}
    return sorted(found, key=lambda symbol: Element(symbol).Z)


def parse_scope_exclusion(text: str) -> ScopeExclusion:
    """Parse `M:T` (e.g. `Hf:O`, `Re:none`, `*:O`) into a scope exclusion.

    Args:
        text: Metal symbol or `*`, a colon, and `none`, `F` or `O`.

    Returns:
        (metal, termination), with termination None for `none`.

    Raises:
        ValueError: If the text is malformed or names an unknown element or
            termination.
    """
    metal, sep, term = text.partition(":")
    metal, term = metal.strip(), term.strip()
    if not sep or not metal or not term:
        raise ValueError(f"Expected METAL:TERMINATION, e.g. Hf:O, got {text!r}")
    if metal != "*" and not Element.is_valid_symbol(metal):
        raise ValueError(f"{metal!r} is not an element symbol")
    termination = None if term.lower() == "none" else term
    if termination not in TERMINATIONS:
        raise ValueError(f"Termination must be none, F or O, got {term!r}")
    return metal, termination


def _excluded(metal: str, term: str | None, out_of_scope) -> bool:
    return (metal, term) in out_of_scope or ("*", term) in out_of_scope


def grid_states(
    result: CheckResult,
    out_of_scope: Collection[ScopeExclusion] = (),
) -> tuple[dict[tuple, str], dict[str, list[CheckRecord]]]:
    """State of every grid cell and the records that claim each cell.

    Args:
        result: Output of `check_dataset`.
        out_of_scope: (metal, termination) combinations that are not expected
            to have structures; their empty cells are shown as out of scope
            instead of missing.

    Returns:
        `{(metal, nonmetal, n, termination, label): symbol}` and
        `{cellId: check records}`.
    """
    out_of_scope = set(out_of_scope)
    claims: dict[str, list[CheckRecord]] = {}
    for rec in result.records:
        if rec.cellId and rec.status != "skipped":
            claims.setdefault(rec.cellId, []).append(rec)

    states = {}
    for m in metals_in(result):
        for x in NONMETALS:
            for n, term, label in grid_columns():
                recs = claims.get(cell_id(m, x, n, term, label), [])
                if any(r.status == "failed" for r in recs):
                    state = BAD
                elif recs:
                    state = GOOD
                elif _excluded(m, term, out_of_scope):
                    state = OUT_OF_SCOPE
                else:
                    state = MISSING
                states[(m, x, n, term, label)] = state
    return states, claims


def write_overview(
    result: CheckResult,
    path: str | Path,
    root: str | Path,
    out_of_scope: Collection[ScopeExclusion] = (),
) -> None:
    """Write the overview workbook.

    Args:
        result: Output of `check_dataset`.
        path: Excel file to write.
        root: Root folder of the CONTCAR tree, for relative paths.
        out_of_scope: Combinations excluded from the scope (see `grid_states`).
    """
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    root = Path(root)
    states, claims = grid_states(result, out_of_scope)
    columns = grid_columns()
    systems = [(m, x) for m in metals_in(result) for x in NONMETALS]

    fills = {k: PatternFill("solid", fgColor=bg) for k, (bg, _) in _COLORS.items()}
    fonts = {k: Font(color=fg, bold=True, size=12) for k, (_, fg) in _COLORS.items()}
    center = Alignment(horizontal="center", vertical="center")
    thin, thick = Side(style="thin", color="BFBFBF"), Side(
        style="medium", color="404040"
    )
    header_fill = PatternFill("solid", fgColor="DDEBF7")
    bold = Font(bold=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Overview"

    # --- title, summary and legend -----------------------------------------
    totals = Counter(states.values())
    ws["A1"] = "two_d_mxenes dataset status"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (
        f"Generated {datetime.now().astimezone().date().isoformat()} from {root.name}: "
        f"{totals[GOOD]} good, {totals[BAD]} with problems "
        f"({len(result.failures)} files), "
        f"{totals[MISSING]} missing, {len(result.skipped)} auxiliary files skipped"
    )
    legend = [
        (GOOD, "CONTCAR passes all checks"),
        (BAD, "problem: hover the cell, or see Problems"),
        (MISSING, "no CONTCAR yet: see Missing"),
        (OUT_OF_SCOPE, "out of scope"),
    ]
    col = 1
    for symbol, text in legend:
        c = ws.cell(row=3, column=col, value=symbol or " ")
        c.fill, c.font, c.alignment = fills[symbol], fonts[symbol], center
        ws.cell(row=3, column=col + 1, value=text)
        col += 13

    # --- header rows ---------------------------------------------------------
    top, first_data = 5, 8
    first_grid_col = 2
    ws.cell(row=top + 2, column=1, value="system").font = bold
    for r in range(top, top + 3):
        ws.cell(row=r, column=1).fill = header_fill

    def group_starts(key):
        starts, prev = [], None
        for i, c in enumerate(columns):
            if key(c) != prev:
                starts.append(i)
                prev = key(c)
        return starts

    n_starts = set(group_starts(lambda c: c[0]))
    t_starts = set(group_starts(lambda c: c[:2]))

    for row, key, names in [
        (top, lambda c: c[0], lambda c: _N_NAMES[c[0]]),
        (top + 1, lambda c: c[:2], lambda c: _T_NAMES[c[1]]),
    ]:
        starts = sorted(group_starts(key)) + [len(columns)]
        for a, b in pairwise(starts):
            c1, c2 = first_grid_col + a, first_grid_col + b - 1
            ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
            cell = ws.cell(row=row, column=c1, value=names(columns[a]))
            cell.font, cell.alignment, cell.fill = bold, center, header_fill

    for i, (n, term, label) in enumerate(columns):
        cell = ws.cell(row=top + 2, column=first_grid_col + i, value=label)
        cell.alignment = Alignment(horizontal="center", text_rotation=90)
        cell.fill, cell.font = header_fill, Font(size=9)

    # --- grid ----------------------------------------------------------------
    total_col = first_grid_col + len(columns)
    for j, symbol in enumerate((GOOD, BAD, MISSING)):
        c = ws.cell(row=top + 2, column=total_col + j, value=symbol)
        c.fill, c.font, c.alignment = fills[symbol], fonts[symbol], center
    ws.cell(row=top + 1, column=total_col, value="per system").font = bold

    for r, (m, x) in enumerate(systems, start=first_data):
        ws.cell(row=r, column=1, value=f"{m}–{x}").font = bold
        row_counts = Counter()
        for i, (n, term, label) in enumerate(columns):
            state = states[(m, x, n, term, label)]
            row_counts[state] += 1
            cell = ws.cell(row=r, column=first_grid_col + i, value=state or None)
            cell.fill, cell.font, cell.alignment = fills[state], fonts[state], center
            left = (
                thick
                if i in n_starts
                else (Side(style="thin", color="808080") if i in t_starts else thin)
            )
            cell.border = Border(left=left, right=thin, top=thin, bottom=thin)
            if state == BAD:
                cid = cell_id(m, x, n, term, label)
                text = "\n".join(
                    f"{rec.path.relative_to(root)}: {rec.message}"
                    for rec in claims[cid]
                )
                cell.comment = Comment(
                    f"{cid}\n{text}", "dataset check", width=420, height=160
                )
        for j, symbol in enumerate((GOOD, BAD, MISSING)):
            ws.cell(row=r, column=total_col + j, value=row_counts[symbol]).alignment = (
                center
            )

    # per-column totals
    last = first_data + len(systems) - 1
    for k, symbol in enumerate((GOOD, BAD, MISSING)):
        r = last + 1 + k
        c = ws.cell(row=r, column=1, value=f"{symbol} per structure")
        c.font = Font(color=_COLORS[symbol][1], bold=True)
        for i, (n, term, label) in enumerate(columns):
            count = sum(states[(m, x, n, term, label)] == symbol for m, x in systems)
            ws.cell(row=r, column=first_grid_col + i, value=count or None).alignment = (
                center
            )

    ws.column_dimensions["A"].width = 16
    for i in range(len(columns) + 3):
        ws.column_dimensions[get_column_letter(first_grid_col + i)].width = 4.2
    ws.row_dimensions[top + 2].height = 42
    ws.freeze_panes = ws.cell(row=first_data, column=first_grid_col)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # --- Problems -------------------------------------------------------------
    ps = wb.create_sheet("Problems")
    ps.append(["structure", "file", "measured coordination", "problem"])
    for rec in result.failures:
        ps.append(
            [
                rec.cellId or "(could not be placed)",
                str(rec.path.relative_to(root)),
                rec.measuredCoordination,
                rec.message,
            ]
        )
    _style_table(ps, [18, 45, 22, 110], bold, header_fill)

    # --- Missing ----------------------------------------------------------------
    ms = wb.create_sheet("Missing")
    ms.append(["structure", "M", "X", "n", "termination", "label"])
    for (m, x, n, term, label), state in states.items():
        if state == MISSING:
            ms.append([cell_id(m, x, n, term, label), m, x, n, term or "none", label])
    _style_table(ms, [18, 6, 6, 5, 13, 8], bold, header_fill)

    # --- All files ----------------------------------------------------------------
    fs = wb.create_sheet("All files")
    fs.append(
        ["file", "status", "structure", "formula", "measured coordination", "message"]
    )
    for rec in result.records:
        fs.append(
            [
                str(rec.path.relative_to(root)),
                rec.status,
                rec.cellId,
                rec.formula,
                rec.measuredCoordination,
                rec.message,
            ]
        )
    _style_table(fs, [50, 9, 18, 12, 22, 90], bold, header_fill)

    wb.save(path)


def _style_table(ws, widths, bold, fill) -> None:
    from openpyxl.utils import get_column_letter

    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
        ws.cell(row=1, column=i).font = bold
        ws.cell(row=1, column=i).fill = fill
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
