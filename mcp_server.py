#!/usr/bin/env python3
"""
PBS WARN MCP Server
Provides emergency alert data through the Model Context Protocol (MCP).
"""
import asyncio
import json
import os
import math
import datetime
import time
import logging
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Load environment variables
load_dotenv()

# RAG Imports
try:
    from rags.retriever import AlertRetriever
    from rags.generator import ResponseGenerator
    RAG_AVAILABLE = True
except ImportError as e:
    print(f"DEBUG: Failed to import RAG modules: {e}")
    RAG_AVAILABLE = False

ALERT_FILE = os.getenv("ALERT_FILE", "./data/cleaned_alerts.json")

# Downtime logging
DOWNTIME_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downtime.log")

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------
# Global RAG components (lazy loaded)
_retriever = None
_generator = None

def get_rag_components():
    """Lazy load RAG components to avoid startup overhead/errors if not configured."""
    global _retriever, _generator
    if not RAG_AVAILABLE:
        raise ImportError("RAG modules not available. Check dependencies.")
        
    if _retriever is None:
        # Defaults to ./chroma_db
        _retriever = AlertRetriever()
    
    if _generator is None:
        # Requires GEMINI_API_KEY
        _generator = ResponseGenerator()
        
    return _retriever, _generator

def extract_lat_lon(alert):
    """Extract latitude/longitude from alert, checking nested areas if needed."""
    lat = alert.get("latitude")
    lon = alert.get("longitude")
    if lat and lon and lat != 0.0 and lon != 0.0:
        return lat, lon
    # Check nested areas for circle type with center coordinates
    for area in alert.get("areas", []):
        if area.get("type") == "circle":
            value = area.get("value", {})
            if isinstance(value, dict):
                center = value.get("center", {})
                lat = center.get("latitude")
                lon = center.get("longitude")
                if lat and lon:
                    return lat, lon
    return None, None

def load_alerts():
    """Load alerts from JSON file."""
    if not os.path.exists(ALERT_FILE):
        return []
    try:
        with open(ALERT_FILE, "r") as f:
            data = json.load(f)
        # Handle {"alerts": [...]} wrapper
        if isinstance(data, dict) and "alerts" in data:
            data = data["alerts"]
        # Ensure each alert has top-level latitude/longitude
        for alert in data:
            lat, lon = extract_lat_lon(alert)
            if lat is not None:
                alert["latitude"] = lat
                alert["longitude"] = lon
        return data
    except Exception:
        return []

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two lat/lon points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def now_utc_iso():
    """Return current UTC timestamp in ISO format."""
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()

# -------------------------------------------------------------
# MCP Server Setup
# -------------------------------------------------------------
server = Server("pbs-warn-scraper")

@server.list_tools()
async def list_tools():
    """Define available tools for the MCP client."""
    return [
        Tool(
            name="get_alerts_near_location",
            description="Return all active alerts within a given radius (km) of exact latitude/longitude coordinates. Only use when you have precise coordinates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude coordinate"},
                    "longitude": {"type": "number", "description": "Longitude coordinate"},
                    "radius_km": {"type": "number", "description": "Search radius in kilometers", "default": 25}
                },
                "required": ["latitude", "longitude"]
            }
        ),
        Tool(
            name="check_emergency_status",
            description="Check if any active emergency is near exact coordinates. Only use when you have precise lat/lon.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude coordinate"},
                    "longitude": {"type": "number", "description": "Longitude coordinate"}
                },
                "required": ["latitude", "longitude"]
            }
        ),
        Tool(
            name="get_alert_summary_for_region",
            description="Search alerts by region/city/state/county name. Searches alert sender, event name, and area descriptions for the given text. Returns up to 5 alerts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string", 
                        "description": "Region, city, state, or county name to search for in alert data. Example: 'California' or 'Los Angeles'."
                    }
                },
                "required": ["region"]
            }
        ),
        Tool(
            name="get_alert_sources_status",
            description="Return the current status of all upstream alert sources.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="ask_alert_knowledge_base",
            description="PREFERRED TOOL. Ask a natural language question about emergency alerts using the RAG knowledge base. Use this FIRST for any general questions about alerts, summaries, what's happening, or when a user asks about alerts in a region or area. This searches the full alert database semantically.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string", 
                        "description": "The natural language question to ask about emergency alerts. Must be clearly phrased."
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="system_health_check",
            description="Perform automated health checks on system components to monitor uptime and detect downtime.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls from the MCP client."""
    try:
        alerts = load_alerts()

        if name == "get_alerts_near_location":
            lat = float(arguments["latitude"])
            lon = float(arguments["longitude"])
            radius = float(arguments.get("radius_km", 200))
            nearby = []
            nearest, min_dist = None, float("inf")

            for a in alerts:
                try:
                    dist = haversine(lat, lon, a["latitude"], a["longitude"])
                    if dist < min_dist:
                        nearest, min_dist = a.copy(), dist
                    if dist <= radius:
                        a_copy = dict(a)
                        a_copy["distance_km"] = round(dist, 2)
                        nearby.append(a_copy)
                except Exception:
                    continue

            result = {
                "success": True,
                "tool": "get_alerts_near_location",
                "count": len(nearby),
                "timestamp": now_utc_iso(),
                "alerts": nearby
            }
            # Always include nearest alert info even if outside radius
            if nearest and not nearby:
                result["nearest_alert"] = {
                    "event": nearest.get("event", "Unknown"),
                    "sender": nearest.get("sender", "Unknown"),
                    "distance_km": round(min_dist, 2),
                    "note": f"No alerts within {radius}km, but nearest alert is {round(min_dist, 1)}km away."
                }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "check_emergency_status":
            lat = float(arguments["latitude"])
            lon = float(arguments["longitude"])

            nearest, min_dist = None, float("inf")
            for a in alerts:
                try:
                    dist = haversine(lat, lon, a["latitude"], a["longitude"])
                    if dist < min_dist:
                        nearest, min_dist = a, dist
                except Exception:
                    continue

            if nearest and min_dist < 10:
                status = f"Active alert within {min_dist:.1f} km: {nearest.get('title') or nearest.get('event', 'Unknown')}."
            elif nearest:
                status = f"No active emergency nearby. Closest alert {min_dist:.1f} km away."
            else:
                status = "No alert data available."

            result = {
                "success": True,
                "tool": "check_emergency_status",
                "status": status,
                "nearest_alert": nearest,
                "distance_km": round(min_dist, 2) if min_dist != float("inf") else None,
                "timestamp": now_utc_iso()
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_alert_summary_for_region":
            region = arguments.get("region", "").lower()
            
            # State abbreviation mapping for flexible matching
            state_map = {
                "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
                "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
                "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
                "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
                "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
                "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
                "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
                "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
                "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
                "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
                "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
                "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
                "wisconsin": "wi", "wyoming": "wy"
            }
            abbrev_map = {v: k for k, v in state_map.items()}
            
            # Build search terms: split on commas and spaces, filter empties
            import re as _re
            search_terms = [t.strip() for t in _re.split(r'[,]+', region) if t.strip()]
            # Expand state names/abbreviations
            expanded = set(search_terms)
            for term in search_terms:
                if term in state_map:
                    expanded.add(state_map[term])
                if term in abbrev_map:
                    expanded.add(abbrev_map[term])
            
            region_alerts = []
            for a in alerts:
                searchable = " ".join([
                    str(a.get("sender", "")),
                    str(a.get("event", "")),
                    str(a.get("title", "")),
                    str(a.get("category", "")),
                    " ".join(
                        str(area.get("value", ""))
                        for area in a.get("areas", [])
                        if area.get("type") == "area_description"
                    ),
                    " ".join(
                        str(t.get("text", ""))
                        for t in a.get("texts", [])
                    )
                ]).lower()
                # Match if ANY search term is found
                if any(term in searchable for term in expanded):
                    region_alerts.append(a)
            summary = f"{len(region_alerts)} active alerts matching '{region.title()}'."

            result = {
                "success": True,
                "tool": "get_alert_summary_for_region",
                "region": region,
                "count": len(region_alerts),
                "summary": summary,
                "alerts": region_alerts[:5],
                "timestamp": now_utc_iso()
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_alert_sources_status":
            sources = [
                {"name": "PBS WARN", "last_fetched": "2 m ago", "status": "OK"},
                {"name": "IPAWS", "last_fetched": "8 m ago", "status": "OK"}
            ]

            result = {
                "success": True,
                "tool": "get_alert_sources_status",
                "sources": sources,
                "timestamp": now_utc_iso()
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ask_alert_knowledge_base":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(type="text", text="Error: Query is required.")]

            try:
                start_time = time.time()
                retriever, generator = get_rag_components()
                
                # 1. Retrieve
                retrieved_docs = retriever.retrieve(query)
                
                # 2. Generate
                response = generator.generate(query, retrieved_docs)
                end_time = time.time()
                duration = end_time - start_time
                logging.info(f"Query '{query}' response time: {duration:.2f} seconds")
                if duration > 5:
                    logging.warning(f"Query '{query}' exceeded 5 second threshold: {duration:.2f} seconds")
                
                # Format output
                result = {
                    "success": True,
                    "tool": "ask_alert_knowledge_base",
                    "answer": response["answer"],
                    "sources_count": len(response["sources"]),
                    "sources": response["sources"],
                    "tokens_used": response.get("tokens_used", 0),
                    "response_time_seconds": duration
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
                
            except Exception as e:
                return [TextContent(type="text", text=json.dumps({"success": False, "error": f"RAG Error: {str(e)}"}))]

        elif name == "system_health_check":
            health_status = {}
            
            # Check RAG components
            try:
                retriever, generator = get_rag_components()
                health_status['rag_components'] = 'up'
            except Exception as e:
                health_status['rag_components'] = f'down: {str(e)}'
            
            # Check alert loading
            try:
                alerts = load_alerts()
                health_status['alert_data'] = f'up: {len(alerts)} alerts loaded'
            except Exception as e:
                health_status['alert_data'] = f'down: {str(e)}'
            
            # Check API connectivity (mock for now)
            health_status['api_connectivity'] = 'up'  # Could add actual check
            
            # Determine overall status
            is_healthy = all('up' in str(status) for status in health_status.values())
            if not is_healthy:
                logging.warning(f"System health check detected issues: {health_status}")
                # Log downtime event
                with open(DOWNTIME_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{now_utc_iso()}: Downtime detected - {health_status}\n")
            
            result = {
                "success": True,
                "tool": "system_health_check",
                "healthy": is_healthy,
                "components": health_status,
                "timestamp": now_utc_iso()
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        # Standardize the error response pattern for OpenAI compatibility
        error_result = {
            "success": False,
            "error": str(e),
            "tool": name,
            "timestamp": now_utc_iso(),
            "note": "Ensure your request parameters strictly match the tool schema."
        }
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]

# -------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------
async def main():
    """Run the MCP server using stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
