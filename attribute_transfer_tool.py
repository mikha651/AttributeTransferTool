from qgis.PyQt.QtWidgets import (
    QAction, QWidget, QComboBox, QPushButton, QVBoxLayout,
    QLabel, QMessageBox, QTextEdit, QSizePolicy
)
from qgis.PyQt.QtCore import Qt
from qgis.core import *
from qgis.utils import iface


class AttributeTransferToolPlugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        self.action = QAction("🧲 Attribute Transfer Tool", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("Attribute Transfer Tool", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu("Attribute Transfer Tool", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.tool_window = AttributeTransferToolUI()
        self.tool_window.show()
        self.tool_window.raise_()
        self.tool_window.activateWindow()


class AttributeTransferToolUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🧲 Attribute Transfer Tool")
        self.setMinimumWidth(400)

        self.source_layer_combo = QComboBox()
        self.source_field_combo = QComboBox()
        self.target_layer_combo = QComboBox()
        self.target_field_combo = QComboBox()
        self.match_type_combo = QComboBox()
        self.run_button = QPushButton("Transfer Attributes")
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(180)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Source Layer"))
        layout.addWidget(self.source_layer_combo)
        layout.addWidget(QLabel("Field to Transfer"))
        layout.addWidget(self.source_field_combo)
        layout.addWidget(QLabel("Target Layer"))
        layout.addWidget(self.target_layer_combo)
        layout.addWidget(QLabel("Field to Receive"))
        layout.addWidget(self.target_field_combo)
        layout.addWidget(QLabel("Matching Rule"))
        layout.addWidget(self.match_type_combo)
        layout.addWidget(self.run_button)
        layout.addWidget(QLabel("🔍 Log"))
        layout.addWidget(self.log_output)
        self.setLayout(layout)

        self.match_type_combo.addItems([
            "intersects", "contains", "within", "touches", "equals", "vertex match"
        ])

        self.populate_layers()
        self.source_layer_combo.currentIndexChanged.connect(self.populate_source_fields)
        self.target_layer_combo.currentIndexChanged.connect(self.populate_target_fields)
        self.run_button.clicked.connect(self.run_transfer)

    def populate_layers(self):
        self.source_layer_combo.clear()
        self.target_layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                self.source_layer_combo.addItem(layer.name(), layer)
                self.target_layer_combo.addItem(layer.name(), layer)
        self.populate_source_fields()
        self.populate_target_fields()

    def populate_source_fields(self):
        self.source_field_combo.clear()
        layer = self.source_layer_combo.currentData()
        if layer:
            for field in layer.fields():
                self.source_field_combo.addItem(field.name(), field)

    def populate_target_fields(self):
        self.target_field_combo.clear()
        layer = self.target_layer_combo.currentData()
        if layer:
            for field in layer.fields():
                self.target_field_combo.addItem(field.name(), field)

    def log(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible()

    def run_transfer(self):
        self.log_output.clear()
        source_layer = self.source_layer_combo.currentData()
        target_layer = self.target_layer_combo.currentData()
        source_field = self.source_field_combo.currentData()
        target_field = self.target_field_combo.currentData()
        match_type = self.match_type_combo.currentText()

        if not source_layer or not target_layer or not source_field or not target_field:
            QMessageBox.warning(self, "Missing Selection", "Please select all required inputs.")
            return

        if source_field.type() != target_field.type():
            self.log("❌ Field type mismatch.")
            QMessageBox.critical(self, "Field Type Mismatch", "Source and target fields must have the same type.")
            return

        if not target_layer.isEditable():
            self.log("❌ Editing is not enabled for target layer.")
            QMessageBox.critical(self, "Editing Mode Required", "Please toggle editing ON for the target layer.")
            return

        self.log("🧠 Building spatial index on source layer...")
        spatial_index = QgsSpatialIndex(source_layer.getFeatures())
        updated_ids = []
        updated_count = 0

        self.log("🚀 Starting attribute transfer process...")
        for target_feat in target_layer.getFeatures():
            tid = target_feat.id()
            target_geom = target_feat.geometry()
            candidate_ids = spatial_index.intersects(target_geom.boundingBox())
            matches = []

            for source_feat in source_layer.getFeatures(QgsFeatureRequest().setFilterFids(candidate_ids)):
                source_geom = source_feat.geometry()
                match = False

                if match_type == "intersects" and target_geom.intersects(source_geom):
                    match = True
                elif match_type == "contains" and source_geom.contains(target_geom):
                    match = True
                elif match_type == "within" and source_geom.within(target_geom):
                    match = True
                elif match_type == "touches" and target_geom.touches(source_geom):
                    match = True
                elif match_type == "equals" and target_geom.equals(source_geom):
                    match = True
                elif match_type == "vertex match":
                    if target_geom.type() == QgsWkbTypes.PointGeometry:
                        pt = QgsPointXY(target_geom.asPoint())
                        for v in source_geom.vertices():
                            if pt.distance(QgsPointXY(v)) < 0.001:
                                match = True
                                break

                if match:
                    matches.append(source_feat)

            if len(matches) == 0:
                self.log(f"⚠️ Feature ID {tid} skipped: no match found.")
            elif len(matches) > 1:
                self.log(f"⚠️ Feature ID {tid} skipped: multiple ({len(matches)}) matches found.")
            else:
                value = matches[0][source_field.name()]
                idx = target_layer.fields().indexFromName(target_field.name())
                success = target_layer.changeAttributeValue(tid, idx, value)
                if success:
                    updated_ids.append(tid)
                    updated_count += 1
                    self.log(f"✅ Feature ID {tid} updated with value '{value}'")
                else:
                    self.log(f"❌ Failed to update Feature ID {tid}.")

        target_layer.selectByIds(updated_ids)
        self.log(f"\n🎯 Transfer completed: {updated_count} features updated.")
        QMessageBox.information(self, "Transfer Complete", f"{updated_count} features updated and selected.")
