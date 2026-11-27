---
title: "wsnet"
subtitle: "Extrai redes de água e esgoto de modelos Bentley e devolve shapefiles prontos"
language: pt
---

Um formulário no navegador lê o modelo Bentley, um arquivo SQLite, com sql.js
e reconstrói a geometria da rede no cliente. Ele envia GeoJSON para uma API
FastAPI, que responde com um zip contendo dois shapefiles, pontos e linhas, do
sistema de abastecimento de água (SAA) ou do de esgotamento sanitário (SES).

Modelos Bentley guardam as coordenadas em UTM e em pés, sem CRS declarado. O
backend converte pés para metros, lê as coordenadas na zona UTM que o
geocódigo do município indica e reprojeta a saída para SIRGAS 2000
(EPSG:4674). Um ponto que cai fora do Brasil vai para o log, que é o que
denuncia unidade ou zona lida errado.
