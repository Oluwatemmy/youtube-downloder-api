from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os, yt_dlp, logging

app = FastAPI()

# Middleware for CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to ["chrome-extension://<extension-id>"] later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)

# Target resolutions
TARGET_RESOLUTIONS = ["360p", "480p", "720p", "1080p", "1440p", "2160p"]

class MyLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(f"❌ {msg}")

class DownloadRequest(BaseModel):
    url: HttpUrl
    resolution: str

def create_download_path():
    path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(path, exist_ok=True)
    return path

def format_size(size):
    if size is None:
        return "Unknown size"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (' ', '.', '_', '-')).strip()

def get_video_info(url):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch video info: {e}")

# Homepage route
@app.get("/")
async def homepage():
    return JSONResponse({
        "message": "Welcome to the Video Downloader API",
        "available_resolutions": TARGET_RESOLUTIONS,
        "documentation": "Visit /docs for API documentation"
    })


@app.post("/download")
async def download_video(request: DownloadRequest):
    url = request.url
    resolution = request.resolution
    download_path = create_download_path()

    info = get_video_info(str(url))
    formats = info.get('formats', [])
    filtered = [
        f for f in formats
        if f.get('vcodec') != 'none'
        and (f.get('format_note') == resolution or f.get('height') == int(resolution.replace('p', '')))
    ]

    if not filtered:
        raise HTTPException(status_code=404, detail="No matching format found")

    selected = filtered[0]
    title = sanitize_filename(info.get('title', 'video'))

    file_exists = any(
        os.path.exists(os.path.join(download_path, f"{title}.{ext}"))
        for ext in ['mp4', 'mkv', 'webm']
    )
    if file_exists:
        return JSONResponse({"status": "exists", "message": "Video already downloaded."})

    ydl_opts = {
        'logger': MyLogger(),
        'quiet': True,
        'no_warnings': True,
        'format': f"{selected['format_id']}+bestaudio/best",
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'ignoreerrors': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([str(url)])
        file_path = os.path.join(download_path, f"{title}.mp4")
        return FileResponse(file_path, media_type='video/mp4', filename=f"{title}.mp4")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")

@app.get("/info")
async def get_formats(url: HttpUrl):
    # Adding logging for debugging
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Fetching video info for URL: {url}")

    try:
        info = get_video_info(str(url))
        formats = info.get('formats', [])
        if not formats:
            logging.warning("No formats found in the info response.")
            raise HTTPException(status_code=404, detail="No valid video formats found.")
        filtered_formats = []

        if not filtered_formats:
            logging.warning("Filtered formats list is empty after applying TARGET_RESOLUTIONS.")
            raise HTTPException(status_code=404, detail="No valid video formats found.")

        logging.info(f"Raw formats from yt_dlp ({len(formats)} entries):")
        for f in formats:
            logging.info(f"  - {f.get('format_id')}: {f.get('format_note')} ({f.get('height')}p) | {f.get('vcodec')})")
            resolution = f.get('format_note') or f.get('height')
            if isinstance(resolution, int):
                resolution = f"{resolution}p"
            if f.get('vcodec') != 'none' :
                filtered_formats.append({
                    'format_id': f['format_id'],
                    'resolution': resolution,
                    'filesize': format_size(f.get('filesize') or f.get('filesize_approx')),
                    'ext': f.get('ext')
                })

        logging.info(f"Video title: {info.get('title')}")
        logging.info(f"Available formats: {filtered_formats}")

        return {
            "title": info.get("title"),
            "available_formats": filtered_formats
        }
    
    except Exception as e:
        logging.error(f"Error fetching video info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch video info: {e}")


