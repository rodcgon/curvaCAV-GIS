# -*- coding: utf-8 -*-
def classFactory(iface):
    from .curvacav_gis import CurvaCAVGIS
    return CurvaCAVGIS(iface)
