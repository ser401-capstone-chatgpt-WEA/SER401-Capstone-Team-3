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

def create_leaflet_alert_maps_per_alert(json_file_path):
    """
    Generates a standalone HTML file with Leaflet.js for each alert in the JSON file.
    Each file is named pbs_warn_alert_<alert_id>.html and visualizes only that alert's polygons.
    """
    with open(json_file_path, 'r', encoding='utf-8') as file:
        alert_data = json.load(file)
    alerts = alert_data.get('alerts', [])
    output_files = []
    for alert in alerts:
        alert_id = alert.get('id')
        polygons = []
        area_description = None
        for area in alert.get('areas', []):
            if area.get('type') == 'polygon':
                polygons.append(area.get('value'))
            elif area.get('type') == 'area_description':
                area_description = area.get('value')
        if not polygons:
            continue
        # Flatten polygons (usually one per alert)
        for poly_coords in polygons:
            map_center_latitude = sum([pt[0] for pt in poly_coords]) / len(poly_coords)
            map_center_longitude = sum([pt[1] for pt in poly_coords]) / len(poly_coords)
            leaflet_polygons = []
            area_label = area_description or alert.get('event') or 'Alert Area'
            popup_content = f"{area_label}<br>Sender: {alert.get('sender', '')}"
            leaflet_polygons.append({'coordinates': poly_coords, 'popup': popup_content})
            source_json_filename = Path(json_file_path).name
            html_filename = f"pbs_warn_alert_{alert_id}.html"
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
        <b>Source JSON file:</b> <a href="{source_json_filename}" target="_blank">{source_json_filename}</a>
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
            html_path = Path(json_file_path).parent / html_filename
            with open(html_path, 'w', encoding='utf-8') as html_file:
                html_file.write(html_content)
            print(f"Map saved to {html_path}")
            output_files.append(str(html_path))
    return output_files

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python alert_map_leaflet.py <pbs_warn_alerts.json>")
        sys.exit(1)
    json_path = sys.argv[1]
    create_leaflet_alert_maps_per_alert(json_path)