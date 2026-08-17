# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from .curvacav_dialog import CurvaCAVDialog


class CurvaCAVGIS:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None

    def tr(self, message):
        return QCoreApplication.translate('CurvaCAVGIS', message)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(QIcon(icon_path), self.tr('curvaCAV-GIS'), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.tr('curvaCAV-GIS'), self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginMenu(self.tr('curvaCAV-GIS'), self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        dlg = CurvaCAVDialog(self.iface, self.iface.mainWindow())
        dlg.exec()
