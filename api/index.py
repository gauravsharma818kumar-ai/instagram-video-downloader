from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/info")
def get_video_info(url: str = Query(...)):
    # Clean URL (Remove query parameters like ?igsh=...)
    clean_url = url.split("?")[0]

    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            video_url = info.get('url')
            title = info.get('title', 'Instagram Video')
            thumbnail = info.get('thumbnail', '')
            
            if not video_url:
                raise Exception("No direct stream URL found")

            return {
                "success": True,
                "download_url": video_url,
                "title": title,
                "thumbnail": thumbnail
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Instagram block or invalid link. Please try another reel.")

@app.get("/api/download")
def download_file(url: str = Query(...)):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        req = requests.get(url, stream=True, headers=headers, timeout=15)
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 1024),
            media_type="video/mp4",
            headers={"Content-Disposition": 'attachment; filename="instagram_video.mp4"'}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to stream file.")
