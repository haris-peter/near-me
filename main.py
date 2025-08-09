from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import requests
import math
import uvicorn
import os

# --------------------------------------------------------------------
# Configuration & Server ID
# --------------------------------------------------------------------
SERVER_ID = os.getenv("MCP_SERVER_ID", "near-me")  # Default ID if not set
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 6))
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", 5.0))

# --------------------------------------------------------------------
# FastAPI App
# --------------------------------------------------------------------
app = FastAPI(
    title="LocalGovServicesMCP",
    description="Find nearest public services via OSM Overpass",
    version="1.0.0"
)

# ----------------------------- Utilities -----------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def overpass_query(lat: float, lon: float, radius_km: float, amenity: str) -> List[Dict[str, Any]]:
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
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Overpass API error: {e}")

    elements = res.json().get("elements", [])
    results = []

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or "Unknown"
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("telephone")
        addr_parts = [
            tags.get(k)
            for k in ["addr:street", "addr:housenumber", "addr:city", "addr:postcode", "addr:state", "addr:country"]
            if tags.get(k)
        ]
        address = ", ".join(addr_parts) if addr_parts else tags.get("addr:full") or "Not available"

        if el.get("type") == "node":
            lat_e = el.get("lat")
            lon_e = el.get("lon")
        else:
            center = el.get("center") or {}
            lat_e = center.get("lat")
            lon_e = center.get("lon")

        if lat_e is None or lon_e is None:
            continue

        results.append({
            "name": name,
            "address": address,
            "contact": phone or "Not available",
            "lat": lat_e,
            "lon": lon_e,
            "osm_id": el.get("id"),
            "type": el.get("type"),
            "tags": tags,
        })

    for r in results:
        r["distance_km"] = haversine_km(lat, lon, r["lat"], r["lon"])
    return sorted(results, key=lambda x: x.get("distance_km") or 9999)[:MAX_RESULTS]

# ----------------------------- Models -----------------------------
class FindParams(BaseModel):
    latitude: float
    longitude: float
    radius_km: Optional[float] = DEFAULT_RADIUS_KM
    amenity: Optional[str] = "hospital"

class ToolCall(BaseModel):
    tool: str
    params: Dict[str, Any]

# ----------------------------- Tool Metadata -----------------------------
TOOLS = [
    {"name": "find_nearest_hospital", "description": "Find nearby hospitals", "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}},
    {"name": "find_nearest_police", "description": "Find nearby police stations", "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}},
    {"name": "find_nearest_fire_station", "description": "Find nearby fire stations", "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}},
    {"name": "find_nearest_public_office", "description": "Find nearby public offices", "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}},
]

AMENITY_MAP = {
    "hospital": "hospital",
    "police": "police",
    "fire_station": "fire_station",
    "public_office": "townhall",
}

# ----------------------------- Endpoints -----------------------------
@app.get("/tools")
def list_tools():
    return {"server_id": SERVER_ID, "tools": TOOLS}

@app.get("/server-id")
def get_server_id():
    return {"server_id": SERVER_ID}

@app.post("/call")
def call_tool(call: ToolCall):
    if call.tool not in [t["name"] for t in TOOLS]:
        raise HTTPException(status_code=404, detail="Tool not found")

    if call.tool == "find_nearest_hospital":
        amenity = AMENITY_MAP["hospital"]
    elif call.tool == "find_nearest_police":
        amenity = AMENITY_MAP["police"]
    elif call.tool == "find_nearest_fire_station":
        amenity = AMENITY_MAP["fire_station"]
    elif call.tool == "find_nearest_public_office":
        amenity = AMENITY_MAP["public_office"]
    else:
        amenity = call.params.get("amenity") or "hospital"

    try:
        lat = float(call.params.get("latitude"))
        lon = float(call.params.get("longitude"))
    except Exception:
        raise HTTPException(status_code=400, detail="latitude and longitude must be numeric")

    radius_km = float(call.params.get("radius_km", DEFAULT_RADIUS_KM))
    results = overpass_query(lat, lon, radius_km, amenity)

    return {"results": [
        {
            "name": r["name"],
            "address": r["address"],
            "contact": r["contact"],
            "distance_km": round(r["distance_km"], 2),
            "map_link": f"https://www.google.com/maps?q={r['lat']},{r['lon']}",
            "osm_tags": r["tags"],
        }
        for r in results
    ]}

# ----------------------------- Run -----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
