from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import re

app = FastAPI()

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def is_valid_url(url: str) -> bool:
    regex = r"^(https?:\/\/)?(www\.)?(instagram\.com|threads\.net)\/.+$"
    return bool(re.match(regex, url))

@app.get("/api/info")
def extract_media(url: str = Query(..., description="Media URL to parse")):
    if not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL. Only valid links are permitted.")

    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'socket_timeout': 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="Media not found or private.")

            # Direct stream extraction without holding on server
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                for f in reversed(info['formats']):
                    if f.get('ext') == 'mp4':
                        video_url = f.get('url')
                        break

            return {
                "success": True,
                "title": info.get("title", "Instagram Video"),
                "thumbnail": info.get("thumbnail"),
                "download_url": video_url or info.get("webpage_url"),
                "duration": info.get("duration"),
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch media. Please verify link accessibility.")
