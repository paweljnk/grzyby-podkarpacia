from grzyby.etl.probe import (feature_properties_schema, infer_json_schema, parse_wcs_capabilities,
                              parse_wfs_capabilities, parse_xsd_elements)

# Minimalne dokumenty w formacie standardów OGC — fikstury testowe parsera, nie dane źródłowe.
WFS_CAPS = b"""<?xml version="1.0"?>
<wfs:WFS_Capabilities version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:ows="http://www.opengis.net/ows/1.1">
 <ows:OperationsMetadata><ows:Operation name="GetFeature">
   <ows:Parameter name="outputFormat"><ows:AllowedValues>
     <ows:Value>application/gml+xml; version=3.2</ows:Value><ows:Value>application/json</ows:Value>
   </ows:AllowedValues></ows:Parameter></ows:Operation></ows:OperationsMetadata>
 <wfs:FeatureTypeList><wfs:FeatureType><wfs:Name>ns:Warstwa_A</wfs:Name><wfs:Title>A</wfs:Title>
   <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::2180</wfs:DefaultCRS></wfs:FeatureType></wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""

XSD = b"""<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema">
 <xsd:complexType name="Warstwa_AType"><xsd:complexContent><xsd:extension base="gml:AbstractFeatureType">
  <xsd:sequence><xsd:element name="nazwa" type="xsd:string"/><xsd:element name="geom" type="gml:GeometryPropertyType"/>
  </xsd:sequence></xsd:extension></xsd:complexContent></xsd:complexType></xsd:schema>"""


def test_parse_wfs_capabilities():
    caps = parse_wfs_capabilities(WFS_CAPS)
    assert caps["wersja"] == "2.0.0"
    assert caps["typy_obiektow"] == [{"Name": "ns:Warstwa_A", "Title": "A", "DefaultCRS": "urn:ogc:def:crs:EPSG::2180"}]
    assert "application/json" in caps["formaty_wyjsciowe"]


def test_parse_xsd_fields():
    assert parse_xsd_elements(XSD) == {"Warstwa_AType": {"nazwa": "xsd:string", "geom": "gml:GeometryPropertyType"}}


def test_parse_wcs():
    xml = b'<w:Capabilities xmlns:w="http://www.opengis.net/wcs/2.0" version="2.0.1"><w:Contents>' \
          b'<w:CoverageSummary><w:CoverageId>C1</w:CoverageId></w:CoverageSummary></w:Contents></w:Capabilities>'
    assert parse_wcs_capabilities(xml) == {"wersja": "2.0.1", "pokrycia": ["C1"]}


def test_feature_schema_counts_nulls_and_types():
    feats = [{"type": "Feature", "geometry": {"type": "Polygon"}, "properties": {"a": 1, "b": None}},
             {"type": "Feature", "geometry": {"type": "Polygon"}, "properties": {"a": None, "b": "x"}}]
    s = feature_properties_schema(feats)
    assert s["pola"]["a"]["typy"] == {"integer": 1, "null": 1}
    assert s["pola"]["b"]["przyklad"] == "x"
    assert s["typ_geometrii"] == {"Polygon": 2}


def test_infer_json_schema():
    assert infer_json_schema({"x": [1, 2], "y": {"z": None}}) == {"x": ["integer", "<2 elementów>"], "y": {"z": "null"}}
