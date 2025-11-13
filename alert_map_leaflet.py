import json
from pathlib import Path

def extract_alert_polygons(alert_json_path):
    """
    Extract polygons and region info from a PBS WARN alert JSON file.
    Returns a list of dicts: { 'polygon': [[lat, lon], ...], 'area_description': str, 'event': str, 'sender': str }
    """
    with open(alert_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    results = []
    for alert in data.get('alerts', []):
        area_info = {
            'polygon': None,
            'area_description': None,
            'event': alert.get('event'),
            'sender': alert.get('sender'),
        }
        for area in alert.get('areas', []):
            if area.get('type') == 'polygon':
                area_info['polygon'] = area.get('value')
            elif area.get('type') == 'area_description':
                area_info['area_description'] = area.get('value')
        if area_info['polygon']:
            results.append(area_info)
    return results

def generate_leaflet_html(alert_json_path, output_html_path=None):
    """
    Generate a standalone HTML file with Leaflet.js to display alert polygons.
    """
    polygons = extract_alert_polygons(alert_json_path)
    if not polygons:
        print("No polygons found in alert file.")
        return None
    # Center map on first polygon
    first_poly = polygons[0]['polygon']
    center_lat = sum([pt[0] for pt in first_poly]) / len(first_poly)
    center_lon = sum([pt[1] for pt in first_poly]) / len(first_poly)
    # Prepare JS polygons
    js_polygons = []
    for info in polygons:
        poly = [[lat, lon] for lat, lon in info['polygon']]
        desc = info.get('area_description') or info.get('event') or 'Alert Area'
        popup = f"{desc}<br>Sender: {info.get('sender', '')}"
        js_polygons.append({'coords': poly, 'popup': popup})
    # HTML template
    html = f'''<!DOCTYPE html>
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
    <div id="map"></div>
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lon}], 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: 'Map © OpenStreetMap contributors'
        }}).addTo(map);
        var polygons = {json.dumps(js_polygons)};
        polygons.forEach(function(p) {{
            var poly = L.polygon(p.coords, {{color: 'blue', fillOpacity: 0.3}}).addTo(map);
            poly.bindPopup(p.popup);
        }});
    </script>
</body>
</html>'''
    if not output_html_path:
        output_html_path = str(Path(alert_json_path).with_suffix('.html'))
    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Map saved to {output_html_path}")
    return output_html_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python alert_map_leaflet.py <pbs_warn_alerts.json> [output_map.html]")
        sys.exit(1)
    alert_json_path = sys.argv[1]
    output_html_path = sys.argv[2] if len(sys.argv) > 2 else None
    generate_leaflet_html(alert_json_path, output_html_path)
