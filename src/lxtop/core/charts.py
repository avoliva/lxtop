"""Pure chart drawing in text: sparklines and graphs, stacked and line charts in braille or box
characters, the mirrored link chart, and round tops for their axes."""

from __future__ import annotations

from lxtop.core.render import Glyphs


def nice_top(values: list[float], floor: float, base: int = 10) -> float:
    """A round scale for a graph: at least `floor`, rounded up to 1/2/5 x 10^n, or with
    base=1024 (bytes) to 1/2/5/10/20/50/100/200/500 x 1024^n."""
    peak = max([floor, *values])
    scale = 1.0
    if base == 1024:
        while scale * 1024 <= peak:
            scale *= 1024
        for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1024):
            if peak <= step * scale:
                return step * scale
        return peak
    while scale * 10 <= peak:
        scale *= 10
    for step in (1, 2, 5, 10):
        if peak <= step * scale:
            return step * scale
    return peak


def downsample(values: list[float], width: int) -> list[float]:
    """At most `width` points, each the peak of its bucket, so short spikes stay visible."""
    if width <= 0 or len(values) <= width:
        return list(values)
    size = len(values) / width
    return [
        max(values[int(i * size) : max(int(i * size) + 1, int((i + 1) * size))])
        for i in range(width)
    ]


def resample(values: list[float], width: int) -> list[float]:
    """At most `width` points, each the mean of its bucket (for stacked charts, whose layers
    must add up)."""
    if width <= 0 or len(values) <= width:
        return list(values)
    size = len(values) / width
    out = []
    for i in range(width):
        bucket = values[int(i * size) : max(int(i * size) + 1, int((i + 1) * size))]
        out.append(sum(bucket) / len(bucket))
    return out


def graph(values: list[float], width: int, height: int, top: float, g: Glyphs) -> list[str]:
    """Columns of the last `width` values, scaled to `top`, as `height` rows (top row first)."""
    if width <= 0 or height <= 0:
        return []
    recent = values[-width:]
    recent = [0.0] * (width - len(recent)) + recent
    steps = len(g.vertical)
    levels = [round(max(0.0, min(1.0, v / top)) * height * steps) if top > 0 else 0 for v in recent]
    rows: list[str] = []
    for row in range(height):
        floor = (height - row - 1) * steps
        line = []
        for level in levels:
            fill = level - floor
            if fill >= steps:
                line.append(g.vertical[-1])
            elif fill > 0:
                line.append(g.vertical[fill - 1])
            else:
                line.append(" ")
        rows.append("".join(line))
    return rows


def stack(
    layers: list[list[float]], width: int, height: int, top: float, g: Glyphs
) -> list[list[tuple[str, int]]]:
    """A stacked area chart: `height` rows (top first) of `width` cells, each (char, layer).
    Layers are drawn bottom up and aligned on the right (newest); layer -1 is empty. A cell
    goes to the layer covering most of it; the top cell of a column is a partial block."""
    if width <= 0 or height <= 0:
        return []
    steps = len(g.vertical)
    padded = [[0.0] * (width - len(v[-width:])) + v[-width:] for v in layers]
    grid = [[(" ", -1)] * width for _ in range(height)]
    for col in range(width):
        bounds, total = [], 0.0
        for index, values in enumerate(padded):
            low = total
            total += max(0.0, values[col])
            bounds.append((low, total, index))
        if top <= 0:
            continue
        cells = min(1.0, total / top) * height
        for row in range(height):  # row 0 is the bottom
            if cells <= row:
                break
            fill = min(1.0, cells - row)
            a, b = row * top / height, (row + 1) * top / height
            owner = max(bounds, key=lambda x: min(b, x[1]) - max(a, x[0]))[2] if bounds else -1
            level = max(1, round(fill * steps))
            char = g.vertical[-1] if level >= steps else g.vertical[level - 1]
            if steps == 1 and fill < 0.5:
                char = " "
            grid[height - 1 - row][col] = (char, owner)
    return grid


def mirror(
    rx: list[float],
    tx: list[float],
    width: int,
    up: int,
    down: int,
    top: float,
    g: Glyphs,
) -> list[list[tuple[str, str]]]:
    """Download growing up from a middle axis and upload growing down from it, both scaled to
    `top`, newest on the right: `up` rows, the axis, `down` rows. Each cell is (char, kind),
    kind "rx", "tx", "axis" or "". Down has half cells (▀) only: the font has no other top-aligned
    blocks, and the console without lxtop's font has whole cells only."""
    if width <= 0:
        return []

    def cells(values: list[float], rows: int) -> list[float]:
        recent = values[-width:]
        recent = [0.0] * (width - len(recent)) + recent
        return [max(0.0, min(1.0, v / top)) * rows if top > 0 else 0.0 for v in recent]

    steps = len(g.vertical)
    grid: list[list[tuple[str, str]]] = []
    rx_cells = cells(rx, up)
    for row in range(up):
        floor = up - row - 1
        line = []
        for filled in rx_cells:
            part = filled - floor
            if part >= 1:
                line.append((g.vertical[-1], "rx"))
            elif part > 0 and steps > 1 and round(part * steps) > 0:
                line.append((g.vertical[round(part * steps) - 1], "rx"))
            elif part >= 0.5:
                line.append((g.vertical[-1], "rx"))
            else:
                line.append((" ", ""))
        grid.append(line)
    grid.append([(g.hline, "axis")] * width)
    tx_cells = cells(tx, down)
    for row in range(down):
        line = []
        for filled in tx_cells:
            part = filled - row
            if part >= 0.75 or (part >= 0.5 and not g.eighths):
                line.append((g.full, "tx"))
            elif part >= 0.25 and g.eighths:
                line.append(("▀", "tx"))
            else:
                line.append((" ", ""))
        grid.append(line)
    return grid


BRAILLE_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))  # [row][column]


def _squeeze(values: list[float], width: int) -> list[float]:
    """At most `width` points, each its bucket's peak (a gap if all of it is a gap)."""
    if width <= 0 or len(values) <= width:
        return list(values)
    size = len(values) / width
    out = []
    for i in range(width):
        bucket = values[int(i * size) : max(int(i * size) + 1, int((i + 1) * size))]
        good = [v for v in bucket if v >= 0]
        out.append(max(good) if good else -1.0)
    return out


def lines(
    series: list[list[float]], width: int, height: int, top: float, g: Glyphs
) -> list[list[tuple[str, int]]]:
    """Line graphs of several series on one chart, newest on the right: `height` rows of
    `width` cells, each (char, series index or -1). A negative value is a gap (no answer).
    With braille each cell is 2 x 4 dots and neighbouring points are joined by a vertical run;
    a cell two lines cross goes to the later series. Without it, box-drawing steps."""
    if width <= 0 or height <= 0:
        return []
    if not g.braille:
        return _box_lines(series, width, height, top)
    cols, rows = width * 2, height * 4
    dots = [[0] * width for _ in range(height)]
    owner = [[-1] * width for _ in range(height)]
    for index, values in enumerate(series):
        points = _squeeze(values, cols)[-cols:]
        points = [-1.0] * (cols - len(points)) + points
        prev: int | None = None
        for x, v in enumerate(points):
            if v < 0 or top <= 0:
                prev = None
                continue
            y = min(rows - 1, int(min(v, top) / top * (rows - 1) + 0.5))
            low, high = (y, y) if prev is None else (min(prev, y), max(prev, y))
            for yy in range(low, high + 1):
                r = rows - 1 - yy
                dots[r // 4][x // 2] |= BRAILLE_BITS[r % 4][x % 2]
                owner[r // 4][x // 2] = index
            prev = y
    return [
        [(chr(0x2800 + d) if d else " ", owner[r][c]) for c, d in enumerate(dots[r])]
        for r in range(height)
    ]


def _box_lines(
    series: list[list[float]], width: int, height: int, top: float
) -> list[list[tuple[str, int]]]:
    grid: list[list[tuple[str, int]]] = [[(" ", -1)] * width for _ in range(height)]

    def put(level: int, x: int, char: str, index: int) -> None:
        grid[height - 1 - level][x] = (char, index)

    for index, values in enumerate(series):
        points = _squeeze(values, width)[-width:]
        points = [-1.0] * (width - len(points)) + points
        levels = [
            None if v < 0 or top <= 0 else min(height - 1, round(min(v, top) / top * (height - 1)))
            for v in points
        ]
        for x, b in enumerate(levels):
            a = levels[x - 1] if x else None
            if b is None:
                continue
            if a is None or a == b:
                put(b, x, "─", index)
                continue
            put(a, x, "╯" if b > a else "╮", index)
            put(b, x, "╭" if b > a else "╰", index)
            for level in range(min(a, b) + 1, max(a, b)):
                put(level, x, "│", index)
    return grid
