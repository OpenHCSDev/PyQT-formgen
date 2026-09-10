"""One Qt text layout for painting and measuring styled list previews."""

from dataclasses import dataclass
from math import ceil

from PyQt6.QtCore import QPointF, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextLayout, QTextOption
from objectstate import DottedFieldPath

from pyqt_reactive.widgets.shared.styled_text_layout import Segment, StyledTextLayout


def field_matches(path: str | None, field_set: set[str]) -> bool:
    """Return whether a segment field path matches any styled field."""
    if path is None:
        return False
    if path == "":
        return bool(field_set)
    return DottedFieldPath(path).contains_any(field_set)


@dataclass(frozen=True)
class TextPaintContext:
    """Shared measurement/painting inputs, including width-changing markers."""

    dirty_fields: set[str]
    sig_diff_fields: set[str]
    base_font: QFont
    name_color: QColor
    preview_color: QColor


@dataclass(frozen=True)
class PreparedTextLayout:
    """Laid-out paragraphs shared verbatim by size hints and painting."""

    paragraphs: tuple[QTextLayout, ...]
    size: QSize

    def paint(self, painter: QPainter, origin: QPointF) -> None:
        for paragraph in self.paragraphs:
            paragraph.draw(painter, origin)


class TextMetricCache:
    """Bound retained shaped text, keyed by width and visual field state."""

    def __init__(self, max_entries: int = 256) -> None:
        self.max_entries = max_entries
        self._sizes: dict[tuple, PreparedTextLayout] = {}

    def remember(self, key: tuple, prepared: PreparedTextLayout) -> PreparedTextLayout:
        if len(self._sizes) >= self.max_entries:
            self._sizes.clear()
        self._sizes[key] = prepared
        return prepared


class StyledTextRenderer:
    """Shape styled paragraphs once; Qt owns line breaking and glyph geometry."""

    def __init__(self, metric_cache: TextMetricCache | None = None) -> None:
        self._metric_cache = metric_cache or TextMetricCache()

    def prepare(
        self,
        layout: StyledTextLayout | str,
        context: TextPaintContext,
        width: int | None = None,
    ) -> PreparedTextLayout:
        paragraphs = (
            layout.display_paragraphs()
            if isinstance(layout, StyledTextLayout)
            else [[(Segment(line), True)] for line in layout.replace("\u2028", "\n").split("\n")]
        )
        key = (
            tuple(tuple(paragraph) for paragraph in paragraphs),
            context.base_font.key(),
            context.name_color.rgba(),
            context.preview_color.rgba(),
            frozenset(context.dirty_fields),
            frozenset(context.sig_diff_fields),
            width,
        )
        cached = self._metric_cache._sizes.get(key)
        if cached is not None:
            return cached

        prepared = []
        y = 0.0
        max_width = 0.0
        for spans in paragraphs:
            text_parts = []
            formats = []
            position = 0
            for segment, primary in spans:
                dirty = field_matches(segment.field_path, context.dirty_fields)
                text = segment.text
                if dirty:
                    text = "*" + text if segment.asterisk_prefix else text + "*"
                formatting = QTextCharFormat()
                formatting.setForeground(context.name_color if primary else context.preview_color)
                formatting.setFontUnderline(
                    field_matches(segment.field_path, context.sig_diff_fields)
                )
                run = QTextLayout.FormatRange()
                run.start = position
                # Qt indexes UTF-16 code units, not Python Unicode code points.
                run.length = len(text.encode("utf-16-le")) // 2
                run.format = formatting
                formats.append(run)
                text_parts.append(text)
                position += run.length
            paragraph = QTextLayout("".join(text_parts), context.base_font)
            paragraph.setCacheEnabled(True)
            paragraph.setFormats(formats)
            option = QTextOption()
            option.setWrapMode(
                QTextOption.WrapMode.NoWrap
                if width is None
                else QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
            )
            paragraph.setTextOption(option)
            paragraph.beginLayout()
            while True:
                line = paragraph.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(1e9 if width is None else max(1, width))
                line.setPosition(QPointF(0, y))
                y += line.height()
                max_width = max(max_width, line.naturalTextWidth())
            paragraph.endLayout()
            prepared.append(paragraph)
        return self._metric_cache.remember(
            key,
            PreparedTextLayout(tuple(prepared), QSize(ceil(max_width), ceil(y))),
        )


class StyledTextSizeCalculator:
    """Public sizing surface backed by the same shaped text as the delegate."""

    def __init__(self, metric_cache: TextMetricCache | None = None) -> None:
        self._renderer = StyledTextRenderer(metric_cache)

    def from_layout(self, layout: StyledTextLayout | str, font: QFont) -> QSize:
        prepared = self._renderer.prepare(
            layout, TextPaintContext(set(), set(), font, QColor(), QColor())
        )
        return prepared.size + QSize(20, 10)

    def from_text(self, text: str, font: QFont) -> QSize:
        return self.from_layout(text, font)
