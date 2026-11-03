"""Charts in text: sparklines, stacked and line charts, the mirrored link chart, round tops."""

from __future__ import annotations

from lxtop.core import charts
from lxtop.core.charts import lines, mirror
from lxtop.core.render import CONSOLE, UNICODE


def test_graph_rows_top_first() -> None:
    rows = charts.graph([0.0, 0.5, 1.0], width=3, height=2, top=1.0, g=CONSOLE)
    assert rows == ["  █", " ██"]
    assert charts.graph([2.0], width=1, height=1, top=1.0, g=CONSOLE) == ["█"]
    fine = charts.graph([0.25], width=1, height=1, top=1.0, g=UNICODE)
    assert fine == ["▂"]
    # Fewer values than columns: padded on the left, newest on the right.
    assert charts.graph([1.0], width=3, height=1, top=1.0, g=CONSOLE) == ["  █"]


def test_downsample_keeps_peaks() -> None:
    values = [0.0] * 10
    values[7] = 9.0
    out = charts.downsample(values, 5)
    assert len(out) == 5 and out[3] == 9.0
    assert charts.downsample([1.0, 2.0], 5) == [1.0, 2.0]


def test_nice_top() -> None:
    assert charts.nice_top([0.0], 1024) == 2000
    assert charts.nice_top([3500.0], 1) == 5000
    assert charts.nice_top([700 * 1024], 1024, base=1024) == 1024 * 1024
    assert charts.nice_top([0.0], 1024, base=1024) == 1024


def test_resample_keeps_means() -> None:
    assert charts.resample([1.0, 3.0, 5.0, 7.0], 2) == [2.0, 6.0]
    assert charts.resample([1.0], 4) == [1.0]


def test_stack_layers_bottom_up() -> None:
    grid = charts.stack([[1.0], [1.0]], width=1, height=2, top=2.0, g=UNICODE)
    assert grid == [[("█", 1)], [("█", 0)]]
    # A half-full single row is a half block of the layer that covers it.
    (row,) = charts.stack([[0.5], [0.0]], width=2, height=1, top=1.0, g=UNICODE)
    assert row == [(" ", -1), ("▄", 0)]
    # The console's whole-cell glyphs round a half cell up, and nothing below it.
    (row,) = charts.stack([[0.4]], width=1, height=1, top=1.0, g=CONSOLE)
    assert row == [(" ", 0)]
    assert charts.stack([[5.0]], 1, 1, top=1.0, g=UNICODE) == [[("█", 0)]]
    assert charts.stack([], 3, 2, 1.0, UNICODE) == [[(" ", -1)] * 3] * 2


def test_mirror_puts_download_up_and_upload_down() -> None:
    grid = mirror([0.0, 10.0], [10.0, 5.0], 2, 2, 2, 10.0, UNICODE)
    assert len(grid) == 5  # 2 up, the axis, 2 down
    up = ["".join(c for c, _ in row) for row in grid[:2]]
    assert up == [" █", " █"]
    assert all(kind in ("rx", "") for row in grid[:2] for _, kind in row)
    assert grid[2] == [("─", "axis"), ("─", "axis")]
    down = ["".join(c for c, _ in row) for row in grid[3:]]
    assert down == ["██", "█ "]  # 5 of 10 fills the first row down only
    assert all(kind in ("tx", "") for row in grid[3:] for _, kind in row)


def test_mirror_half_cells_down_and_eighths_up() -> None:
    grid = mirror([5.0], [6.0], 1, 1, 1, 10.0, UNICODE)
    assert grid[0][0] == ("▄", "rx")  # half of one row, from the axis up
    assert grid[2][0] == ("▀", "tx")  # down has half cells only: from 1/4 to 3/4 a half


def test_braille_lines_join_points_and_leave_gaps() -> None:
    # 4 points in 2 cells, 1 row (4 dots high), top 3: heights 0, 3, 3, 0.
    grid = lines([[0.0, 3.0, 3.0, 0.0]], 2, 1, 3.0, UNICODE)
    chars = "".join(c for c, _ in grid[0])
    # Left cell: the start point (bottom left dot) and the climb to the top (its right column).
    # Right cell: the top point (top left dot) and the drop back down (its right column).
    assert chars == chr(0x2800 + 0x40 + 0xB8) + chr(0x2800 + 0x01 + 0xB8)
    assert [owner for _, owner in grid[0]] == [0, 0]
    gap = lines([[1.0, -1.0, -1.0, 1.0]], 2, 1, 3.0, UNICODE)  # negative: no answer
    assert gap[0][0][0] == chr(0x2800 + 0x04) and gap[0][1][0] == chr(0x2800 + 0x20)


def test_two_series_share_a_cell_by_or_and_the_later_one_owns_it() -> None:
    grid = lines([[0.0, 0.0], [3.0, 3.0]], 1, 1, 3.0, UNICODE)
    char, owner = grid[0][0]
    assert ord(char) - 0x2800 == 0x40 | 0x80 | 0x01 | 0x08 and owner == 1


def test_console_lines_use_box_drawing() -> None:
    grid = lines([[0.0, 2.0, 2.0, 0.0]], 4, 3, 2.0, CONSOLE)
    rows = ["".join(c for c, _ in row) for row in grid]
    assert rows == [" ╭─╮", " │ │", "─╯ ╰"]  # up at x=1, flat at x=2, down at x=3
    assert all(c in " ─│╭╮╰╯" for row in rows for c in row)
