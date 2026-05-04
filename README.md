# curvaCAV-GIS

Plugin QGIS para cálculo de curvas **Cota-Área-Volume (CAV)** a partir de MDT (Modelo Digital de Terreno).

## Recursos

- Cálculo CAV com incremento configurável
- Modos de recorte: todo o MDT, layer poligonal, extent atual do mapa ou retângulo desenhado
- Estatísticas (cota mín/máx) atualizadas conforme a área selecionada
- Aba "Resultados" com gráfico interativo e tabela
- Exportação de CSV e gráfico (JPG/PNG)
- Copiar tabela para clipboard (colar no Excel com Ctrl+V)
- Copiar imagem do gráfico para clipboard

## Instalação

### Via repositório QGIS
1. QGIS → Plugins → Gerenciar e Instalar Plugins
2. Buscar por `curvaCAV-GIS`
3. Instalar e ativar

### Via ZIP
1. QGIS → Plugins → Gerenciar e Instalar Plugins → Instalar a partir de ZIP
2. Selecionar `curvaCAV_GIS_vX.X.X.zip`
3. Ativar o plugin

## Uso

1. Clique no ícone **curvaCAV-GIS** na toolbar
2. Selecione o MDT raster
3. Defina a área considerada (padrão: extent atual do mapa)
4. Ajuste cota inicial, máxima e incremento
5. (Opcional) defina pasta de saída para salvar CSV e gráfico
6. Clique em **Calcular** — resultados aparecem na aba **Resultados**

## Autor

**Rodrigo Goncalves**
Email: rcghidro@gmail.com
GitHub: https://github.com/rodcgon

## Licença

GNU General Public License v2.0 — veja [LICENSE](LICENSE)
