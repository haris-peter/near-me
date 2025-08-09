# server.py
import os
import math
import requests
from fastmcp import FastMCP

# Configuration
SERVER_ID = os.getenv("MCP_SERVER_ID", "near-me-tool")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 6))
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", 5.0))

# Initialize FastMCP server
mcp = FastMCP(name=SERVER_ID)

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def overpass_query(lat, lon, radius_km, amenity):
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
    res = requests.post(OVERPASS_URL, data=query, timeout=30)
    res.raise_for_status()

    results = []
    for el in res.json().get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or "Unknown"
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("telephone")
        addr_parts = [tags.get(k) for k in ["addr:street", "addr:housenumber", "addr:city", "addr:postcode", "addr:state", "addr:country"] if tags.get(k)]
        address = ", ".join(addr_parts) or tags.get("addr:full", "Not available")
        lat_e, lon_e = (el.get("lat"), el.get("lon")) if el["type"] == "node" else (el.get("center", {}).get("lat"), el.get("center", {}).get("lon"))
        if lat_e is None or lon_e is None:
            continue

        results.append({
            "name": name,
            "address": address,
            "contact": phone or "Not available",
            "lat": lat_e,
            "lon": lon_e,
            "distance_km": haversine_km(lat, lon, lat_e, lon_e)
        })

    return sorted(results, key=lambda r: r["distance_km"])[:MAX_RESULTS]

@mcp.tool()
def find_nearest_hospital(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    return overpass_query(latitude, longitude, radius_km, "hospital")

@mcp.tool()
def find_nearest_police(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    return overpass_query(latitude, longitude, radius_km, "police")

@mcp.tool()
def find_nearest_fire_station(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    return overpass_query(latitude, longitude, radius_km, "fire_station")

@mcp.tool()
def find_nearest_public_office(latitude: float, longitude: float, radius_km: float = DEFAULT_RADIUS_KM) -> list:
    return overpass_query(latitude, longitude, radius_km, "townhall")

if __name__ == "__main__":
    mcp.run()
