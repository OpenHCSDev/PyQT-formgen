"""Actual Qt paint geometry for nested parameter-form flash feedback."""

from dataclasses import dataclass, field

import objectstate.config as config_module
import pytest
from objectstate import ObjectState, ObjectStateRegistry, set_base_config_type
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout

from pyqt_reactive.animation.flash_mixin import (
    LEAF_WIDGET_TYPES,
    WindowFlashOverlay,
    _GlobalFlashCoordinator,
    get_child_mask_rect,
    resolve_mask_widgets,
)
from pyqt_reactive.forms.parameter_form_manager import (
    FormManagerConfig,
    ParameterFormManager,
)
from pyqt_reactive.theming import ColorScheme
from pyqt_reactive.widgets.shared.clickable_help_components import HelpIndicator


@pytest.fixture
def nested_form(qapp):
    @dataclass
    class Child:
        alpha: int = 1
        beta: int = 2

    @dataclass
    class Root:
        child: Child = field(default_factory=Child)

    previous_base = config_module._base_config_type
    set_base_config_type(Root)
    ObjectStateRegistry.clear()
    host = QDialog()
    host.resize(600, 350)
    layout = QVBoxLayout(host)
    manager = ParameterFormManager(
        ObjectState(Root()),
        FormManagerConfig(color_scheme=ColorScheme(), use_scroll_area=False),
    )
    layout.addWidget(manager)
    host.show()
    qapp.processEvents()
    yield host, manager.nested_managers["child"]
    coordinator = _GlobalFlashCoordinator.get()
    if coordinator._timer is not None:
        coordinator._timer.stop()
    coordinator._computed_colors.clear()
    coordinator._flash_start_times.clear()
    coordinator._pending_flash_keys.clear()
    WindowFlashOverlay.cleanup_window(host)
    host.close()
    host.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    ObjectStateRegistry.clear()
    config_module._base_config_type = previous_base


@pytest.mark.parametrize("text", ["Alpha:", "A longer parameter label:"])
@pytest.mark.parametrize("width", [100, 220])
@pytest.mark.parametrize("underline", [False, True])
def test_label_mask_is_tight_and_respects_alignment_and_style(
    nested_form, qapp, text, width, underline
):
    host, manager = nested_form
    label = manager.labels["alpha"].findChild(QLabel)
    label.setText(text)
    font = label.font()
    font.setUnderline(underline)
    label.setFont(font)
    label.setWordWrap(True)
    label.setFixedSize(width, 72)
    manager.labels["alpha"].setMinimumSize(width + 40, 80)
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
    label.setStyleSheet("color: white; background: #141414; padding: 4px; margin: 2px;")
    qapp.processEvents()
    rect = label.rect().translated(label.mapTo(host, QPoint()))
    mask = get_child_mask_rect(label, host)
    assert mask.width() < rect.width()
    assert mask.height() < rect.height()
    contents = label.contentsRect().translated(label.mapTo(host, QPoint()))
    assert contents.contains(mask)
    assert mask.bottom() <= contents.bottom()
    image = label.grab().toImage()
    ratio = image.devicePixelRatio()
    text_pixels = [
        QPoint(int(x / ratio), int(y / ratio))
        for y in range(image.height())
        for x in range(image.width())
        if max(image.pixelColor(x, y).getRgb()[:3]) > 20 and image.pixelColor(x, y).alpha() > 0
    ]
    assert text_pixels
    outside = [point for point in text_pixels if not mask.contains(label.mapTo(host, point))]
    assert not outside, (mask, contents, outside[:10])


@pytest.mark.parametrize("fields", [("alpha",), ("alpha", "beta")])
def test_nested_flash_paint_has_opaque_context_and_complete_clear_holes(nested_form, qapp, fields):
    host, manager = nested_form
    for name in fields:
        manager.update_parameter(name, 10)
    qapp.processEvents()
    overlay = WindowFlashOverlay.get_for_window(host)
    coordinator = _GlobalFlashCoordinator.get()
    if coordinator._timer is not None:
        coordinator._timer.stop()
    coordinator._computed_colors.clear()
    keys = {f"child.{name}" for name in fields}
    coordinator._computed_colors.update({key: QColor(255, 0, 0, 255) for key in keys})
    overlay._rebuild_geometry_cache([], keys)
    records, _ = overlay._visible_paint_records(keys, colors=coordinator._computed_colors)
    assert len(records) == 1
    record = records[0]
    assert record.color.alpha() == 255
    title = overlay._elements["child.alpha"][0].container._title_label
    assert not record.path.contains(QPointF(get_child_mask_rect(title, host).center()))
    for name in fields:
        labels = resolve_mask_widgets(manager.labels[name], LEAF_WIDGET_TYPES)
        indicator = manager.labels[name].findChild(HelpIndicator)
        assert indicator is not None
        assert get_child_mask_rect(indicator, host) == indicator.rect().translated(
            indicator.mapTo(host, QPoint())
        )
        for widget in (*labels, manager.widgets[name]):
            rect = get_child_mask_rect(widget, host)
            for point in (
                rect.center(),
                rect.topLeft() + QPoint(1, 1),
                rect.bottomRight() - QPoint(1, 1),
            ):
                assert not record.path.contains(QPointF(point))

    image = overlay.grab().toImage()
    ratio = image.devicePixelRatio()
    for name in fields:
        point = manager.widgets[name].mapTo(host, manager.widgets[name].rect().center())
        assert image.pixelColor(int(point.x() * ratio), int(point.y() * ratio)).alpha() == 0
    painted = [
        image.pixelColor(int(x * ratio), int(y * ratio))
        for y in range(record.rect.top() + 2, record.rect.bottom() - 2)
        for x in range(record.rect.left() + 2, record.rect.right() - 2)
        if record.path.contains(QPointF(x + 0.5, y + 0.5))
    ]
    assert any(color.alpha() == 255 and color.red() == 255 for color in painted)


def test_overlapping_flash_phases_retain_all_active_holes(nested_form, qapp):
    host, manager = nested_form
    for name in ("alpha", "beta"):
        manager.update_parameter(name, 10)
    qapp.processEvents()
    overlay = WindowFlashOverlay.get_for_window(host)
    colors = {
        "child.alpha": QColor(255, 0, 0, 64),
        "child.beta": QColor(0, 0, 255, 255),
    }
    overlay._rebuild_geometry_cache([], set(colors))
    records, _ = overlay._visible_paint_records(set(colors), colors=colors)
    assert len(records) == 1
    assert records[0].color == colors["child.beta"]
    for name in ("alpha", "beta"):
        widget = manager.widgets[name]
        assert not records[0].path.contains(QPointF(widget.mapTo(host, widget.rect().center())))

    remaining, _ = overlay._visible_paint_records({"child.beta"}, colors=colors)
    alpha = manager.widgets["alpha"]
    beta = manager.widgets["beta"]
    assert remaining[0].path.contains(QPointF(alpha.mapTo(host, alpha.rect().center())))
    assert not remaining[0].path.contains(QPointF(beta.mapTo(host, beta.rect().center())))


def test_materialized_leaf_retires_its_lazy_container_mask(nested_form, qapp):
    host, manager = nested_form
    manager.update_parameter("alpha", 10)
    qapp.processEvents()
    overlay = WindowFlashOverlay.get_for_window(host)
    container = overlay._elements["child.alpha"][0].container
    root = manager.form_tree.root()
    root.register_flash_groupbox("child.alpha", container)
    assert len(overlay._elements["child.alpha"]) == 2
    root.register_flash_leaf(
        "child.alpha", container, manager.widgets["alpha"], manager.labels["alpha"]
    )
    assert len(overlay._elements["child.alpha"]) == 1
    overlay._rebuild_geometry_cache([], {"child.alpha"})
    records, _ = overlay._visible_paint_records({"child.alpha"})
    sibling = manager.widgets["beta"]
    assert records[0].path.contains(QPointF(sibling.mapTo(host, sibling.rect().center())))
