import signal
import sys

from PySide6.QtCore import Qt, QEvent, QObject, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QActionGroup, QAction, QSinglePointEvent, QImage, \
    QColorConstants, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, \
    QColorDialog, QSpinBox, QFormLayout, QFrame, QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem, \
    QGraphicsEllipseItem, QGraphicsLineItem, QFileDialog, QGraphicsItem, QLabel, QDialog, QSlider

from task_png import Image, Pixel, write_png

DEFAULT_FILL = QColor(200, 200, 255)
DEFAULT_STROKE = QColor(30, 30, 30)
DEFAULT_STROKE_WIDTH = 2


class CanvasView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent: QObject = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)


class ShapeFactory:
    @staticmethod
    def rect(
            x: int = 10, y: int = 10, w: int = 100, h: int = 70, fill: QColor = DEFAULT_FILL,
            stroke: QColor = DEFAULT_STROKE, sw: int = DEFAULT_STROKE_WIDTH,
    ) -> QGraphicsRectItem:
        r = QGraphicsRectItem(0, 0, w, h)
        r.setBrush(QBrush(fill))
        p = QPen(stroke)
        p.setWidth(sw)
        r.setPen(p)
        r.setPos(x, y)
        r.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        return r

    @staticmethod
    def ellipse(
            x: int = 10, y: int = 10, w: int = 100, h: int = 70, fill: QColor = DEFAULT_FILL,
            stroke: QColor = DEFAULT_STROKE, sw: int = DEFAULT_STROKE_WIDTH,
    ) -> QGraphicsEllipseItem:
        e = QGraphicsEllipseItem(0, 0, w, h)
        e.setBrush(QBrush(fill))
        p = QPen(stroke)
        p.setWidth(sw)
        e.setPen(p)
        e.setPos(x, y)
        e.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        return e

    @staticmethod
    def line(
            x1: int = 10, y1: int = 10, x2: int = 150, y2: int = 10, stroke: QColor = DEFAULT_STROKE,
            sw: int = DEFAULT_STROKE_WIDTH,
    ) -> QGraphicsLineItem:
        dx = x2 - x1
        dy = y2 - y1
        l = QGraphicsLineItem(0, 0, dx, dy)
        p = QPen(stroke)
        p.setWidth(sw)
        l.setPen(p)
        l.setPos(x1, y1)
        l.setFlags(
            QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsLineItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsLineItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        return l


class PropertyEditor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._item = None
        self._lock = False

        layout = QFormLayout(self)

        self.spin_x = QSpinBox()
        self.spin_x.setRange(-10000, 10000)
        self.spin_x.valueChanged.connect(self._on_position_changed)
        layout.addRow("X:", self.spin_x)

        self.spin_y = QSpinBox()
        self.spin_y.setRange(-10000, 10000)
        self.spin_y.valueChanged.connect(self._on_position_changed)
        layout.addRow("Y:", self.spin_y)

        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 10000)
        self.spin_w.valueChanged.connect(self._on_size_changed)
        layout.addRow("Width:", self.spin_w)

        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 10000)
        self.spin_h.valueChanged.connect(self._on_size_changed)
        layout.addRow("Height:", self.spin_h)

        self.spin_rot = QSpinBox()
        self.spin_rot.setRange(-360, 360)
        self.spin_rot.valueChanged.connect(self._on_rotation_changed)
        layout.addRow("Rotation:", self.spin_rot)

        self.spin_sw = QSpinBox()
        self.spin_sw.setRange(0, 50)
        self.spin_sw.valueChanged.connect(self._on_stroke_changed)
        layout.addRow("Stroke Width:", self.spin_sw)

        self.btn_fill = QPushButton("Fill Color")
        self.btn_fill.clicked.connect(self._choose_fill)
        layout.addRow("Fill:", self.btn_fill)

        self.btn_stroke = QPushButton("Stroke Color")
        self.btn_stroke.clicked.connect(self._choose_stroke)
        layout.addRow("Stroke:", self.btn_stroke)

        self.sat_slider = QSlider()
        self.sat_slider.setOrientation(Qt.Orientation.Horizontal)
        self.sat_slider.setMinimum(0)
        self.sat_slider.setMaximum(255)
        self.sat_slider.setValue(0)
        self.sat_slider.setSingleStep(1)
        self.sat_slider.valueChanged.connect(self._on_sat_changed)
        layout.addRow("Sat:", self.sat_slider)

        self.lum_slider = QSlider()
        self.lum_slider.setOrientation(Qt.Orientation.Horizontal)
        self.lum_slider.setMinimum(0)
        self.lum_slider.setMaximum(255)
        self.lum_slider.setValue(0)
        self.lum_slider.setSingleStep(1)
        self.lum_slider.valueChanged.connect(self._on_lum_changed)
        layout.addRow("Lum:", self.lum_slider)

    def set_item(self, item: QGraphicsItem | None) -> None:
        self._item = item
        self._update_ui()

    def get_item(self) -> QGraphicsItem | None:
        return self._item

    def _update_ui(self) -> None:
        self._lock = True

        if self._item is None:
            for w in self.findChildren(QWidget):
                w.setEnabled(False)
            self._lock = False
            return

        for w in self.findChildren(QWidget):
            w.setEnabled(True)

        pos = self._item.pos()
        self.spin_x.setValue(int(pos.x()))
        self.spin_y.setValue(int(pos.y()))
        self.spin_rot.setValue(int(self._item.rotation()))

        if hasattr(self._item, "pen"):
            self.spin_sw.setValue(self._item.pen().width())

        if isinstance(self._item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            r = self._item.rect()
            self.spin_w.setValue(int(r.width()))
            self.spin_h.setValue(int(r.height()))
            self.spin_h.setEnabled(True)
        elif isinstance(self._item, QGraphicsLineItem):
            line = self._item.line()
            length = int((line.dx()**2 + line.dy()**2) ** 0.5)
            self.spin_w.setValue(length)
            self.spin_h.setValue(0)
            self.spin_h.setEnabled(False)

        if isinstance(self._item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            h, s, l, *_ = self._item.brush().color().getHsl()
            self.sat_slider.setValue(s)
            self.lum_slider.setValue(l)
        elif isinstance(self._item, QGraphicsLineItem):
            h, s, l, *_ = self._item.pen().color().getHsl()
            self.sat_slider.setValue(s)
            self.lum_slider.setValue(l)

        self._lock = False

    def _on_position_changed(self) -> None:
        if self._lock or self._item is None:
            return
        self._item.setPos(self.spin_x.value(), self.spin_y.value())

    def _on_size_changed(self) -> None:
        if self._lock or self._item is None:
            return
        w, h = self.spin_w.value(), self.spin_h.value()

        if isinstance(self._item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            self._item.setRect(0, 0, w, h)
        elif isinstance(self._item, QGraphicsLineItem):
            self._item.setLine(0, 0, w, 0)

    def _on_rotation_changed(self) -> None:
        if self._lock or self._item is None:
            return
        self._item.setRotation(self.spin_rot.value())

    def _on_stroke_changed(self) -> None:
        if self._lock or self._item is None:
            return
        pen = self._item.pen()
        pen.setWidth(self.spin_sw.value())
        self._item.setPen(pen)

    def _choose_fill(self) -> None:
        if self._item is None:
            return
        col = QColorDialog.getColor(DEFAULT_FILL, self, "Choose Fill")
        if col.isValid():
            if hasattr(self._item, "setBrush"):
                self._item.setBrush(QBrush(col))

    def _choose_stroke(self) -> None:
        if self._item is None:
            return
        col = QColorDialog.getColor(DEFAULT_STROKE, self, "Choose Stroke")
        if col.isValid():
            pen = self._item.pen()
            pen.setColor(col)
            self._item.setPen(pen)

    def _on_sat_changed(self) -> None:
        if self._lock or self._item is None:
            return

        if isinstance(self._item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            h, _, l, *_ = self._item.brush().color().getHsl()
            new_color = QColor.fromHsl(h, self.sat_slider.value(), l)
            self._item.setBrush(QBrush(new_color))
        elif isinstance(self._item, QGraphicsLineItem):
            h, _, l, *_ = self._item.pen().color().getHsl()
            new_color = QColor.fromHsl(h, self.sat_slider.value(), l)
            self._item.setPen(QPen(new_color))

    def _on_lum_changed(self) -> None:
        if self._lock or self._item is None:
            return

        if isinstance(self._item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            h, s, _, *_ = self._item.brush().color().getHsl()
            new_color = QColor.fromHsl(h, s, self.lum_slider.value())
            self._item.setBrush(QBrush(new_color))
        elif isinstance(self._item, QGraphicsLineItem):
            h, s, _, *_ = self._item.pen().color().getHsl()
            new_color = QColor.fromHsl(h, s, self.lum_slider.value())
            self._item.setPen(QPen(new_color))


class HSLCompareWidget(QDialog):
    def __init__(self, parent: QObject | None=None) -> None:
        super().__init__(parent)

        self.originalLabel = QLabel()
        self.hslLabel = QLabel()

        self.originalLabel.setScaledContents(True)
        self.hslLabel.setScaledContents(True)

        layout = QHBoxLayout()
        layout.addWidget(self.originalLabel)
        layout.addWidget(self.hslLabel)
        self.setLayout(layout)

    def setImage(self, img: QImage) -> None:
        if img.isNull():
            return

        self.originalLabel.setPixmap(QPixmap.fromImage(img))

        hsl_img = self.convertToHSLPreview(img)
        self.hslLabel.setPixmap(QPixmap.fromImage(hsl_img))

    @staticmethod
    def convertToHSLPreview(img: QImage) -> QImage:
        w, h = img.width(), img.height()
        preview = QImage(w, h, QImage.Format.Format_RGB888)

        for y in range(h):
            for x in range(w):
                rgbColor = img.pixelColor(x, y)
                previewColor = rgbColor.toHsl()
                preview.setPixelColor(x, y, previewColor)

        return preview


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pz1")
        self.resize(1100, 700)

        self.scene = QGraphicsScene(0, 0, 800, 600)
        self.view = CanvasView(self.scene)

        self.prop = PropertyEditor()

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(self.view, 1)

        side = QFrame()
        side.setFrameShape(QFrame.Shape.StyledPanel)
        side_lay = QVBoxLayout(side)
        side_lay.addWidget(self.prop)
        layout.addWidget(side, 0)

        self.setCentralWidget(container)

        self._create_toolbar()
        self._create_menu()
        self._create_actions()

        self.current_tool = None
        self.scene.selectionChanged.connect(self._on_selection)

        self.view.viewport().installEventFilter(self)

    def _create_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        act_export_png = QAction("Export PNG", self)
        act_export_png.triggered.connect(self.export_png)
        file_menu.addAction(act_export_png)

        act_export_svg = QAction("Export SVG", self)
        act_export_svg.triggered.connect(self.export_svg)
        file_menu.addAction(act_export_svg)

        file_menu.addSeparator()

        act_compare_cmyk = QAction("Load from SVG", self)
        act_compare_cmyk.triggered.connect(self.load_svg)
        file_menu.addAction(act_compare_cmyk)

        file_menu.addSeparator()

        act_compare_cmyk = QAction("Compare RBG and HSL", self)
        act_compare_cmyk.triggered.connect(self.compare_cmyk)
        file_menu.addAction(act_compare_cmyk)

    def _render(self) -> QImage:
        image = QImage(int(self.scene.width()), int(self.scene.height()), QImage.Format.Format_RGB888)
        image.fill(QColorConstants.White)
        painter = QPainter(image)

        old_sel = self.scene.selectedItems()
        self.scene.clearSelection()
        self.prop.set_item(None)

        self.scene.render(painter)

        for item in reversed(old_sel):
            item.setSelected(True)
            self.prop.set_item(item)

        painter.end()

        return image

    def export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG Files (*.png)")
        if not path:
            return

        img = Image(int(self.scene.width()), int(self.scene.height()))

        pixmap = self._render()

        pixels = [
            [Pixel(*img.bg_color) for _ in range(img.width)]
            for _ in range(img.height)
        ]

        for i in range(int(self.scene.width())):
            for j in range(int(self.scene.height())):
                pix = pixmap.pixelColor(i, j)
                pixels[j][i].set(pix.red(), pix.green(), pix.blue())

        write_png(path, pixels)

        QMessageBox.information(self, "Export - PNG", f"PNG export completed.\nSaved to:\n{path}")

    def export_svg(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export SVG", "", "SVG Files (*.svg)")
        if path:
            QMessageBox.information(self, "Export - SVG", f"SVG export not implemented.\nWould save to:\n{path}")

    def load_svg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load SVG", "", "SVG Files (*.svg)")
        if path:
            QMessageBox.information(self, "Import - SVG", f"SVG loading not implemented.\nWould load:\n{path}")

    def compare_cmyk(self) -> None:
        w = HSLCompareWidget()
        w.setImage(self._render())
        w.resize(800, 400)
        w.setModal(True)
        w.exec()

    def _create_toolbar(self) -> None:
        tb = QToolBar("Tools")
        self.addToolBar(tb)

        group = QActionGroup(self)
        group.setExclusive(True)

        act_select = QAction("Select", self, checkable=True)
        act_select.setChecked(True)
        act_select.triggered.connect(lambda: self._set_tool(None))
        group.addAction(act_select)
        tb.addAction(act_select)

        act_rect = QAction("Rect", self, checkable=True)
        act_rect.triggered.connect(lambda: self._set_tool("rect"))
        group.addAction(act_rect)
        tb.addAction(act_rect)

        act_ellipse = QAction("Ellipse", self, checkable=True)
        act_ellipse.triggered.connect(lambda: self._set_tool("ellipse"))
        group.addAction(act_ellipse)
        tb.addAction(act_ellipse)

        act_line = QAction("Line", self, checkable=True)
        act_line.triggered.connect(lambda: self._set_tool("line"))
        group.addAction(act_line)
        tb.addAction(act_line)

        tb.addSeparator()

        act_delete = QAction("Delete", self)
        act_delete.triggered.connect(self.delete_selected)
        tb.addAction(act_delete)

    def _create_actions(self) -> None:
        act_delete = QAction(self)
        act_delete.setShortcut(Qt.Key.Key_Delete)
        act_delete.triggered.connect(self.delete_selected)
        self.addAction(act_delete)

    def _set_tool(self, tool: str | None) -> None:
        self.current_tool = tool
        if tool is None:
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.view.setCursor(Qt.CursorShape.CrossCursor)

    def eventFilter(self, obj: QWidget, event: QSinglePointEvent) -> bool:
        if obj is self.view.viewport():
            if event.type() == QEvent.Type.MouseButtonPress and \
                    event.button() == Qt.MouseButton.LeftButton and self.current_tool:
                pos = self.view.mapToScene(event.position().toPoint())
                self._add_shape_at(pos)
                return True
        return super().eventFilter(obj, event)

    def _add_shape_at(self, pos: QPointF) -> None:
        x, y = int(pos.x()), int(pos.y())
        if self.current_tool == "rect":
            item = ShapeFactory.rect(x, y, 120, 80)
        elif self.current_tool == "ellipse":
            item = ShapeFactory.ellipse(x, y, 120, 80)
        elif self.current_tool == "line":
            item = ShapeFactory.line(x, y, x + 120, y)
        else:
            return
        self.scene.addItem(item)
        self.scene.clearSelection()
        item.setSelected(True)

    def _on_selection(self) -> None:
        sel = self.scene.selectedItems()
        if sel:
            self.prop.set_item(sel[0])
        else:
            self.prop.set_item(None)

    def delete_selected(self) -> None:
        for item in self.scene.selectedItems():
            self.scene.removeItem(item)
        self.prop.set_item(None)


def main() -> None:
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
