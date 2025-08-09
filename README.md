
# 🗺️ Local Government Services Finder MCP Server

This project is an **MCP (Model Context Protocol) server** built with **FastAPI** that integrates with **Puch AI** and WhatsApp to find nearby **hospitals, police stations, fire stations, and public offices** using **OpenStreetMap Overpass API**.

It allows users to:
- Share their **live location** via WhatsApp
- Instantly get **name, address, contact number, distance, and Google Maps link** to the nearest essential government service
- Access these capabilities through Puch’s MCP tool ecosystem

---

## 🚀 Features
- **Automatic location detection** from WhatsApp location messages
- Support for **hospital**, **police station**, **fire station**, and **public office**
- Uses **OpenStreetMap Overpass API** (free & global coverage)
- Returns sorted results by **distance**
- Ready for deployment with **Docker** and **Railway.app**
- MCP-compliant `/tools` and `/call` endpoints for Puch integration

---

## 🛠 Tools Available

| Tool Name                   | Description                                       | Parameters                                           |
|-----------------------------|---------------------------------------------------|------------------------------------------------------|
| `find_nearest_hospital`     | Finds nearby hospitals                            | latitude, longitude, radius_km (optional)           |
| `find_nearest_police`       | Finds nearby police stations                      | latitude, longitude, radius_km (optional)           |
| `find_nearest_fire_station` | Finds nearby fire stations                        | latitude, longitude, radius_km (optional)           |
| `find_nearest_public_office`| Finds nearby public offices / municipal buildings | latitude, longitude, radius_km (optional)           |


## 📦 Installation

### 1️⃣ Clone the repository
```bash
git clone https://github.com/haris-peter/near-me.git
cd near-me
````

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Run locally

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at:

```
http://localhost:8000
```

---

## 🐳 Docker Deployment

### Build Docker image

```bash
docker build -t near-me .
```

### Run container

```bash
docker run -p 8000:8000 near-me
```



## 📡 API Endpoints

### List Tools

```http
GET /tools
```

### Call a Tool

```http
POST /call
Content-Type: application/json

{
  "tool": "find_nearest_hospital",
  "params": {
    "latitude": 10.8505,
    "longitude": 76.2711,
    "radius_km": 5
  }
}
```

### WhatsApp Webhook

```http
POST /whatsapp/webhook
```

* Accepts WhatsApp Cloud API messages
* If location is shared → returns nearby service details
* If text is sent → prompts to share location

---

## 📌 Example Response

```json
{
  "results": [
    {
      "name": "District Hospital",
      "address": "Main Road, City Center",
      "contact": "+91-1234567890",
      "distance_km": 1.23,
      "map_link": "https://www.google.com/maps?q=10.8505,76.2711",
      "osm_tags": { "amenity": "hospital" }
    }
  ]
}
```

