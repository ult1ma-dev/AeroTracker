# Bundled map resources

The report contains every required asset inline; it does not load map tiles,
fonts, scripts, styles, or data from the internet when it is opened.

## Leaflet 1.9.4

Copyright (c) 2010–2023, Volodymyr Agafonkin; Copyright (c) 2010–2011, CloudMade.
Licensed under BSD-2-Clause. The complete license is in LICENSE-Leaflet.txt.
The upstream license banner is preserved in the JavaScript file, and the full
license is also embedded as an HTML comment in each standalone report.

Sources (retrieved 2026-10-27):

- https://github.com/Leaflet/Leaflet/releases/download/v1.9.4/leaflet.zip
  (`dist/leaflet.js` extracted from the official release archive)
- https://raw.githubusercontent.com/Leaflet/Leaflet/v1.9.4/dist/leaflet.css
- https://raw.githubusercontent.com/Leaflet/Leaflet/v1.9.4/LICENSE

The renderer removes the source-map directive and replaces CSS image URLs
with `none`: this application uses circle markers and no bitmap icons.

## Natural Earth

Natural Earth 1:110m Admin 0 Countries, GeoJSON export from
`nvkelso/natural-earth-vector`. The bundled file preserves the source data.
Natural Earth data is public domain and requires no permission or attribution.
The report nevertheless credits Natural Earth.

Source (retrieved 2026-10-27):
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson

Terms: https://www.naturalearthdata.com/about/terms-of-use/

The generalized outlines are intended for visual context, not navigation or
precise boundary analysis. The displayed request rectangle is from Nominatim;
the aircraft observations are from OpenSky Network.
