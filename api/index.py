from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import requests
import re
import html
import yt_dlp

app = FastAPI(
    title="AllSavePro Media Core Engine",
    description="Universal Production Media Extraction and Streaming Engine",
    version="2.0.0"
)

# ---------------------------------------------------------
# Architecture Flag:
# False = High-Speed Direct Redirect (Optimized for Vercel)
# True  = Full Binary Proxy Stream (For Dedicated Servers / VPS)
# ---------------------------------------------------------
PROXY_MODE = False

# Strict CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "Content-Type"]
)

# Authorized Target Domains
ALLOWED_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "tiktok.com",
    "pinterest.com",
    "pin.it",
    "twitter.com",
    "x.com"
]

@app.get("/")
@app.get("/api/health")
def health_probe():
    """Health check endpoint for web crawlers and uptime monitoring"""
    return JSONResponse(status_code=200, content={"status": "healthy", "engine": "running"})

def validate_target_url(raw_url: str) -> str:
    """Sanitize URL to prevent SSRF and filter unwanted payloads"""
    if not raw_url or len(raw_url) > 500:
        raise HTTPException(status_code=400, detail="Invalid target link length.")
    
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in ["http", "https"]:
        raise HTTPException(status_code=400, detail="Invalid URI scheme.")
    
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Malformed host detected.")
    
    is_authorized = any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS)
    if not is_authorized:
        raise HTTPException(status_code=400, detail="Platform host not supported.")
    
    return raw_url.strip()

def extract_instagram_graphql(shortcode: str):
    """Tier 1: Direct High-Speed GraphQL Extractor for Instagram"""
    query_url = f"https://www.instagram.com/graphql/query/?query_hash=b3055c01b4b222b8a47dc12b090e4e64&variables=%7B%22shortcode%22:%22{shortcode}%22%7D"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15",
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*"
    }
    try:
        res = requests.get(query_url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", {}).get("shortcode_media", {})
            if data and data.get("is_video"):
                video_url = data.get("video_url")
                thumb = data.get("display_url", "")
                title = "Instagram Media"
                try:
                    edges = data.get("edge_media_to_caption", {}).get("edges", [])
                    if edges:
                        title = edges[0].get("node", {}).get("text", "Instagram Media")[:40]
                except Exception:
                    pass
                return video_url, thumb, title
    except Exception:
        pass
    return None, None, None

def extract_opengraph_meta(clean_url: str):
    """Tier 2: Meta OpenGraph Extractor for Facebook and Meta Assets"""
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        res = requests.get(clean_url, headers=headers, timeout=5)
        if res.status_code == 200:
            body = res.text
            match = re.search(r'<meta property="og:video" content="([^"]+)"', body) or \
                    re.search(r'"video_url":"([^"]+)"', body)
            thumb_match = re.search(r'<meta property="og:image" content="([^"]+)"', body)
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', body)

            if match:
                raw_media = match.group(1).replace("\\u0026", "&").replace("&amp;", "&")
                video_url = html.unescape(raw_media)
                thumb = html.unescape(thumb_match.group(1).replace("\\u0026", "&").replace("&amp;", "&")) if thumb_match else ""
                title = html.unescape(title_match.group(1))[:40] if title_match else "Social Video"
                return video_url, thumb, title
    except Exception:
        pass
    return None, None, None

@app.get("/api/info")
def get_media_payload(url: str = Query(...)):
    """Main extraction handler compatible with existing front-end structure"""
    valid_url = validate_target_url(url)

    # 1. Instagram Optimization Path
    if "instagram.com" in valid_url:
        shortcode_match = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]+)', valid_url)
        if shortcode_match:
            v_url, thumb, title = extract_instagram_graphql(shortcode_match.group(1))
            if v_url:
                return {"success": True, "download_url": v_url, "title": title, "thumbnail": thumb}

        v_url, thumb, title = extract_opengraph_meta(valid_url)
        if v_url:
            return {"success": True, "download_url": v_url, "title": title, "thumbnail": thumb}

    # 2. Universal Engine (Pinterest, Facebook, TikTok, X)
    try:
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(valid_url, download=False)
            stream_target = info.get('url')

            if not stream_target and 'formats' in info:
                for fmt in reversed(info['formats']):
                    if fmt.get('url'):
                        stream_target = fmt['url']
                        break

            if stream_target:
                return {
                    "success": True,
                    "download_url": stream_target,
                    "title": (info.get('title') or 'Social Video')[:40],
                    "thumbnail": info.get('thumbnail', '')
                }
    except Exception:
        pass

    raise HTTPException(status_code=400, detail="Failed to fetch video. Please verify the link is public.")

@app.get("/api/stream")
def process_media_stream(url: str = Query(...)):
    """Dual-mode streaming handler (Direct Redirect vs VPS Proxy Stream)"""
    if not url:
        raise HTTPException(status_code=400, detail="Target download URL is missing.")

    # Mode 1: Vercel Direct Redirect (Prevents Payload Drop)
    if not PROXY_MODE:
        return RedirectResponse(url=url)

    # Mode 2: Dedicated Server Binary Stream (Future VPS Mode)
    try:
        stream_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        upstream = requests.get(url, stream=True, headers=stream_headers, timeout=30)
        
        downstream_headers = {
            "Content-Disposition": 'attachment; filename="AllSavePro_Media.mp4"',
            "Content-Type": upstream.headers.get("Content-Type", "video/mp4"),
            "Access-Control-Allow-Origin": "*"
        }

        return StreamingResponse(
            upstream.iter_content(chunk_size=1024 * 512),
            media_type="video/mp4",
            headers=downstream_headers
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Proxy stream pipe failed.")
