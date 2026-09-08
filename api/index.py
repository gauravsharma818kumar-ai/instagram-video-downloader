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
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get('url')
            title = info.get('title', 'Instagram Video')
            thumbnail = info.get('thumbnail', '')
            
            return {
                "success": True,
                "download_url": video_url,
                "title": title,
                "thumbnail": thumbnail
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid link or private video.")

# नया डायरेक्ट डाउनलोड फ़ीचर (जो फ़ोन में फ़ाइल सेव कराएगा)
@app.get("/api/download")
def download_file(url: str = Query(...)):
    try:
        req = requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        return StreamingResponse(
            req.iter_content(chunk_size=1024 * 1024),
            media_type="video/mp4",
            headers={"Content-Disposition": 'attachment; filename="instagram_video.mp4"'}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to stream file.")
