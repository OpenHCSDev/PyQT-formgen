"""Real Qt layout/paint regressions for optional manager-list preview wrapping."""

import pytest
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QListWidgetItem

from pyqt_reactive.core import ReorderableListWidget
from pyqt_reactive.widgets.shared.list_item_delegate import (
    DIRTY_FIELDS_ROLE,
    LAYOUT_ROLE,
    LEADING_MARKER_ROLE,
    ListItemLeadingMarker,
    MultilinePreviewItemDelegate,
)
from pyqt_reactive.widgets.shared.list_item_text_rendering import (
    StyledTextRenderer,
    TextPaintContext,
)
from pyqt_reactive.widgets.shared.styled_text_layout import Segment, StyledTextLayout


@pytest.fixture
def preview_list(qtbot):
    view = ReorderableListWidget()
    qtbot.addWidget(view)
    view.setItemDelegate(
        MultilinePreviewItemDelegate(
            QColor("black"),
            QColor("gray"),
            QColor("white"),
            parent=view,
        )
    )
    view.resize(380, 500)
    view.show()
    return view


def add_row(view, *, structured=True):
    text = "long_input_path/" * 35
    row = QListWidgetItem(text)
    if structured:
        row.setData(
            LAYOUT_ROLE,
            StyledTextLayout(
                name=Segment("Signal normalization", "name"),
                detail_line=text,
                preview_segments=[Segment("percentile=99.8", "percentile")],
                config_segments=[Segment("source=" + text, "source")],
                multiline=True,
            ),
        )
    view.addItem(row)
    return row


@pytest.mark.parametrize("structured", [True, False])
def test_wrap_toggle_and_viewport_resize_reflow_and_restore_scroll(qtbot, preview_list, structured):
    view = preview_list
    row = add_row(view, structured=structured)
    qtbot.waitUntil(lambda: view.horizontalScrollBar().maximum() > 0)
    compact_height = view.visualItemRect(row).height()
    view.horizontalScrollBar().setValue(100)

    view.setWordWrap(True)
    qtbot.waitUntil(lambda: view.visualItemRect(row).height() > compact_height)
    wrapped_height = view.visualItemRect(row).height()
    assert not view.horizontalScrollBar().isVisible()
    assert view.horizontalScrollBar().value() == 0
    assert view.visualItemRect(row).width() <= view.viewport().width()

    view.resize(240, 500)
    qtbot.waitUntil(lambda: view.visualItemRect(row).height() > wrapped_height)
    view.resize(650, 500)
    qtbot.waitUntil(lambda: view.visualItemRect(row).height() < wrapped_height)

    view.setWordWrap(False)
    qtbot.waitUntil(lambda: view.horizontalScrollBar().maximum() > 0)
    assert view.visualItemRect(row).height() == compact_height
    assert view.horizontalScrollBar().isVisible()


def test_wrapped_rows_update_after_content_and_font_changes(qtbot, preview_list):
    view = preview_list
    row = QListWidgetItem("short")
    view.addItem(row)
    view.setWordWrap(True)
    initial_height = view.visualItemRect(row).height()
    row.setText("a_very_long_unbroken_path/" * 80)
    qtbot.waitUntil(lambda: view.visualItemRect(row).height() > initial_height)
    text_height = view.visualItemRect(row).height()
    font = QFont(view.font())
    font.setPointSize(20)
    view.setFont(font)
    qtbot.waitUntil(lambda: view.visualItemRect(row).height() > text_height)


def test_single_wrapped_row_taller_than_viewport_can_scroll_to_last_line(qtbot, preview_list):
    view = preview_list
    view.resize(220, 150)
    row = add_row(view)
    view.setWordWrap(True)
    qtbot.waitUntil(lambda: view.verticalScrollBar().maximum() > 0)
    qtbot.waitUntil(
        lambda: view.verticalScrollBar().maximum()
        >= view.visualItemRect(row).height() - view.viewport().height()
    )
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
    assert view.visualItemRect(row).bottom() <= view.viewport().height()


def test_wrapped_row_markers_and_dirty_fields_take_measured_space(qtbot, preview_list):
    view = preview_list
    row = add_row(view)
    view.setWordWrap(True)
    before = view.visualItemRect(row).height()
    row.setData(LEADING_MARKER_ROLE, ListItemLeadingMarker())
    row.setData(DIRTY_FIELDS_ROLE, {"name", "source", "percentile"})
    qtbot.waitUntil(lambda: view.visualItemRect(row).height() >= before)
    # Paint the actual view, including the marker and row borders, without an X server.
    assert not view.grab().isNull()
    assert view.horizontalScrollBar().maximum() == 0


def test_shared_layout_preserves_unicode_field_styles_and_entire_text(qapp):
    layout = StyledTextLayout(
        name=Segment("🔬 Neurons", "name", asterisk_prefix=True),
        preview_segments=[Segment("percentile=99.8", "percentile")],
        config_segments=[Segment("path=" + "/plate/images" * 10, "path")],
        multiline=True,
    )
    renderer = StyledTextRenderer()
    context = TextPaintContext(
        {"name", "path"},
        {"percentile"},
        QFont("Sans", 12),
        QColor("white"),
        QColor("gray"),
    )
    compact = renderer.prepare(layout, context)
    wrapped = renderer.prepare(layout, context, 130)
    assert wrapped is renderer.prepare(layout, context, 130)
    assert wrapped.size.height() > compact.size.height()
    assert [p.text() for p in wrapped.paragraphs] == [p.text() for p in compact.paragraphs]
    assert "*🔬 Neurons" in wrapped.paragraphs[0].text()
    for paragraph in wrapped.paragraphs:
        encoded = paragraph.text().encode("utf-16-le")
        assert (
            sum(paragraph.lineAt(i).textLength() for i in range(paragraph.lineCount()))
            == len(encoded) // 2
        )
        for formatting in paragraph.formats():
            substring = encoded[
                formatting.start * 2 : (formatting.start + formatting.length) * 2
            ].decode("utf-16-le")
            if substring == "percentile=99.8":
                assert formatting.format.fontUnderline()


def test_single_line_layout_does_not_measure_hidden_details(qapp):
    renderer = StyledTextRenderer()
    context = TextPaintContext(set(), set(), QFont(), QColor(), QColor())
    layout = StyledTextLayout(name=Segment("Name"), detail_line="not displayed", multiline=False)
    prepared = renderer.prepare(layout, context)
    assert len(prepared.paragraphs) == 1
    assert prepared.paragraphs[0].text() == "▶ Name"
