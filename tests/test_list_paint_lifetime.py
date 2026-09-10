"""Native paint dispatch keeps its widget alive through cyclic collection."""

import gc
import weakref

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QListWidgetItem

from pyqt_reactive.core import ReorderableListWidget
from pyqt_reactive.services.widget_tree_projection import WidgetActionKind
from pyqt_reactive.widgets.shared.list_item_delegate import (
    LAYOUT_ROLE,
    PREVIEW_WRAP_ROLE,
    MultilinePreviewItemDelegate,
    PreviewWrapMode,
)
from pyqt_reactive.widgets.shared.styled_text_layout import (
    ParagraphLineGuide,
    Segment,
    StyledTextLayout,
)


def test_pending_row_action_cannot_collect_widget_during_native_paint(qapp, qtbot, monkeypatch):
    def prepare_pending_view():
        view = ReorderableListWidget()
        qtbot.addWidget(view)
        view.setItemDelegate(
            MultilinePreviewItemDelegate(
                QColor("black"), QColor("gray"), QColor("white"), parent=view
            )
        )
        view.resize(400, 400)
        for name in ("First", "Second"):
            row = QListWidgetItem(name)
            row.setData(
                LAYOUT_ROLE,
                StyledTextLayout(
                    name=Segment(name),
                    preview_segments=[Segment("source=" + "/images/" * 30)],
                    multiline=True,
                ),
            )
            view.addItem(row)
        view.show()
        view.doItemsLayout()
        index = view.model().index(0, 0)
        WidgetActionKind.ITEM_PREVIEW_TOGGLE.item_action.defer(view, index)
        qtbot.waitUntil(lambda: view.item(0).data(PREVIEW_WRAP_ROLE) is PreviewWrapMode.WRAPPED)
        WidgetActionKind.ITEM_SELECT.item_action.defer(view, index)
        view.viewport().update()
        # No test-local owner survives this frame. The queued callback and its
        # native-parented timer form a cycle, while qtbot retains only a weakref.
        return weakref.ref(view)

    reference = prepare_pending_view()
    collections = []
    original = ParagraphLineGuide.paint

    def collect_inside_paint(self, painter, origin, height, color):
        gc.collect()
        collections.append(reference() is not None)
        original(self, painter, origin, height, color)

    monkeypatch.setattr(ParagraphLineGuide, "paint", collect_inside_paint)
    qtbot.waitUntil(lambda: bool(collections))
    assert all(collections)
    # The native paint boundary protects the owner temporarily, not forever.
    gc.collect()
    assert reference() is None
