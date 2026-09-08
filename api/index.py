from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
import requests
import re
import html
import yt_dlp

app = FastAPI(title="Universal Secure Media Engine")

# CORS पॉलिसी
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# भविष्य के विस्तार के लिए डोमेन सूची (भविष्य में facebook.com आदि जोड़ सकते हैं)
ALLOWED_DOMAINS = [
    "instagram.com",
    "www.instagram.com",
    "cdninstagram.com"
]

def sanitize_and_validate(url: str) -> str:
    """SSRF एवं दुर्भावनापूर्ण यूआरएल से सुरक्षा"""
    if not url or len(url) > 300:
        raise HTTPException(status_code=400, detail="Invalid link length.")
    
    parsed = urlparse(url.strip())
    if parsed.scheme not in ["http", "https"]:
        raise HTTPException(status_code=400, detail="Invalid protocol.")
    
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Malformed URL.")
    
    is_allowed = any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)
    if not is_allowed:
        raise HTTPException(status_code=400, detail="Unsupported platform.")
    
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def fetch_graphql(shortcode: str):
    """Tier 1: Instagram GraphQL API"""
    target = f"https://www.instagram.com/graphql/query/?query_hash=b3055c01b4b222b8a47dc12b090e4e64&variables=%7B%22shortcode%22:%22{shortcode}%22%7D"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15",
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*"
    }
    try:
        r = requests.get(target, headers=headers, timeout=6)
        if r.status_code == 200:
            data = r.json()
            media = data.get("data", {}).get("shortcode_media", {})
            if media and media.get("is_video"):
                video_url = media.get("video_url")
                thumb = media.get("display_url", "")
                title = "Video Media"
                try:
                    edges = media.get("edge_media_to_caption", {}).get("edges", [])
                    if edges:
                        title = edges[0].get("node", {}).get("text", "Video Media")[:40]
                except Exception:
                    pass
                return video_url, thumb, title
    except Exception:
        pass
    return None, None, None

def fetch_meta_tags(url: str):
    """Tier 2: Meta OpenGraph Tags"""
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            text = r.text
            match = re.search(r'<meta property="og:video" content="([^"]+)"', text) or \
                    re.search(r'"video_url":"([^"]+)"', text)
            thumb_match = re.search(r'<meta property="og:image" content="([^"]+)"', text)
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', text)

            if match:
                raw_url = match.group(1).replace("\\u0026", "&").replace("&amp;", "&")
                video_url = html.unescape(raw_url)
                thumb = html.unescape(thumb_match.group(1).replace("\\u0026", "&").replace("&amp;", "&")) if thumb_match else ""
                title = html.unescape(title_match.group(1))[:40] if title_match else "Social Video"
                return video_url, thumb, title
    except Exception:
        pass
    return None, None, None

@app.get("/api/info")
def extract_media(url: str = Query(...)):
    clean_url = sanitize_and_validate(url)

    shortcode = None
    m = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]+)', clean_url)
    if m:
        shortcode = m.group(1)

    # 1. GraphQL
    if shortcode:
        v_url, thumb, title = fetch_graphql(shortcode)
        if v_url:
            return {"success": True, "download_url": v_url, "title": title, "thumbnail": thumb}

    # 2. OpenGraph Meta
    v_url, thumb, title = fetch_meta_tags(clean_url)
    if v_url:
        return {"success": True, "download_url": v_url, "title": title, "thumbnail": thumb}

    # 3. yt-dlp Backup
    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            v_url = info.get('url')
            if v_url:
                return {
                    "success": True,
                    "download_url": v_url,
                    "title": info.get('title', 'Video Media'),
                    "thumbnail": info.get('thumbnail', '')
                }
    except Exception:
        pass

    raise HTTPException(status_code=400, detail="Unable to retrieve media stream. Verify public access.")

@app.get("/api/stream")
def force_download_stream(url: str = Query(...)):
    """iOS Safari एवं Android के लिए बाध्यकारी डाउनलोड हेडर स्ट्रीम"""
    parsed = urlparse(url)
    # केवल अधिकृत मीडिया होस्ट्स से प्रॉक्सी की अनुमति
    if not (parsed.hostname and ("cdninstagram.com" in parsed.hostname or "fbcdn.net" in parsed.hostname)):
        raise HTTPException(status_code=403, detail="Unauthorized streaming source.")

    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)"}
        req = requests.get(url, stream=True, headers=headers, timeout=25)
        
        response_headers = {
            "Content-Disposition": 'attachment; filename="Instagram_Video.mp4"',
            "Content-Type": "video/mp4",
            "Access-Control-Allow-Origin": "*"
        }
        
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 512),
            media_type="video/mp4",
            headers=response_headers
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Stream connection failed.")
