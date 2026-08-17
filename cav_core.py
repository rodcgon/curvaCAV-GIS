# -*- coding: utf-8 -*-
import math
import os
import tempfile
from datetime import datetime

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from numpy import arange
from osgeo import gdal
from qgis import processing
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsReferencedRectangle,
    QgsVectorLayer,
)


CLIP_NODATA = -99999.0


def _clip_by_polygon(mdt_layer, polygon_layer,
                     nodata_value=CLIP_NODATA):
    """Recorta o MDT usando todos os polígonos da camada."""
    result = processing.run('gdal:cliprasterbymasklayer', {
        'INPUT': mdt_layer,
        'MASK': polygon_layer,
        'SOURCE_CRS': None,
        'TARGET_CRS': None,
        'NODATA': nodata_value,
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'KEEP_RESOLUTION': True,
        'SET_RESOLUTION': False,
        'X_RESOLUTION': None,
        'Y_RESOLUTION': None,
        'MULTITHREADING': False,
        'OPTIONS': '',
        'DATA_TYPE': 0,
        'EXTRA': '',
        'OUTPUT': 'TEMPORARY_OUTPUT',
    })

    return result['OUTPUT']


def _clip_by_feature(mdt_layer, polygon_layer, feature,
                     nodata_value=CLIP_NODATA):
    """Recorta o MDT usando exclusivamente uma feature poligonal."""
    if feature is None:
        raise ValueError('Nenhuma feature foi selecionada.')

    if not feature.hasGeometry():
        raise ValueError(
            'A feature selecionada nao possui geometria valida.'
        )

    crs_str = polygon_layer.crs().authid()

    temp_layer = QgsVectorLayer(
        'Polygon?crs={}'.format(crs_str),
        'temp_feature_clip',
        'memory',
    )

    provider = temp_layer.dataProvider()

    if not provider.addFeature(feature):
        raise ValueError(
            'Nao foi possivel adicionar a feature a mascara temporaria.'
        )

    temp_layer.updateExtents()

    result = processing.run('gdal:cliprasterbymasklayer', {
        'INPUT': mdt_layer,
        'MASK': temp_layer,
        'SOURCE_CRS': None,
        'TARGET_CRS': None,
        'NODATA': nodata_value,
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'KEEP_RESOLUTION': True,
        'SET_RESOLUTION': False,
        'X_RESOLUTION': None,
        'Y_RESOLUTION': None,
        'MULTITHREADING': False,
        'OPTIONS': '',
        'DATA_TYPE': 0,
        'EXTRA': '',
        'OUTPUT': 'TEMPORARY_OUTPUT',
    })

    return result['OUTPUT']


def _clip_by_extent(mdt_layer, extent, crs,
                    nodata_value=CLIP_NODATA):
    """Recorta o MDT por uma extensão e CRS."""
    ref_rect = QgsReferencedRectangle(extent, crs)

    result = processing.run('gdal:cliprasterbyextent', {
        'INPUT': mdt_layer,
        'PROJWIN': ref_rect,
        'OVERCRS': True,
        'NODATA': nodata_value,
        'OPTIONS': '',
        'DATA_TYPE': 0,
        'EXTRA': '',
        'OUTPUT': 'TEMPORARY_OUTPUT',
    })

    return result['OUTPUT']


def _get_source_nodata(mdt_layer):
    """Obtém o NODATA original da banda 1, quando disponível."""
    provider = mdt_layer.dataProvider()

    if provider is None:
        raise ValueError('MDT sem dataProvider valido.')

    try:
        value = provider.sourceNoDataValue(1)
        value = float(value)

        if not np.isfinite(value):
            return None

        return value

    except (AttributeError, TypeError, ValueError):
        return None


def _read_array(raster_source, nodata_hint=None):
    """Lê banda 1 e retorna array, NODATA e área do pixel."""
    dataset = gdal.Open(raster_source)

    if dataset is None:
        raise ValueError(
            'Nao foi possivel abrir o raster: {}'.format(raster_source)
        )

    band = dataset.GetRasterBand(1)

    if band is None:
        dataset = None
        raise ValueError('O raster nao possui uma banda 1 valida.')

    arr = band.ReadAsArray().astype(float)

    nodata = band.GetNoDataValue()

    if nodata is None:
        nodata = nodata_hint

    if nodata is not None:
        try:
            nodata = float(nodata)
        except (TypeError, ValueError):
            nodata = nodata_hint

    geotransform = dataset.GetGeoTransform()
    area_pixel = abs(geotransform[1] * geotransform[5])

    dataset = None

    return arr, nodata, area_pixel


def _build_valid_mask(arr, raster_nodata=None,
                      source_nodata=None,
                      clip_nodata=CLIP_NODATA):
    """
    Cria máscara de pixels válidos, excluindo valores NODATA,
    NaN, infinito e pixels externos aos recortes.
    """
    mask_valid = np.isfinite(arr)

    nodata_values = [
        raster_nodata,
        source_nodata,
        clip_nodata,
    ]

    for value in nodata_values:
        if value is None:
            continue

        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        if not np.isfinite(value):
            continue

        mask_valid &= ~np.isclose(arr, value)

    return mask_valid


def _get_raster_source(mdt_layer, area_mode,
                       polygon_layer=None,
                       iface=None,
                       drawn_rect=None,
                       drawn_crs=None,
                       selected_feature=None,
                       nodata_value=CLIP_NODATA):
    """Retorna o raster inteiro ou o raster temporariamente recortado."""
    if area_mode == 0:
        return mdt_layer.dataProvider().dataSourceUri()

    if area_mode == 1:
        if polygon_layer is None:
            raise ValueError('Selecione um layer poligonal valido.')

        if selected_feature is not None:
            return _clip_by_feature(
                mdt_layer,
                polygon_layer,
                selected_feature,
                nodata_value,
            )

        return _clip_by_polygon(
            mdt_layer,
            polygon_layer,
            nodata_value,
        )

    if area_mode == 2:
        if iface is None:
            raise ValueError(
                'Interface do QGIS necessaria para usar '
                'o extent atual do mapa.'
            )

        extent = iface.mapCanvas().extent()
        crs = iface.mapCanvas().mapSettings().destinationCrs()

        return _clip_by_extent(
            mdt_layer,
            extent,
            crs,
            nodata_value,
        )

    if area_mode == 3:
        if drawn_rect is None or drawn_crs is None:
            raise ValueError(
                'Desenhe um retangulo no mapa antes de calcular.'
            )

        return _clip_by_extent(
            mdt_layer,
            drawn_rect,
            drawn_crs,
            nodata_value,
        )

    raise ValueError(
        'Modo de area invalido: {}.'.format(area_mode)
    )


def get_raster_stats(mdt_layer, area_mode=0,
                     polygon_layer=None,
                     iface=None,
                     drawn_rect=None,
                     drawn_crs=None,
                     selected_feature=None):
    """Calcula mínimo, máximo e resolução sobre pixels válidos."""
    if mdt_layer is None:
        raise ValueError('Selecione um MDT raster valido.')

    source_nodata = _get_source_nodata(mdt_layer)

    raster_source = _get_raster_source(
        mdt_layer=mdt_layer,
        area_mode=area_mode,
        polygon_layer=polygon_layer,
        iface=iface,
        drawn_rect=drawn_rect,
        drawn_crs=drawn_crs,
        selected_feature=selected_feature,
        nodata_value=CLIP_NODATA,
    )

    arr, raster_nodata, area_pixel = _read_array(
        raster_source,
        nodata_hint=CLIP_NODATA,
    )

    mask_valid = _build_valid_mask(
        arr,
        raster_nodata=raster_nodata,
        source_nodata=source_nodata,
        clip_nodata=CLIP_NODATA,
    )

    if not np.any(mask_valid):
        raise ValueError(
            'Nenhum pixel valido encontrado na area considerada.'
        )

    values = arr[mask_valid]

    return {
        'min': float(np.min(values)),
        'max': float(np.max(values)),
        'resx': float(mdt_layer.rasterUnitsPerPixelX()),
        'resy': float(mdt_layer.rasterUnitsPerPixelY()),
        'area_pixel': float(area_pixel),
    }


def _nice_tick_interval(data_range, target_ticks=10):
    if data_range <= 0:
        return 1.0

    raw = data_range / target_ticks
    magnitude = math.pow(
        10,
        math.floor(math.log10(raw)),
    )

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
    maj_interval = _nice_tick_interval(
        y_range,
        target_ticks=10,
    )
    min_interval = maj_interval / 5.0

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        sharey=True,
        figsize=(9, 7),
        dpi=150,
    )

    fig.patch.set_facecolor('white')

    ax1.plot(
        x1,
        y,
        color='#1f78ff',
        linewidth=2,
    )

    ax1.set_xlim(left=0)
    ax1.set_ylim(
        bottom=y.min(),
        top=y.max(),
    )

    ax1.invert_xaxis()
    ax1.set_ylabel('Cota', fontsize=11)
    ax1.set_xlabel('Area (ha)', fontsize=10)

    ax1.yaxis.set_major_locator(
        mticker.MultipleLocator(maj_interval)
    )

    ax1.yaxis.set_minor_locator(
        mticker.MultipleLocator(min_interval)
    )

    ax1.tick_params(
        axis='y',
        which='major',
        labelsize=9,
    )

    ax1.grid(
        which='major',
        alpha=0.7,
        linestyle='-',
    )

    ax1.grid(
        which='minor',
        alpha=0.25,
        linestyle='--',
    )

    ax2.plot(
        x2,
        y,
        color='#0f2740',
        linewidth=2,
    )

    ax2.set_xlim(left=0)
    ax2.set_xlabel('Volume (hm3)', fontsize=10)

    ax2.tick_params(
        axis='y',
        labelleft=False,
    )

    ax2.yaxis.set_major_locator(
        mticker.MultipleLocator(maj_interval)
    )

    ax2.yaxis.set_minor_locator(
        mticker.MultipleLocator(min_interval)
    )

    ax2.grid(
        which='major',
        alpha=0.7,
        linestyle='-',
    )

    ax2.grid(
        which='minor',
        alpha=0.25,
        linestyle='--',
    )

    plt.subplots_adjust(
        wspace=0.04,
        hspace=0.0,
    )

    watermark = (
        'Plugin curvaCAV-GIS - QGIS\n'
        'rcghidro@gmail.com'
    )

    fig.text(
        0.87,
        0.15,
        watermark,
        fontsize=15,
        color='0.3',
        alpha=0.20,
        ha='right',
        va='bottom',
        rotation=0,
        transform=fig.transFigure,
        fontweight='normal',
        linespacing=1.8,
    )

    plt.savefig(
        fo,
        bbox_inches='tight',
    )

    plt.close(fig)


def run_cav(iface, mdt_layer, area_mode,
            polygon_layer, cota_ini, cota_max,
            incr, output_folder,
            make_plot=True,
            drawn_rect=None,
            drawn_crs=None,
            selected_feature=None):
    """Calcula a curva Cota-Área-Volume."""
    if mdt_layer is None:
        raise ValueError('MDT invalido.')

    if cota_max < cota_ini:
        raise ValueError(
            'Cota maxima deve ser >= cota inicial.'
        )

    if incr <= 0:
        raise ValueError(
            'Incremento deve ser maior que zero.'
        )

    if area_mode == 1 and polygon_layer is None:
        raise ValueError(
            'Selecione um layer poligonal valido.'
        )

    if area_mode == 2 and iface is None:
        raise ValueError(
            'Interface do QGIS necessaria para usar '
            'o extent atual do mapa.'
        )

    if area_mode == 3:
        if drawn_rect is None or drawn_crs is None:
            raise ValueError(
                'Desenhe um retangulo no mapa antes de calcular.'
            )

    source_nodata = _get_source_nodata(mdt_layer)

    raster_source = _get_raster_source(
        mdt_layer=mdt_layer,
        area_mode=area_mode,
        polygon_layer=polygon_layer,
        iface=iface,
        drawn_rect=drawn_rect,
        drawn_crs=drawn_crs,
        selected_feature=selected_feature,
        nodata_value=CLIP_NODATA,
    )

    arr, raster_nodata, area_pixel = _read_array(
        raster_source,
        nodata_hint=CLIP_NODATA,
    )

    mask_valid = _build_valid_mask(
        arr,
        raster_nodata=raster_nodata,
        source_nodata=source_nodata,
        clip_nodata=CLIP_NODATA,
    )

    if not np.any(mask_valid):
        raise ValueError(
            'Nenhum pixel valido encontrado na area considerada.'
        )

    lst_cotas = list(
        arange(
            cota_ini,
            cota_max + incr / 2.0,
            incr,
        )
    )

    dic_area = {}
    dic_vol = {}

    for cota in lst_cotas:
        mask_cota = mask_valid & (arr <= cota)

        dic_area[cota] = float(
            mask_cota.sum() * area_pixel
        )

        dic_vol[cota] = float(
            np.where(
                mask_cota,
                (cota - arr) * area_pixel,
                0.0,
            ).sum()
        )

    stamp = datetime.now().strftime(
        '_%d%b%Y_%Hh%Mm'
    )

    base_name = mdt_layer.name()

    df = pd.DataFrame({
        'AREA_m2': pd.Series(dic_area),
        'VOLUME_m3': pd.Series(dic_vol),
    })

    df.index.name = 'COTA'

    csv_path = None

    if output_folder:
        os.makedirs(
            output_folder,
            exist_ok=True,
        )

        csv_path = os.path.join(
            output_folder,
            '{}_CURVA_CAV{}.csv'.format(
                base_name,
                stamp,
            ),
        )

        df.to_csv(
            csv_path,
            encoding='utf-8-sig',
        )

    plot_path = None

    if make_plot:
        if output_folder:
            plot_path = os.path.join(
                output_folder,
                '{}_CAV_PLOT{}.jpg'.format(
                    base_name,
                    stamp,
                ),
            )
        else:
            plot_path = os.path.join(
                tempfile.gettempdir(),
                '{}_CAV_PLOT{}.jpg'.format(
                    base_name,
                    stamp,
                ),
            )

        plota(
            df,
            plot_path,
        )

    area_labels = {
        0: 'todo o MDT',
        2: 'extent atual do mapa',
        3: 'retangulo desenhado',
    }

    area_label = area_labels.get(
        area_mode,
        'todo o MDT',
    )

    if area_mode == 1 and polygon_layer is not None:
        if selected_feature is not None:
            area_label = (
                'feature {} do layer poligonal: {}'
            ).format(
                selected_feature.id(),
                polygon_layer.name(),
            )
        else:
            area_label = (
                'layer poligonal: {}'
            ).format(
                polygon_layer.name()
            )

    return {
        'message': (
            'CAV calculada com sucesso usando {}.'
        ).format(area_label),
        'csv': csv_path,
        'plot': plot_path,
        'df': df,
        'raster_source': raster_source,
        'source_nodata': source_nodata,
    }


def gerar_poligono_na(raster_source, na_value,
                      source_nodata=None,
                      layer_name='Poligono_NA'):
    """
    Gera uma camada de memória com os pixels de elevação
    menor ou igual ao nível d'água selecionado.
    """
    try:
        na_value = float(na_value)
    except (TypeError, ValueError):
        raise ValueError(
            'A cota selecionada nao e numerica.'
        )

    arr, raster_nodata, area_pixel = _read_array(
        raster_source,
        nodata_hint=CLIP_NODATA,
    )

    mask_valid = _build_valid_mask(
        arr,
        raster_nodata=raster_nodata,
        source_nodata=source_nodata,
        clip_nodata=CLIP_NODATA,
    )

    mask_na = mask_valid & (arr <= na_value)

    if not np.any(mask_na):
        raise ValueError(
            'Nenhum pixel com cota menor ou igual ao nivel selecionado.'
        )

    dataset = gdal.Open(raster_source)

    if dataset is None:
        raise ValueError(
            'Nao foi possivel abrir o raster usado no calculo.'
        )

    geotransform = dataset.GetGeoTransform()
    projection = dataset.GetProjection()

    rows, cols = mask_na.shape

    unique_id = datetime.now().strftime(
        '%Y%m%d%H%M%S%f'
    )

    mask_path = os.path.join(
        tempfile.gettempdir(),
        'curvacav_na_mask_{}.tif'.format(unique_id),
    )

    try:
        driver = gdal.GetDriverByName('GTiff')

        if driver is None:
            raise ValueError(
                'Driver GTiff do GDAL nao esta disponivel.'
            )

        mask_dataset = driver.Create(
            mask_path,
            cols,
            rows,
            1,
            gdal.GDT_Byte,
            options=['COMPRESS=LZW'],
        )

        if mask_dataset is None:
            raise ValueError(
                'Nao foi possivel criar a mascara raster temporaria.'
            )

        mask_dataset.SetGeoTransform(geotransform)
        mask_dataset.SetProjection(projection)

        mask_band = mask_dataset.GetRasterBand(1)

        mask_array = np.where(
            mask_na,
            1,
            0,
        ).astype(np.uint8)

        mask_band.WriteArray(mask_array)
        mask_band.SetNoDataValue(0)
        mask_band.FlushCache()

        mask_band = None
        mask_dataset = None
        dataset = None

        polygonized = processing.run('gdal:polygonize', {
            'INPUT': mask_path,
            'BAND': 1,
            'FIELD': 'DN',
            'EIGHT_CONNECTEDNESS': True,
            'EXTRA': '',
            'OUTPUT': 'TEMPORARY_OUTPUT',
        })

        polygonized_path = polygonized['OUTPUT']

        # NOVA ETAPA: Corrigir geometrias inválidas ("bow-ties") geradas pela vetorização
        fixed = processing.run('native:fixgeometries', {
            'INPUT': polygonized_path,
            'OUTPUT': 'TEMPORARY_OUTPUT',
        })
        
        fixed_path = fixed['OUTPUT']

        filtered = processing.run(
            'native:extractbyexpression',
            {
                'INPUT': fixed_path,
                'EXPRESSION': '"DN" = 1',
                'OUTPUT': 'TEMPORARY_OUTPUT',
            },
        )
        
        filtered_path = filtered['OUTPUT']

        dissolved = processing.run(
            'native:dissolve',
            {
                'INPUT': filtered_path,
                'FIELD': [],
                'SEPARATE_DISJOINT': False,
                'OUTPUT': 'TEMPORARY_OUTPUT',
            },
        )
        
        dissolved_output = dissolved['OUTPUT']
        
        # Verifica se o retorno ja e um objeto QgsVectorLayer ou uma string (path/id)
        if isinstance(dissolved_output, QgsVectorLayer):
            dissolved_layer = dissolved_output
        else:
            dissolved_layer = QgsVectorLayer(dissolved_output, 'temp_dissolve', 'ogr')
        
        if not dissolved_layer.isValid():
            raise ValueError(
                'Falha ao carregar a camada de poligonos dissolvida.'
            )

        # Prepara a string de criação do QgsVectorLayer já com o CRS apropriado embutido
        crs_uri = 'Polygon'
        if projection:
            crs = QgsCoordinateReferenceSystem()
            crs.createFromWkt(projection)
            if crs.isValid():
                crs_uri = 'Polygon?crs={}'.format(crs.authid())

        result_layer = QgsVectorLayer(
            crs_uri,
            layer_name,
            'memory',
        )

        result_provider = result_layer.dataProvider()

        fields = QgsFields()
        fields.append(QgsField('COTA_NA', QVariant.Double))
        fields.append(QgsField('AREA_M2', QVariant.Double))
        fields.append(QgsField('AREA_HA', QVariant.Double))

        result_provider.addAttributes(fields)
        result_layer.updateFields()

        area_m2 = float(mask_na.sum() * area_pixel)

        # Itera sobre a camada dissolvida (e não sobre a string retornada pelo algoritmo)
        for feature in dissolved_layer.getFeatures():
            geometry = feature.geometry()

            if geometry is None or geometry.isEmpty():
                continue

            result_feature = QgsFeature(
                result_layer.fields()
            )

            result_feature.setGeometry(geometry)
            result_feature.setAttribute(
                'COTA_NA',
                na_value,
            )

            result_feature.setAttribute(
                'AREA_M2',
                area_m2,
            )

            result_feature.setAttribute(
                'AREA_HA',
                area_m2 / 10000.0,
            )

            result_provider.addFeature(result_feature)

        result_layer.updateExtents()

        if result_layer.featureCount() == 0:
            raise ValueError(
                'A poligonizacao nao produziu areas validas para o NA.'
            )

        return result_layer

    finally:
        dataset = None
        
        # Limpeza explícita de referências para soltar locks do arquivo temporário
        try:
            del dissolved_layer
        except NameError:
            pass

        try:
            if os.path.exists(mask_path):
                os.remove(mask_path)
        except OSError:
            pass
