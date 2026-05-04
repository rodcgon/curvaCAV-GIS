# -*- coding: utf-8 -*-
import os
import math
import tempfile
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np
import pandas as pd
from numpy import arange
from osgeo import gdal
from qgis import processing
from qgis.core import QgsReferencedRectangle


def _clip_by_polygon(mdt_layer, polygon_layer):
    result = processing.run('gdal:cliprasterbymasklayer', {
        'INPUT': mdt_layer, 'MASK': polygon_layer,
        'SOURCE_CRS': None, 'TARGET_CRS': None, 'NODATA': None,
        'ALPHA_BAND': False, 'CROP_TO_CUTLINE': True, 'KEEP_RESOLUTION': True,
        'SET_RESOLUTION': False, 'X_RESOLUTION': None, 'Y_RESOLUTION': None,
        'MULTITHREADING': False, 'OPTIONS': '', 'DATA_TYPE': 0,
        'EXTRA': '', 'OUTPUT': 'TEMPORARY_OUTPUT',
    })
    return result['OUTPUT']


def _clip_by_feature(mdt_layer, polygon_layer, feature):
    """Clip raster by a single feature from a polygon layer."""
    from qgis.core import QgsVectorLayer
    crs_str = polygon_layer.crs().authid()
    temp = QgsVectorLayer(
        'Polygon?crs={}'.format(crs_str), 'temp_feature_clip', 'memory'
    )
    temp.dataProvider().addFeature(feature)
    temp.updateExtents()
    result = processing.run('gdal:cliprasterbymasklayer', {
        'INPUT': mdt_layer, 'MASK': temp,
        'SOURCE_CRS': None, 'TARGET_CRS': None, 'NODATA': None,
        'ALPHA_BAND': False, 'CROP_TO_CUTLINE': True, 'KEEP_RESOLUTION': True,
        'SET_RESOLUTION': False, 'X_RESOLUTION': None, 'Y_RESOLUTION': None,
        'MULTITHREADING': False, 'OPTIONS': '', 'DATA_TYPE': 0,
        'EXTRA': '', 'OUTPUT': 'TEMPORARY_OUTPUT',
    })
    return result['OUTPUT']


def _clip_by_extent(mdt_layer, extent, crs):
    """Clip raster by a QgsRectangle + QgsCoordinateReferenceSystem extent."""
    ref_rect = QgsReferencedRectangle(extent, crs)
    result = processing.run('gdal:cliprasterbyextent', {
        'INPUT': mdt_layer,
        'PROJWIN': ref_rect,
        'OVERCRS': True,
        'NODATA': None,
        'OPTIONS': '',
        'DATA_TYPE': 0,
        'EXTRA': '',
        'OUTPUT': 'TEMPORARY_OUTPUT',
    })
    return result['OUTPUT']


def get_raster_stats(mdt_layer, area_mode=0, polygon_layer=None,
                     iface=None, drawn_rect=None, drawn_crs=None,
                     selected_feature=None):
    source = mdt_layer
    if area_mode == 1 and polygon_layer is not None:
        if selected_feature is not None:
            source = _clip_by_feature(mdt_layer, polygon_layer, selected_feature)
        else:
            source = _clip_by_polygon(mdt_layer, polygon_layer)
    elif area_mode == 2 and iface is not None:
        ext = iface.mapCanvas().extent()
        crs = iface.mapCanvas().mapSettings().destinationCrs()
        source = _clip_by_extent(mdt_layer, ext, crs)
    elif area_mode == 3 and drawn_rect is not None and drawn_crs is not None:
        source = _clip_by_extent(mdt_layer, drawn_rect, drawn_crs)

    res_stat = processing.run('native:rasterlayerstatistics', {
        'INPUT': source, 'BAND': 1, 'OUTPUT_HTML_FILE': 'TEMPORARY_OUTPUT',
    })
    return {
        'min': float(res_stat['MIN']),
        'max': float(res_stat['MAX']),
        'resx': float(mdt_layer.rasterUnitsPerPixelX()),
        'resy': float(mdt_layer.rasterUnitsPerPixelY()),
    }


def _read_array(raster_source):
    ds = gdal.Open(raster_source)
    if ds is None:
        raise ValueError('Could not open raster: {}'.format(raster_source))
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray().astype(float)
    nodata = band.GetNoDataValue()
    gt = ds.GetGeoTransform()
    area_pixel = abs(gt[1] * gt[5])
    ds = None
    return arr, nodata, area_pixel


def _nice_tick_interval(data_range, target_ticks=10):
    if data_range <= 0:
        return 1.0
    raw = data_range / target_ticks
    magnitude = math.pow(10, math.floor(math.log10(raw)))
    residual = raw / magnitude
    if residual <= 1.0:
        nice = 1.0
    elif residual <= 2.0:
        nice = 2.0
    elif residual <= 2.5:
        nice = 2.5
    elif residual <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * magnitude


def plota(df_in, fo):
    x1 = df_in['AREA_m2'].values / 10000.0
    x2 = df_in['VOLUME_m3'].values / 1000000.0
    y = df_in.index.values.astype(float)
    if len(y) == 0:
        return
    y_range = float(y.max() - y.min())
    maj_interval = _nice_tick_interval(y_range, target_ticks=10)
    min_interval = maj_interval / 5.0

    fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True, figsize=(9, 7), dpi=150)
    fig.patch.set_facecolor('white')

    ax1.plot(x1, y, color='#1f78ff', linewidth=2)
    ax1.set_xlim(left=0)
    ax1.set_ylim(bottom=y.min(), top=y.max())
    ax1.invert_xaxis()
    ax1.set_ylabel('Cota', fontsize=11)
    ax1.set_xlabel('Area (ha)', fontsize=10)
    ax1.yaxis.set_major_locator(mticker.MultipleLocator(maj_interval))
    ax1.yaxis.set_minor_locator(mticker.MultipleLocator(min_interval))
    ax1.tick_params(axis='y', which='major', labelsize=9)
    ax1.grid(which='major', alpha=0.7, linestyle='-')
    ax1.grid(which='minor', alpha=0.25, linestyle='--')

    ax2.plot(x2, y, color='#0f2740', linewidth=2)
    ax2.set_xlim(left=0)
    ax2.set_xlabel('Volume (hm3)', fontsize=10)
    ax2.tick_params(axis='y', labelleft=False)
    ax2.yaxis.set_major_locator(mticker.MultipleLocator(maj_interval))
    ax2.yaxis.set_minor_locator(mticker.MultipleLocator(min_interval))
    ax2.grid(which='major', alpha=0.7, linestyle='-')
    ax2.grid(which='minor', alpha=0.25, linestyle='--')

    plt.subplots_adjust(wspace=0.04, hspace=0.0)

    watermark = 'Plugin curvaCAV-GIS - QGIS\nrcghidro@gmail.com'
    fig.text(
        0.87, 0.15, watermark,
        fontsize=15, color='0.3', alpha=0.20,
        ha='right', va='bottom', rotation=0,
        transform=fig.transFigure, fontweight='normal', linespacing=1.8,
    )

    plt.savefig(fo, bbox_inches='tight')
    plt.close(fig)


def run_cav(iface, mdt_layer, area_mode, polygon_layer,
            cota_ini, cota_max, incr, output_folder, make_plot=True,
            drawn_rect=None, drawn_crs=None, selected_feature=None):
    if mdt_layer is None:
        raise ValueError('MDT invalido.')
    if cota_max < cota_ini:
        raise ValueError('Cota maxima deve ser >= cota inicial.')
    if incr <= 0:
        raise ValueError('Incremento deve ser maior que zero.')
    if area_mode == 1 and polygon_layer is None:
        raise ValueError('Selecione um layer poligonal valido.')
    if area_mode == 3 and (drawn_rect is None or drawn_crs is None):
        raise ValueError('Desenhe um retangulo no mapa antes de calcular.')

    raster_source = mdt_layer.dataProvider().dataSourceUri()
    if area_mode == 1:
        if selected_feature is not None:
            raster_source = _clip_by_feature(mdt_layer, polygon_layer, selected_feature)
        else:
            raster_source = _clip_by_polygon(mdt_layer, polygon_layer)
    elif area_mode == 2:
        ext = iface.mapCanvas().extent()
        crs = iface.mapCanvas().mapSettings().destinationCrs()
        raster_source = _clip_by_extent(mdt_layer, ext, crs)
    elif area_mode == 3:
        raster_source = _clip_by_extent(mdt_layer, drawn_rect, drawn_crs)

    arr, nodata, area_pixel = _read_array(raster_source)
    if nodata is None:
        mask_valid = np.isfinite(arr)
    else:
        mask_valid = np.isfinite(arr) & (arr != nodata)

    if not np.any(mask_valid):
        raise ValueError('Nenhum pixel valido encontrado na area considerada.')

    lst_cotas = list(arange(cota_ini, cota_max + incr / 2.0, incr))
    dic_area = {}
    dic_vol = {}
    for ct in lst_cotas:
        mask_ct = (arr <= ct) & mask_valid
        dic_vol[ct] = float(np.where(mask_ct, (ct - arr) * area_pixel, 0.0).sum())
        dic_area[ct] = float(np.where(mask_ct, area_pixel, 0.0).sum())

    stamp = datetime.now().strftime('_%d%b%Y_%Hh%Mm')
    base_name = mdt_layer.name()
    df = pd.DataFrame({'AREA_m2': pd.Series(dic_area), 'VOLUME_m3': pd.Series(dic_vol)})
    df.index.name = 'COTA'

    csv_path = None
    if output_folder:
        os.makedirs(output_folder, exist_ok=True)
        csv_path = os.path.join(
            output_folder, '{}_CURVA_CAV{}.csv'.format(base_name, stamp)
        )
        df.to_csv(csv_path, encoding='utf-8-sig')

    plot_path = None
    if make_plot:
        if output_folder:
            plot_path = os.path.join(
                output_folder, '{}_CAV_PLOT{}.jpg'.format(base_name, stamp)
            )
        else:
            plot_path = os.path.join(
                tempfile.gettempdir(), '{}_CAV_PLOT{}.jpg'.format(base_name, stamp)
            )
        plota(df, plot_path)

    area_labels = {
        0: 'todo o MDT',
        2: 'extent atual do mapa',
        3: 'retangulo desenhado',
    }
    area_label = area_labels.get(area_mode, 'todo o MDT')
    if area_mode == 1 and polygon_layer is not None:
        area_label = 'layer poligonal: {}'.format(polygon_layer.name())

    return {
        'message': 'CAV calculada com sucesso usando {}.'.format(area_label),
        'csv': csv_path,
        'plot': plot_path,
        'df': df,
    }
