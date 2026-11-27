---
title: "wsnet"
subtitle: "Extracts water and sewerage networks from Bentley models and returns ready shapefiles"
date: 2026-07-23
tags: [WebGIS]
language: en
ai_written: false
external_link: https://wsnet.rikalves.com/
source_repo: https://github.com/RikFerreira/wsnet
---

A browser form reads a Bentley model, a SQLite file, with sql.js and rebuilds
the network geometry on the client. It posts GeoJSON to a FastAPI backend,
which answers with a zip holding two shapefiles, points and lines, for either
the water supply network (SAA) or the sewerage network (SES).

Bentley models store coordinates in UTM feet and declare no CRS. The backend
converts feet to metres, reads them in the UTM zone the municipality code
implies, and reprojects the output to SIRGAS 2000 (EPSG:4674). A point that
lands outside Brazil is logged, which is what catches a wrong unit or zone.
