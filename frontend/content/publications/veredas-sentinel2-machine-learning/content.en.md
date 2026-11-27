---
title: Mapping Veredas (Cerrado Wetlands) by Integrating Sentinel-2 Spectral Indices and Copernicus DEM Morphometrics with Supervised Machine Learning
subtitle: XIV Brazilian Colloquium on Geodetic Sciences, Curitiba, 2026
date: 2026-09-23
cover: assets/classificacao-veredas.jpg
tags: [Remote Sensing, Machine Learning, Wetlands, Sentinel-2, Cerrado]
language: en
ai_written: false
citation: cite.bib
doi: https://doi.org/10.5281/zenodo.22885603
# Approximate extent of the Pandeiros river basin, northern Minas Gerais.
# Replace with the real basin geometry when it is exported.
aoi_wkt: POLYGON ((-45.32 -15.88, -44.52 -15.88, -44.52 -15.02, -45.32 -15.02, -45.32 -15.88))
---

Co-authored with Claudionor Ribeiro da Silva and L. A. P. Silva. Presented as
an oral communication at the XIV Brazilian Colloquium on Geodetic Sciences,
held at the Federal University of Paraná.

Separating veredas from the surrounding Cerrado is hard with spectral data
alone: moist valley bottoms and seasonal grasslands overlap in index space for
much of the year. Pairing Sentinel-2 spectral indices with morphometric
derivatives of the Copernicus DEM gives the classifier a second, independent
axis, and the wetland boundaries stabilise.

## Patch blending

<video controls preload="metadata" src="assets/vereda_patch_blending_en.mp4"></video>

The record is deposited on Zenodo; the DOI link above resolves to it.
