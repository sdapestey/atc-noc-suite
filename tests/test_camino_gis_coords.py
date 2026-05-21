"""Corrección de coordenadas GIS (lat/lon en GeoJSON)."""

import services.camino_gis as cg


def test_swap_lat_lon_linestring_ar():
    geom = {
        "type": "LineString",
        "coordinates": [[-34.5, -58.4], [-34.51, -58.41]],
    }
    out = cg._maybe_swap_lat_lon_in_geojson(geom)
    assert out["coordinates"][0] == [-58.4, -34.5]
    assert out["coordinates"][1] == [-58.41, -34.51]


def test_no_swap_when_already_lon_lat():
    geom = {
        "type": "LineString",
        "coordinates": [[-58.4, -34.5], [-58.41, -34.51]],
    }
    out = cg._maybe_swap_lat_lon_in_geojson(geom)
    assert out["coordinates"] == geom["coordinates"]


def test_no_swap_projected_coords():
    geom = {
        "type": "LineString",
        "coordinates": [[350000.0, 5810000.0], [351000.0, 5811000.0]],
    }
    out = cg._maybe_swap_lat_lon_in_geojson(geom)
    assert out["coordinates"] == geom["coordinates"]
