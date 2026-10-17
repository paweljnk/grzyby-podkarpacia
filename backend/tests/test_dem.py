from grzyby.etl.dem import aligned_grid, tile_name, tiles_for_bbox


def test_tile_names_match_bucket_convention():
    # Konwencja zweryfikowana listingiem bucketu copernicus-dem-30m (zob. docs/schemas).
    assert tile_name(49, 22) == "Copernicus_DSM_COG_10_N49_00_E022_00_DEM"


def test_tiles_for_pilot_bboxes():
    assert tiles_for_bbox([22.05, 49.15, 22.55, 49.45]) == ["Copernicus_DSM_COG_10_N49_00_E022_00_DEM"]
    assert set(tiles_for_bbox([21.75, 50.05, 22.25, 50.45])) == {
        "Copernicus_DSM_COG_10_N50_00_E021_00_DEM", "Copernicus_DSM_COG_10_N50_00_E022_00_DEM"}


def test_aligned_grid_snaps_to_resolution():
    tr, w, h = aligned_grid((100010.0, 200007.0, 100990.0, 200493.0), 25.0)
    assert tr.c % 25 == 0 and tr.f % 25 == 0
    assert tr.c <= 100010 and tr.c + w * 25 >= 100990
    assert tr.f >= 200493 and tr.f - h * 25 <= 200007
