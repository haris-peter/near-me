import os
import math
import requests
import logging
from fastmcp import FastMCP

# Setup logging for debugging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

# Configuration
SERVER_ID = os.getenv("MCP_SERVER_ID", "near-me-tool")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 6))
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", 5.0))

logging.info(f"Starting MCP server with ID: {SERVER_ID}")
logging.info(f"Using Overpass API URL: {OVERPASS_URL}")
logging.info(f"Max results: {MAX_RESULTS}, Default radius (km): {DEFAULT_RADIUS_KM}")

# Initialize FastMCP server
mcp = FastMCP(name=SERVER_ID)

def haversine_km(lat1, lon1, lat2, lon2):
    logging.debug(f"Calculating distance between ({lat1},{lon1}) and ({lat2},{lon2})")
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    logging.debug(f"Distance: {distance} km")
    return distance

def overpass_query(lat, lon, radius_km, amenity):
    logging.info(f"Querying Overpass API for amenity='{amenity}' near ({lat},{lon}) with radius {radius_km} km")
    radius_m = int(radius_km * 1000)
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
  way["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
  relation["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
);
out center;
"""
    try:
        res = requests.post(OVERPASS_URL, data=query, timeout=30)
        res.raise_for_status()
        logging.debug(f"Overpass API response status: {res.status_code}")
    except requests.RequestException as e:
        logging.error(f"Error querying Overpass API: {e}")
        return []

    results = []
    for el in res.json().get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or "Unknown"
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("telephone")
        addr_parts = [tags.get(k) for k in ["addr:street", "addr:housenumber", "addr:city", "addr:postcode", "addr:state", "addr:country"] if tags.get(k)]
        address = ", ".join(addr_parts) or tags.get("addr:full", "Not available")
        lat_e, lon_e = (el.get("lat"), el.get("lon")) if el["type"] == "node" else (el.get("center", {}).get("lat"), el.get("center", {}).get("lon"))
        if lat_e is None or lon_e is None:
            logging.warning(f"Skipping element without coordinates: {el}")
            continue

        dist = haversine_km(lat, lon, lat_e, lon_e)

        results.append({
            "name": name,
            "address": address,
            "contact": phone or "Not available",
            "lat": lat_e,
            "lon": lon_e,
            "distance_km": dist
        })

    sorted_results = sorted(results, key=lambda r: r["distance_km"])[:MAX_RESULTS]
    logging.info(f"Found {len(sorted_results)} results for amenity '{amenity}'")
    return sorted_results

@mcp.tool()
def find_nearest_hospital(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    logging.info("find_nearest_hospital called")
    return overpass_query(latitude, longitude, radius_km, "hospital")

@mcp.tool()
def find_nearest_police(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    logging.info("find_nearest_police called")
    return overpass_query(latitude, longitude, radius_km, "police")

@mcp.tool()
def find_nearest_fire_station(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    logging.info("find_nearest_fire_station called")
    return overpass_query(latitude, longitude, radius_km, "fire_station")

@mcp.tool()
def find_nearest_public_office(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    logging.info("find_nearest_public_office called")
    return overpass_query(latitude, longitude, radius_km, "townhall")

if __name__ == "__main__":
    logging.info("Starting MCP server...")

    mcp.run(transport="http",
            host="0.0.0.0",
            port=8000,
            )