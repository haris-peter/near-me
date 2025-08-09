from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import requests
import math
import uvicorn
import os
import time

# Configuration
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 6))
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", 5.0))

app = FastAPI(title="LocalGovServicesMCP", description="Find nearest public services via OSM Overpass")


# ----------------------------- Utilities -----------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    # Earth radius in km
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
    # We'll ask for nodes and ways/relations (centroid)
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
  way["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
  relation["amenity"="{amenity}"](around:{radius_m},{lat},{lon});
);
out center; // include center for ways/relations
"""
    try:
        res = requests.post(OVERPASS_URL, data=query, timeout=30)
        res.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Overpass API error: {e}")

    data = res.json()
    elements = data.get("elements", [])
    results = []

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or "Unknown"
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("telephone")
        # address heuristics
        addr_parts = []
        for k in ["addr:street", "addr:housenumber", "addr:city", "addr:postcode", "addr:state", "addr:country"]:
            if tags.get(k):
                addr_parts.append(tags.get(k))
        address = ", ".join(addr_parts) if addr_parts else tags.get("addr:full") or "Not available"

        # get coordinates
        if el.get("type") == "node":
            lat_e = el.get("lat")
            lon_e = el.get("lon")
        else:
            # ways and relations have center
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

    # compute distance and sort
    for r in results:
        r["distance_km"] = haversine_km(lat, lon, r["lat"], r["lon"]) if r.get("lat") else None
    results = sorted(results, key=lambda x: x.get("distance_km") or 9999)
    return results[:MAX_RESULTS]


# ----------------------------- Pydantic models -----------------------------

class FindParams(BaseModel):
    latitude: float
    longitude: float
    radius_km: Optional[float] = DEFAULT_RADIUS_KM
    amenity: Optional[str] = "hospital"


class ToolCall(BaseModel):
    tool: str
    params: Dict[str, Any]


# ----------------------------- Tools metadata -----------------------------

TOOLS = [
    {
        "name": "find_nearest_hospital",
        "description": "Find nearby hospitals based on lat/lon",
        "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}
    },
    {
        "name": "find_nearest_police",
        "description": "Find nearby police stations",
        "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}
    },
    {
        "name": "find_nearest_fire_station",
        "description": "Find nearby fire stations",
        "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}
    },
    {
        "name": "find_nearest_public_office",
        "description": "Find nearby public offices (city hall, municipal office, etc.)",
        "params": {"latitude": "float", "longitude": "float", "radius_km": "float (optional)"}
    },
]

AMENITY_MAP = {
    "hospital": "hospital",
    "police": "police",
    "fire_station": "fire_station",
    "public_office": "townhall",  # use townhall as a heuristic
}


# ----------------------------- Endpoints -----------------------------

@app.get("/tools")
def list_tools():
    """Returns list of available tools (MCP-style)."""
    return {"tools": TOOLS}


@app.post("/call")
def call_tool(call: ToolCall):
    """Call a tool by name. Params should contain latitude, longitude, radius_km optional."""
    tool = call.tool
    params = call.params
    if tool not in [t["name"] for t in TOOLS]:
        raise HTTPException(status_code=404, detail="Tool not found")

    # map tool name to amenity
    if tool == "find_nearest_hospital":
        amenity = AMENITY_MAP["hospital"]
    elif tool == "find_nearest_police":
        amenity = AMENITY_MAP["police"]
    elif tool == "find_nearest_fire_station":
        amenity = AMENITY_MAP["fire_station"]
    elif tool == "find_nearest_public_office":
        amenity = AMENITY_MAP["public_office"]
    else:
        amenity = params.get("amenity") or "hospital"

    try:
        lat = float(params.get("latitude"))
        lon = float(params.get("longitude"))
    except Exception:
        raise HTTPException(status_code=400, detail="latitude and longitude must be provided and numeric")

    radius_km = float(params.get("radius_km", DEFAULT_RADIUS_KM))
    results = overpass_query(lat, lon, radius_km, amenity)

    # format response for WhatsApp-friendly output
    out = []
    for r in results:
        out.append({
            "name": r["name"],
            "address": r["address"],
            "contact": r["contact"],
            "distance_km": round(r["distance_km"], 2) if r.get("distance_km") is not None else None,
            "map_link": f"https://www.google.com/maps?q={r['lat']},{r['lon']}",
            "osm_tags": r["tags"],
        })

    return {"results": out}


# ----------------------------- WhatsApp webhook -----------------------------

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    # Minimal defensive parsing to support WhatsApp Cloud API shape
    try:
        entries = payload.get("entry", [])
        if not entries:
            # Some integrations send plain messages array
            messages = payload.get("messages") or []
        else:
            changes = entries[0].get("changes", [])
            messages = changes[0].get("value", {}).get("messages", []) if changes else []
    except Exception:
        messages = []

    if not messages:
        return {"ok": True, "note": "no messages"}

    msg = messages[0]

    # Recognize location message
    if msg.get("type") == "location":
        lat = msg["location"].get("latitude")
        lon = msg["location"].get("longitude")
        # If the user included text in the same update (rare), try to detect service
        service = "hospital"  # default
        # call tool
        results = overpass_query(lat, lon, DEFAULT_RADIUS_KM, AMENITY_MAP.get(service, service))
        # Prepare WhatsApp-friendly output (simple text lines)
        text_lines = []
        if not results:
            text_lines.append("No nearby results found.")
        for r in results:
            line = f"{r['name']}\n{r['address']}\nCall: {r['contact']}\nDistance: {round(r['distance_km'],2)} km\n{ 'Map: ' + 'https://www.google.com/maps?q=' + str(r['lat']) + ',' + str(r['lon']) }\n"
            text_lines.append(line)

        # In a real integration you'd call WhatsApp send-message endpoint here.
        # We'll return the formatted messages in the HTTP response for testing.
        return {"messages": text_lines}

    # If it's text, try to parse intent (police/hospital/fire)
    if msg.get("type") == "text":
        text = msg.get("text", {}).get("body", "").lower()
        # fallback: if user says "find hospital" and also shares live location previously,
        # ideally you'd store user last location in a DB. For minimal version, we require explicit location.
        # So here we reply asking user to share location if not provided.
        if any(k in text for k in ["hospital", "hosp", "medical"]):
            service = "hospital"
        elif any(k in text for k in ["police", "station"]):
            service = "police"
        elif any(k in text for k in ["fire", "fire station"]):
            service = "fire_station"
        elif any(k in text for k in ["office", "municipal", "townhall"]):
            service = "public_office"
        else:
            service = None

        if service:
            # Ask the user to share their location via WhatsApp Attach -> Location
            prompt = f"Please share your location in WhatsApp so I can find nearby {service.replace('_',' ')}s. Tap Attach → Location → Send current location."
            return {"reply_text": prompt}

    return {"ok": True}


# ----------------------------- Run -----------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)