from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import re
import html
import yt_dlp

app = FastAPI(title="Instagram Downloader Engine")

# सभी प्लेटफॉर्म्स और डिवाइसेस के लिए फुल CORS परमिशन
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

def extract_via_graphql(shortcode: str):
    """लेयर 1: Instagram ऑफिशियल वेब GraphQL एंडपॉइंट (एंटी-ब्लॉक)"""
    url = f"https://www.instagram.com/graphql/query/?query_hash=b3055c01b4b222b8a47dc12b090e4e64&variables=%7B%22shortcode%22:%22{shortcode}%22%7D"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Mode": "cors"
    }
    try:
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code == 200:
            data = response.json()
            media = data.get("data", {}).get("shortcode_media", {})
            if media and media.get("is_video"):
                video_url = media.get("video_url")
                thumb = media.get("display_url", "")
                title = "Instagram Reel"
                try:
                    edges = media.get("edge_media_to_caption", {}).get("edges", [])
                    if edges:
                        title = edges[0].get("node", {}).get("text", "Instagram Reel")[:40]
                except Exception:
                    pass
                return video_url, thumb, title
    except Exception:
        pass
    return None, None, None

def extract_via_meta(clean_url: str):
    """लेयर 2: OpenGraph Meta Tags (WhatsApp/FB बॉट यूज़र एजेंट)"""
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        response = requests.get(clean_url, headers=headers, timeout=7)
        if response.status_code == 200:
            text = response.text
            match = re.search(r'<meta property="og:video" content="([^"]+)"', text) or \
                    re.search(r'"video_url":"([^"]+)"', text)
            thumb_match = re.search(r'<meta property="og:image" content="([^"]+)"', text)
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', text)

            if match:
                raw_video_url = match.group(1).replace("\\u0026", "&").replace("&amp;", "&")
                video_url = html.unescape(raw_video_url)
                thumb = ""
                if thumb_match:
                    thumb = html.unescape(thumb_match.group(1).replace("\\u0026", "&").replace("&amp;", "&"))
                title = "Instagram Video"
                if title_match:
                    title = html.unescape(title_match.group(1))[:40]
                return video_url, thumb, title
    except Exception:
        pass
    return None, None, None

@app.get("/api/info")
def get_video_info(url: str = Query(...)):
    # ट्रैकिंग पैरामीटर्स साफ़ करना
    clean_url = url.split("?")[0].strip()

    shortcode = None
    match = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]+)', clean_url)
    if match:
        shortcode = match.group(1)

    # 1. GraphQL से प्रयास
    if shortcode:
        v_url, thumb, title = extract_via_graphql(shortcode)
        if v_url:
            return {"success": True, "download_url": v_url, "title": title, "thumbnail": thumb}

    # 2. Meta Tags से प्रयास
    v_url, thumb, title = extract_via_meta(clean_url)
    if v_url:
        return {"success": True, "download_url": v_url, "title": title, "thumbnail": thumb}

    # 3. yt-dlp बैकअप
    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            video_url = info.get('url')
            if video_url:
                return {
                    "success": True,
                    "download_url": video_url,
                    "title": info.get('title', 'Instagram Video'),
                    "thumbnail": info.get('thumbnail', '')
                }
    except Exception:
        pass

    raise HTTPException(status_code=400, detail="Instagram link fetch failed. Please make sure the account is public.")

@app.get("/api/download")
def download_video_stream(url: str = Query(...)):
    """मोबाइल ब्राउज़र को सीधे डाउनलोड मोड में फ़ोर्स करने वाला हेडर एंडपॉइंट"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = requests.get(url, stream=True, headers=headers, timeout=20)
        
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 512),
            media_type="video/mp4",
            headers={
                "Content-Disposition": 'attachment; filename="Instagram_Video.mp4"',
                "Content-Type": "video/mp4"
            }
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to stream download.")
