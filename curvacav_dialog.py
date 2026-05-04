# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtCore import Qt, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon, QPixmap, QColor, QPalette
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSplitter, QStyledItemDelegate, QStyle, QTabWidget,
    QTableView, QTextEdit, QVBoxLayout, QWidget, QDoubleSpinBox,
    QHeaderView, QSizePolicy,
)
from qgis.core import (
    QgsProject, QgsMapLayer, QgsWkbTypes,
    QgsRectangle, QgsFeatureRequest, QgsCoordinateTransform,
)
from qgis.gui import QgsMapTool, QgsRubberBand
from .cav_core import get_raster_stats, run_cav
import pandas as pd


# ── Ferramenta: selecionar feature unica no mapa ──────────────────────────────

class FeaturePickTool(QgsMapTool):
    def __init__(self, canvas, layer, callback, iface=None):
        super().__init__(canvas)
        self._canvas = canvas
        self._layer  = layer
        self._callback = callback
        self._iface  = iface

    def canvasReleaseEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        radius = self._canvas.extent().width() * 0.005
        rect = QgsRectangle(
            point.x() - radius, point.y() - radius,
            point.x() + radius, point.y() + radius,
        )
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        layer_crs  = self._layer.crs()
        if canvas_crs != layer_crs:
            tr = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            rect = tr.transformBoundingBox(rect)
        feats = list(self._layer.getFeatures(QgsFeatureRequest().setFilterRect(rect).setLimit(1)))
        if feats:
            self._callback(feats[0])
        elif self._iface:
            self._iface.messageBar().pushWarning(
                'curvaCAV-GIS', 'Nenhuma feature encontrada. Clique sobre o poligono desejado.'
            )

    def deactivate(self):
        super().deactivate()


# ── Ferramenta: retangulo desenhado no mapa ───────────────────────────────────

class RectangleMapTool(QgsMapTool):
    def __init__(self, canvas, on_done):
        super().__init__(canvas)
        self._canvas  = canvas
        self._on_done = on_done
        self._start   = None
        self._drawing = False
        self._rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self._rb.setColor(QColor(31, 120, 255, 160))
        self._rb.setFillColor(QColor(31, 120, 255, 40))
        self._rb.setWidth(2)

    def canvasPressEvent(self, event):
        from qgis.core import QgsPointXY
        self._start   = self.toMapCoordinates(event.pos())
        self._drawing = True
        self._rb.reset(QgsWkbTypes.PolygonGeometry)

    def canvasMoveEvent(self, event):
        if not self._drawing or self._start is None:
            return
        from qgis.core import QgsPointXY
        end  = self.toMapCoordinates(event.pos())
        rect = QgsRectangle(self._start, end)
        self._rb.reset(QgsWkbTypes.PolygonGeometry)
        for pt in [
            QgsPointXY(rect.xMinimum(), rect.yMinimum()),
            QgsPointXY(rect.xMaximum(), rect.yMinimum()),
            QgsPointXY(rect.xMaximum(), rect.yMaximum()),
            QgsPointXY(rect.xMinimum(), rect.yMaximum()),
        ]:
            self._rb.addPoint(pt, False)
        self._rb.closePoints(True)

    def canvasReleaseEvent(self, event):
        if not self._drawing or self._start is None:
            return
        end = self.toMapCoordinates(event.pos())
        self._drawing = False
        self._rb.reset()
        rect = QgsRectangle(self._start, end)
        crs  = self._canvas.mapSettings().destinationCrs()
        self._on_done(rect, crs)

    def deactivate(self):
        self._rb.reset()
        super().deactivate()


# ── Pandas model ──────────────────────────────────────────────────────────────

class PandasModel(QAbstractTableModel):
    HEADERS = ['Cota', 'Area (m2)', 'Volume (m3)']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = pd.DataFrame()

    def rowCount(self, parent=None):   return len(self._df)
    def columnCount(self, parent=None): return 3

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        row, col = index.row(), index.column()
        val = self._df.index[row] if col == 0 else self._df.iat[row, col - 1]
        return '{:.3f}'.format(val) if isinstance(val, float) else str(val)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        return self.HEADERS[section] if orientation == Qt.Horizontal else str(section + 1)

    def setDataFrame(self, df):
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    def toClipboardText(self):
        lines = ['\t'.join(self.HEADERS)]
        for i in range(len(self._df)):
            lines.append('\t'.join([
                '{:.3f}'.format(self._df.index[i]),
                '{:.3f}'.format(self._df.iat[i, 0]),
                '{:.3f}'.format(self._df.iat[i, 1]),
            ]))
        return '\n'.join(lines)


# ── Delegate customizado para itens dos ComboBox ──────────────────────────────
# Para ajustar cores do dropdown, edite as constantes abaixo:

class ComboItemDelegate(QStyledItemDelegate):
    BG_NORMAL   = QColor('#ffffff')
    FG_NORMAL   = QColor('#17324d')
    BG_SELECTED = QColor('#1f78ff')
    FG_SELECTED = QColor('#ffffff')

    def paint(self, painter, option, index):
        painter.save()
        active = bool(
            (option.state & QStyle.State_Selected) or
            (option.state & QStyle.State_MouseOver)
        )
        painter.fillRect(option.rect, self.BG_SELECTED if active else self.BG_NORMAL)
        painter.setPen(self.FG_SELECTED if active else self.FG_NORMAL)
        text = index.data(Qt.DisplayRole) or ''
        painter.drawText(option.rect.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return sh.__class__(sh.width(), max(sh.height(), 26))


# ── Label com imagem auto-escalavel ──────────────────────────────────────────

class ScaledImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.setText('Nenhum grafico gerado ainda.')

    def setSourcePixmap(self, pixmap):
        self._source_pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._source_pixmap and not self._source_pixmap.isNull():
            self.setPixmap(self._source_pixmap.scaled(
                self.width() - 4, self.height() - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


# ── Dialog principal ──────────────────────────────────────────────────────────

class CurvaCAVDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface          = iface
        self.plugin_dir     = os.path.dirname(__file__)
        self._drawn_rect    = None
        self._drawn_crs     = None
        self._prev_map_tool = None
        self._selected_feature = None
        self._current_plot_pixmap = None
        self._last_df       = None
        self._last_plot_path = None

        self.setWindowTitle('curvaCAV-GIS  v1.0.5')
        self.setMinimumWidth(700)
        self.setMinimumHeight(660)
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._populate_layers()
        self._fix_combos()
        self._update_area_state()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tab_calc    = QWidget()
        self.tab_results = QWidget()
        self.tab_about   = QWidget()
        self.tabs.addTab(self.tab_calc,    'Calculo')
        self.tabs.addTab(self.tab_results, 'Resultados')
        self.tabs.addTab(self.tab_about,   'Sobre')
        self._build_calc_tab()
        self._build_results_tab()
        self._build_about_tab()

    def _build_calc_tab(self):
        layout = QVBoxLayout(self.tab_calc)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title    = QLabel('Curva Cota-Area-Volume')
        title.setObjectName('titleLabel')
        subtitle = QLabel('Calcule a CAV a partir de um MDT. Pasta de saida disponivel na aba Resultados.')
        subtitle.setWordWrap(True)
        subtitle.setObjectName('subtitleLabel')
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName('card')
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 14, 14, 14)
        card_lay.setSpacing(10)
        layout.addWidget(card)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        card_lay.addLayout(form)

        # MDT
        self.cmbMdtLayer = QComboBox()
        form.addRow('MDT raster', self.cmbMdtLayer)

        # Area
        self.cmbAreaMode = QComboBox()
        self.cmbAreaMode.addItems([
            'Usar todo o MDT',
            'Usar layer poligonal',
            'Usar extent atual do mapa',
            'Desenhar retangulo no mapa',
        ])
        self.cmbAreaMode.setCurrentIndex(2)
        form.addRow('Area considerada', self.cmbAreaMode)

        # Layer poligonal
        self.cmbPolygonLayer = QComboBox()
        form.addRow('Layer poligonal', self.cmbPolygonLayer)

        # Selecao de feature unica
        feat_row = QWidget()
        feat_lay = QHBoxLayout(feat_row)
        feat_lay.setContentsMargins(0, 0, 0, 0)
        feat_lay.setSpacing(8)
        self.btnSelectFeature = QPushButton('Selecionar feature no mapa')
        self.btnSelectFeature.setObjectName('drawButton')
        self.lblSelectedFeature = QLabel('Nenhuma feature selecionada.')
        self.lblSelectedFeature.setObjectName('infoLabel')
        self.lblSelectedFeature.setWordWrap(True)
        feat_lay.addWidget(self.btnSelectFeature)
        feat_lay.addWidget(self.lblSelectedFeature, 1)
        form.addRow('Feature', feat_row)

        # Retangulo
        draw_row = QWidget()
        draw_lay = QHBoxLayout(draw_row)
        draw_lay.setContentsMargins(0, 0, 0, 0)
        draw_lay.setSpacing(8)
        self.btnDrawRect = QPushButton('Ativar ferramenta de retangulo')
        self.btnDrawRect.setObjectName('drawButton')
        self.lblDrawnRect = QLabel('Nenhum retangulo desenhado.')
        self.lblDrawnRect.setObjectName('infoLabel')
        draw_lay.addWidget(self.btnDrawRect)
        draw_lay.addWidget(self.lblDrawnRect, 1)
        form.addRow('Retangulo', draw_row)

        # Informacoes — carregar sob demanda (nao automatico)
        info_row = QWidget()
        info_lay = QHBoxLayout(info_row)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(8)
        self.btnLoadStats = QPushButton('Carregar estatisticas')
        self.btnLoadStats.setObjectName('copyButton')
        self.lblRasterInfo = QLabel('Clique para carregar informacoes do MDT selecionado.')
        self.lblRasterInfo.setObjectName('infoLabel')
        self.lblRasterInfo.setWordWrap(True)
        info_lay.addWidget(self.btnLoadStats)
        info_lay.addWidget(self.lblRasterInfo, 1)
        form.addRow('Informacoes', info_row)

        # Cotas
        self.dblCotaIni = QDoubleSpinBox()
        self.dblCotaIni.setDecimals(3)
        self.dblCotaIni.setRange(-1e9, 1e9)
        form.addRow('Cota inicial', self.dblCotaIni)

        self.dblCotaMax = QDoubleSpinBox()
        self.dblCotaMax.setDecimals(3)
        self.dblCotaMax.setRange(-1e9, 1e9)
        form.addRow('Cota maxima', self.dblCotaMax)

        self.dblIncremento = QDoubleSpinBox()
        self.dblIncremento.setDecimals(3)
        self.dblIncremento.setRange(0.001, 1e9)
        self.dblIncremento.setValue(1.0)
        form.addRow('Incremento', self.dblIncremento)

        # Acoes
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.chkPlot = QCheckBox('Gerar grafico')
        self.chkPlot.setChecked(True)
        self.btnRun = QPushButton('Calcular')
        self.btnRun.setObjectName('primaryButton')
        actions.addWidget(self.chkPlot)
        actions.addStretch(1)
        actions.addWidget(self.btnRun)
        card_lay.addLayout(actions)

        # Log
        self.txtLog = QTextEdit()
        self.txtLog.setReadOnly(True)
        self.txtLog.setPlaceholderText('Log da execucao...')
        self.txtLog.setMaximumHeight(90)
        layout.addWidget(self.txtLog)

    def _build_results_tab(self):
        layout = QVBoxLayout(self.tab_results)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        # Grafico
        plot_widget = QWidget()
        plot_lay = QVBoxLayout(plot_widget)
        plot_lay.setContentsMargins(0, 0, 0, 0)
        plot_lay.setSpacing(6)
        plot_header = QHBoxLayout()
        lbl_pt = QLabel('Grafico CAV')
        lbl_pt.setObjectName('titleLabel')
        self.btnSavePlot  = QPushButton('Salvar...')
        self.btnSavePlot.setObjectName('copyButton')
        self.btnCopyPlot  = QPushButton('Copiar imagem')
        self.btnCopyPlot.setObjectName('copyButton')
        plot_header.addWidget(lbl_pt)
        plot_header.addStretch(1)
        plot_header.addWidget(self.btnSavePlot)
        plot_header.addWidget(self.btnCopyPlot)
        plot_lay.addLayout(plot_header)
        self.lblPlot = ScaledImageLabel()
        self.lblPlot.setFrameShape(QFrame.StyledPanel)
        plot_lay.addWidget(self.lblPlot)
        splitter.addWidget(plot_widget)

        # Tabela
        tbl_widget = QWidget()
        tbl_lay = QVBoxLayout(tbl_widget)
        tbl_lay.setContentsMargins(0, 0, 0, 0)
        tbl_lay.setSpacing(6)
        tbl_header = QHBoxLayout()
        lbl_tt = QLabel('Tabela Cota-Area-Volume')
        lbl_tt.setObjectName('titleLabel')
        self.btnCopyTable = QPushButton('Copiar para Clipboard')
        self.btnCopyTable.setObjectName('copyButton')
        tbl_header.addWidget(lbl_tt)
        tbl_header.addStretch(1)
        tbl_header.addWidget(self.btnCopyTable)
        tbl_lay.addLayout(tbl_header)
        self.tblResults = QTableView()
        self.tblModel   = PandasModel()
        self.tblResults.setModel(self.tblModel)
        self.tblResults.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tblResults.setAlternatingRowColors(True)
        tbl_lay.addWidget(self.tblResults)
        splitter.addWidget(tbl_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        # ── Pasta de saida (abaixo do splitter) ───────────────────────────
        save_card = QFrame()
        save_card.setObjectName('card')
        save_lay = QVBoxLayout(save_card)
        save_lay.setContentsMargins(12, 10, 12, 10)
        save_lay.setSpacing(8)

        lbl_save = QLabel('Exportar resultados')
        lbl_save.setObjectName('titleLabel')
        save_lay.addWidget(lbl_save)

        folder_row = QWidget()
        folder_lay = QHBoxLayout(folder_row)
        folder_lay.setContentsMargins(0, 0, 0, 0)
        folder_lay.setSpacing(8)
        self.txtOutputFolder = QLineEdit()
        self.txtOutputFolder.setPlaceholderText('(opcional) selecione a pasta para salvar CSV e grafico')
        self.btnBrowse = QPushButton('Selecionar...')
        folder_lay.addWidget(self.txtOutputFolder, 1)
        folder_lay.addWidget(self.btnBrowse)
        save_lay.addWidget(folder_row)

        self.btnSaveResults = QPushButton('Salvar resultados na pasta')
        self.btnSaveResults.setObjectName('primaryButton')
        save_lay.addWidget(self.btnSaveResults)
        layout.addWidget(save_card)

    def _build_about_tab(self):
        layout = QVBoxLayout(self.tab_about)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        card = QFrame()
        card.setObjectName('card')
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(20, 20, 20, 20)
        card_lay.setSpacing(10)
        layout.addWidget(card)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setPixmap(QIcon(os.path.join(self.plugin_dir, 'icon.png')).pixmap(72, 72))
        card_lay.addWidget(icon_label)
        t = QLabel('curvaCAV-GIS')
        t.setAlignment(Qt.AlignCenter)
        t.setObjectName('titleLabel')
        card_lay.addWidget(t)
        info = QLabel(
            '<div style="text-align:center;">' +
            '<p>Versao 1.0.5 &nbsp;|&nbsp; 04/05/2026</p>' +
            '<p style="color:#526476;">Para duvidas, sugestoes, bug reports, treinamentos e plugins sob medida, favor entrar em contato.</p>' +
            '<p><b>Autor:</b> Rodrigo Goncalves</p>' +
            '<p><b>Email:</b> <a href="mailto:rcghidro@gmail.com">rcghidro@gmail.com</a></p>' +
            '<p style="color:#526476;">Plugin para calculo de curvas Cota-Area-Volume a partir de MDT.</p>' +
            '<p style="color:#526476;">O autor nao se responsabiliza por resultados, decisoes de projeto ou danos decorrentes do uso deste plugin.</p>' +
            '<p style="color:#526476;">Se o plugin foi util para voce, <a href="https://rodcgon.github.io/donate/">considere fazer uma doacao para o projeto.</a></p>' +
            '</div>'
        )
        info.setOpenExternalLinks(True)
        info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        card_lay.addWidget(info)
        card_lay.addStretch(1)
        layout.addStretch(1)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.btnBrowse.clicked.connect(self._choose_folder)
        self.btnRun.clicked.connect(self._run)
        self.btnLoadStats.clicked.connect(self._update_raster_info)
        # Mudanca de MDT/area/poligono nao dispara calculo automatico
        # (pode ser lento para rasters grandes — usuario clica em "Carregar estatisticas")
        self.cmbMdtLayer.currentIndexChanged.connect(self._on_mdt_changed)
        self.cmbAreaMode.currentIndexChanged.connect(self._on_area_changed)
        self.cmbPolygonLayer.currentIndexChanged.connect(self._on_poly_changed)
        self.btnDrawRect.clicked.connect(self._activate_draw_tool)
        self.btnSelectFeature.clicked.connect(self._activate_feature_pick)
        self.btnCopyTable.clicked.connect(self._copy_table)
        self.btnSavePlot.clicked.connect(self._save_plot)
        self.btnCopyPlot.clicked.connect(self._copy_plot)
        self.btnSaveResults.clicked.connect(self._save_results)

    def _on_mdt_changed(self):
        self.lblRasterInfo.setText('MDT alterado. Clique em "Carregar estatisticas" para atualizar.')

    def _on_area_changed(self):
        self._update_area_state()
        self.lblRasterInfo.setText('Area alterada. Clique em "Carregar estatisticas" para atualizar.')

    def _on_poly_changed(self):
        self._selected_feature = None
        self.lblSelectedFeature.setText('Nenhuma feature selecionada.')
        self.lblRasterInfo.setText('Layer alterado. Clique em "Carregar estatisticas" para atualizar.')

    # ── Style ─────────────────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background: #f6f8fb; }
            QTabWidget::pane { border: 1px solid #d8e1ee; border-radius: 6px; background: white; }
            QTabBar::tab {
                background: #eaf0f7; color: #324255;
                border: 1px solid #d8e1ee;
                padding: 7px 16px; min-width: 80px; margin-right: 3px;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                font-size: 12px; font-weight: 400;
            }
            QTabBar::tab:selected {
                background: white; color: #0f2740;
                border-bottom: 2px solid #1f78ff;
                padding: 7px 16px; min-width: 80px;
                font-size: 12px; font-weight: 400;
            }
            QFrame#card { background: white; border: 1px solid #dde5f0; border-radius: 12px; }
            QLabel#titleLabel { font-size: 13px; font-weight: 700; color: #17324d; }
            QLabel#subtitleLabel, QLabel#infoLabel { color: #526476; font-size: 11px; }
            QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit {
                background: white; border: 1px solid #cad5e2;
                border-radius: 8px; padding: 6px 8px; }
            QTableView { border: 1px solid #cad5e2; border-radius: 8px;
                         alternate-background-color: #f0f5fc; }
            QPushButton { border: 1px solid #c7d3e2; border-radius: 8px;
                          background: white; padding: 7px 14px; color: #17324d; }
            QPushButton#primaryButton { background: #1f78ff; border: 1px solid #1f78ff;
                                        color: white; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #1468e1; }
            QPushButton#copyButton { background: #f0f5fc; border: 1px solid #aec6e8; padding: 5px 10px; }
            QPushButton#copyButton:hover { background: #dce8f7; }
            QPushButton#drawButton { background: #e8f4e8; border: 1px solid #7ec87e;
                                     color: #1a5c1a; padding: 5px 10px; }
            QPushButton#drawButton:hover { background: #d0ebd0; }
        """)

    def _fix_combos(self):
        delegate = ComboItemDelegate(self)
        for combo in [self.cmbMdtLayer, self.cmbAreaMode, self.cmbPolygonLayer]:
            combo.setItemDelegate(delegate)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _populate_layers(self):
        self.cmbMdtLayer.clear()
        self.cmbPolygonLayer.clear()
        self.cmbPolygonLayer.addItem('Nenhum', None)
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.RasterLayer:
                self.cmbMdtLayer.addItem(layer.name(), layer.id())
            elif (layer.type() == QgsMapLayer.VectorLayer and
                  QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry):
                self.cmbPolygonLayer.addItem(layer.name(), layer.id())

    def _update_area_state(self):
        mode = self.cmbAreaMode.currentIndex()
        self.cmbPolygonLayer.setEnabled(mode == 1)
        self.btnSelectFeature.setEnabled(mode == 1)
        self.lblSelectedFeature.setVisible(mode == 1)
        self.btnDrawRect.setEnabled(mode == 3)
        self.lblDrawnRect.setVisible(mode == 3)

    def _update_raster_info(self):
        layer_id = self.cmbMdtLayer.currentData()
        if not layer_id:
            self.lblRasterInfo.setText('Selecione um MDT.')
            return
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            self.lblRasterInfo.setText('MDT invalido.')
            return
        mode = self.cmbAreaMode.currentIndex()
        poly_layer = None
        if mode == 1:
            pid = self.cmbPolygonLayer.currentData()
            poly_layer = QgsProject.instance().mapLayer(pid) if pid else None
        if mode == 3 and self._drawn_rect is None:
            self.lblRasterInfo.setText('Desenhe um retangulo no mapa para carregar estatisticas.')
            return
        try:
            stats = get_raster_stats(
                layer, area_mode=mode, polygon_layer=poly_layer,
                iface=self.iface, drawn_rect=self._drawn_rect, drawn_crs=self._drawn_crs,
                selected_feature=self._selected_feature,
            )
            self.lblRasterInfo.setText(
                'Cota min: {:.3f} | Cota max: {:.3f} | Res. X: {:.5f} | Res. Y: {:.5f}'.format(
                    stats['min'], stats['max'], stats['resx'], stats['resy'])
            )
            self.dblCotaIni.setValue(stats['min'])
            self.dblCotaMax.setValue(stats['max'])
        except Exception as e:
            self.lblRasterInfo.setText('Erro ao ler estatisticas: {}'.format(e))

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Pasta para salvar resultados')
        if folder:
            self.txtOutputFolder.setText(folder)

    # ── Feature pick ──────────────────────────────────────────────────────────

    def _activate_feature_pick(self):
        pid = self.cmbPolygonLayer.currentData()
        if not pid:
            QMessageBox.warning(self, 'curvaCAV-GIS', 'Selecione um layer poligonal primeiro.')
            return
        layer = QgsProject.instance().mapLayer(pid)
        if layer is None:
            QMessageBox.warning(self, 'curvaCAV-GIS', 'Layer poligonal invalido.')
            return
        self._prev_map_tool = self.iface.mapCanvas().mapTool()
        tool = FeaturePickTool(self.iface.mapCanvas(), layer, self._on_feature_picked, self.iface)
        self.iface.mapCanvas().setMapTool(tool)
        self._pick_tool = tool
        self.iface.messageBar().pushInfo('curvaCAV-GIS', 'Clique sobre a feature desejada no mapa.')
        self.hide()

    def _on_feature_picked(self, feature):
        self._selected_feature = feature
        self.lblSelectedFeature.setText(
            'Feature ID: {} | Area: {:.2f} m2'.format(
                feature.id(),
                feature.geometry().area() if feature.geometry() else 0.0
            )
        )
        if self._prev_map_tool:
            self.iface.mapCanvas().setMapTool(self._prev_map_tool)
        self.show()
        self.raise_()
        self.activateWindow()
        self._update_raster_info()

    # ── Rectangle draw ────────────────────────────────────────────────────────

    def _activate_draw_tool(self):
        self._prev_map_tool = self.iface.mapCanvas().mapTool()
        tool = RectangleMapTool(self.iface.mapCanvas(), self._on_rectangle_drawn)
        self.iface.mapCanvas().setMapTool(tool)
        self._rect_tool = tool
        self.hide()

    def _on_rectangle_drawn(self, rect, crs):
        self._drawn_rect = rect
        self._drawn_crs  = crs
        self.lblDrawnRect.setText(
            'Rect: ({:.2f},{:.2f})-({:.2f},{:.2f})'.format(
                rect.xMinimum(), rect.yMinimum(),
                rect.xMaximum(), rect.yMaximum()
            )
        )
        if self._prev_map_tool:
            self.iface.mapCanvas().setMapTool(self._prev_map_tool)
        self.show(); self.raise_(); self.activateWindow()
        self._update_raster_info()

    # ── Acoes grafico ─────────────────────────────────────────────────────────

    def _save_plot(self):
        if self._current_plot_pixmap is None:
            QMessageBox.information(self, 'curvaCAV-GIS', 'Nenhum grafico disponivel. Execute o calculo primeiro.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Salvar Grafico', 'grafico_cav', 'JPEG (*.jpg);;PNG (*.png);;BMP (*.bmp)')
        if path:
            self._current_plot_pixmap.save(path)
            QMessageBox.information(self, 'curvaCAV-GIS', 'Grafico salvo em:\n{}'.format(path))

    def _copy_plot(self):
        if self._current_plot_pixmap is None:
            QMessageBox.information(self, 'curvaCAV-GIS', 'Nenhum grafico disponivel. Execute o calculo primeiro.')
            return
        QApplication.clipboard().setPixmap(self._current_plot_pixmap)
        QMessageBox.information(self, 'curvaCAV-GIS', 'Imagem do grafico copiada para o clipboard.')

    def _copy_table(self):
        text = self.tblModel.toClipboardText()
        if not text.strip():
            QMessageBox.information(self, 'curvaCAV-GIS', 'Nenhum dado para copiar. Execute o calculo primeiro.')
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, 'curvaCAV-GIS', 'Tabela copiada. Cole no Excel com Ctrl+V.')

    def _save_results(self):
        """Salva CSV e grafico na pasta definida (pode ser chamado apos o calculo)."""
        folder = self.txtOutputFolder.text().strip()
        if not folder:
            QMessageBox.warning(self, 'curvaCAV-GIS', 'Selecione a pasta de saida antes de salvar.')
            return
        if self._last_df is None:
            QMessageBox.warning(self, 'curvaCAV-GIS', 'Nenhum resultado disponivel. Execute o calculo primeiro.')
            return
        import os
        from datetime import datetime
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.now().strftime('_%d%b%Y_%Hh%Mm')
        saved = []
        csv_path = os.path.join(folder, 'curvaCAV{}.csv'.format(stamp))
        self._last_df.to_csv(csv_path, encoding='utf-8-sig')
        saved.append('CSV: {}'.format(csv_path))
        if self._current_plot_pixmap and not self._current_plot_pixmap.isNull():
            jpg_path = os.path.join(folder, 'curvaCAV_grafico{}.jpg'.format(stamp))
            self._current_plot_pixmap.save(jpg_path)
            saved.append('Grafico: {}'.format(jpg_path))
        msg = 'Resultados salvos:\n' + '\n'.join(saved)
        self.txtLog.append(msg)
        QMessageBox.information(self, 'curvaCAV-GIS', msg)

    # ── Execucao ──────────────────────────────────────────────────────────────

    def _run(self):
        mdt_layer_id = self.cmbMdtLayer.currentData()
        if not mdt_layer_id:
            QMessageBox.warning(self, 'curvaCAV-GIS', 'Selecione um MDT.')
            return
        mode = self.cmbAreaMode.currentIndex()
        poly_layer = None
        if mode == 1:
            pid = self.cmbPolygonLayer.currentData()
            poly_layer = QgsProject.instance().mapLayer(pid) if pid else None
            if poly_layer is None:
                QMessageBox.warning(self, 'curvaCAV-GIS', 'Selecione um layer poligonal valido.')
                return
            if self._selected_feature is None:
                resp = QMessageBox.question(
                    self, 'curvaCAV-GIS',
                    'Nenhuma feature selecionada. Deseja usar o layer poligonal inteiro?',
                    QMessageBox.Yes | QMessageBox.No
                )
                if resp != QMessageBox.Yes:
                    return
        if mode == 3 and self._drawn_rect is None:
            QMessageBox.warning(self, 'curvaCAV-GIS', 'Desenhe um retangulo no mapa antes de calcular.')
            return

        params = {
            'iface':            self.iface,
            'mdt_layer':        QgsProject.instance().mapLayer(mdt_layer_id),
            'area_mode':        mode,
            'polygon_layer':    poly_layer,
            'cota_ini':         self.dblCotaIni.value(),
            'cota_max':         self.dblCotaMax.value(),
            'incr':             self.dblIncremento.value(),
            'output_folder':    None,
            'make_plot':        self.chkPlot.isChecked(),
            'drawn_rect':       self._drawn_rect,
            'drawn_crs':        self._drawn_crs,
            'selected_feature': self._selected_feature,
        }
        self.txtLog.append('Calculando...')
        try:
            result = run_cav(**params)
            self.txtLog.append(result['message'])
            self._last_df        = result.get('df')
            self._last_plot_path = result.get('plot')
            if self._last_df is not None:
                self.tblModel.setDataFrame(self._last_df)
            plot_path = result.get('plot')
            if plot_path and os.path.exists(plot_path):
                pix = QPixmap(plot_path)
                if not pix.isNull():
                    self._current_plot_pixmap = pix
                    self.lblPlot.setSourcePixmap(pix)
                else:
                    self.lblPlot.setText('Nao foi possivel carregar o grafico.')
            else:
                self.lblPlot.setText('Grafico nao gerado.')
            self.tabs.setCurrentWidget(self.tab_results)
            QMessageBox.information(self, 'curvaCAV-GIS', 'Calculo concluido. Use "Salvar resultados" para exportar.')
        except Exception as e:
            self.txtLog.append('Erro: {}'.format(e))
            QMessageBox.critical(self, 'curvaCAV-GIS', 'Erro: {}'.format(e))
