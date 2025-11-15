import json
from pathlib import Path

def get_alert_area_polygons(json_file_path):
    """
    Extracts all polygons and region info from a PBS WARN alert JSON file.
    Returns a list of dicts: { 'polygon': [[lat, lon], ...], 'area_description': str, 'event': str, 'sender': str }
    """
    with open(json_file_path, 'r', encoding='utf-8') as file:
        alert_data = json.load(file)
    polygons_metadata = []
    for alert in alert_data.get('alerts', []):
        area_details = {
            'polygon': None,
            'area_description': None,
            'event': alert.get('event'),
            'sender': alert.get('sender'),
        }
        for area in alert.get('areas', []):
            if area.get('type') == 'polygon':
                area_details['polygon'] = area.get('value')
            elif area.get('type') == 'area_description':
                area_details['area_description'] = area.get('value')
        if area_details['polygon']:
            polygons_metadata.append(area_details)
    return polygons_metadata

def create_leaflet_alert_map(json_file_path, output_html_path=None):
    """
    Generates a standalone HTML file with Leaflet.js to display alert polygons from PBS WARN alerts.
    """
    alert_areas = get_alert_area_polygons(json_file_path)
    if not alert_areas:
        print("No polygons found in alert file.")
        return None
    polygons_metadata = get_alert_area_polygons(json_file_path)
    first_polygon = alert_areas[0]['polygon']
    map_center_latitude = sum([point[0] for point in first_polygon]) / len(first_polygon)
    map_center_longitude = sum([point[1] for point in first_polygon]) / len(first_polygon)
    # Prepare JavaScript polygons
    first_polygon = polygons_metadata[0]['polygon']
    for area in alert_areas:
        polygon_coordinates = [[latitude, longitude] for latitude, longitude in area['polygon']]
        area_label = area.get('area_description') or area.get('event') or 'Alert Area'
    leaflet_polygons = []
    for polygon_info in polygons_metadata:
        polygon_coordinates = [[latitude, longitude] for latitude, longitude in polygon_info['polygon']]
        area_label = polygon_info.get('area_description') or polygon_info.get('event') or 'Alert Area'
        popup_content = f"{area_label}<br>Sender: {polygon_info.get('sender', '')}"
        leaflet_polygons.append({'coordinates': polygon_coordinates, 'popup': popup_content})
    source_json_filename = Path(json_file_path).name
    # If the HTML and JSON are in the same folder, link directly; else, just show filename
    json_link = source_json_filename if not output_html_path or Path(output_html_path).parent == Path(json_file_path).parent else None
    html_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>PBS WARN Alert Map</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
    <style>#map {{ height: 600px; width: 100%; }}</style>
</head>
<body>
    <h2>PBS WARN Alert Map</h2>
    <div style="margin-bottom: 10px;">
        <b>Source JSON file:</b> {'<a href="' + json_link + '" target="_blank">' + source_json_filename + '</a>' if json_link else source_json_filename}
    </div>
    <div id="map"></div>
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
    <script>
        var map = L.map('map').setView([{map_center_latitude}, {map_center_longitude}], 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: 'Map © OpenStreetMap contributors'
        }}).addTo(map);
        var polygons = {json.dumps(leaflet_polygons)};
        polygons.forEach(function(polygon) {{
            var poly = L.polygon(polygon.coordinates, {{color: 'blue', fillOpacity: 0.3}}).addTo(map);
            poly.bindPopup(polygon.popup);
        }});
    </script>
</body>
</html>'''
    if not output_html_path:
        output_html_path = str(Path(json_file_path).with_suffix('.html'))
    with open(output_html_path, 'w', encoding='utf-8') as html_file:
        html_file.write(html_content)
    print(f"Map saved to {output_html_path}")
    return output_html_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python alert_map_leaflet.py <pbs_warn_alerts.json> [output_map.html]")
        sys.exit(1)
    json_path = sys.argv[1]
    html_output_path = sys.argv[2] if len(sys.argv) > 2 else None
    create_leaflet_alert_map(json_path, html_output_path)