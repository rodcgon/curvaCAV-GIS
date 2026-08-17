# curvaCAV-GIS

QGIS plugin for calculating **Elevation-Area-Volume (CAV/EAV)** curves from a DTM raster.

## Features

- CAV/EAV curve calculation with configurable elevation increment
- Clipping modes: entire DTM, polygon layer (with optional single-feature selection), current map extent, or rectangle drawn on the map canvas
- On-demand raster statistics (min/max elevation, resolution)
- Results tab with interactive Area and Volume chart
- Full Elevation-Area-Volume table
- Draw a Polygon enclosing a determined WSL
- Export results as CSV and PNG chart
- Copy table to clipboard (paste directly in Excel with Ctrl+V)
- Copy chart image to clipboard
- No external Python dependencies required

## Requirements

- QGIS 3.16 or newer
- Compatible with Windows, Linux and macOS

## Installation

### From the QGIS Plugin Repository
1. QGIS → Plugins → Manage and Install Plugins
2. Search for `curvaCAV-GIS`
3. Click Install

### From ZIP
1. QGIS → Plugins → Manage and Install Plugins → Install from ZIP
2. Select the downloaded `.zip` file
3. Enable the plugin

## Usage

1. Click the **curvaCAV-GIS** toolbar icon
2. Select the DTM raster layer
3. Choose the area mode (default: entire DTM)
4. Click **Load statistics** to populate min/max elevation fields
5. Set min elevation, max elevation and increment
6. Click **Calculate** — results appear in the **Results** tab
7. Optionally set an output folder and click **Save results to folder** to export CSV and chart

## Author

**Rodrigo Goncalves**
Email: rcghidro@gmail.com
GitHub: https://github.com/rodcgon

## License

GNU General Public License v2 or later — see [LICENSE](LICENSE)
