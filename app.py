import os
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from yt_dlp import YoutubeDL
import uuid

app = Flask(__name__, static_folder='.', static_url_path='')

# Vercel allows writing ONLY to the /tmp directory
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/info', methods=['POST'])
def get_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            resolutions = set()
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('height'):
                    resolutions.add(f['height'])
            
            resolutions = sorted(list(resolutions), reverse=True)
            options = []
            
            for r in resolutions:
                options.append({
                    "id": f"bestvideo[height<={r}][ext=mp4]+bestaudio[ext=m4a]/best[height<={r}]", 
                    "label": f"{r}p (Video + Audio MP4)"
                })
            
            options.append({"id": "bestaudio[ext=m4a]/bestaudio", "label": "Audio Only (M4A/MP3)"})

            return jsonify({
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "uploader": info.get('uploader'),
                "formats": options
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['GET'])
def download_video():
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    if not url or not format_id:
        return jsonify({"error": "Missing parameters"}), 400

    # Generate unique filename
    unique_id = str(uuid.uuid4())
    outtmpl = str(DOWNLOAD_DIR / f"{unique_id}.%(ext)s")

    ydl_opts = {
        'format': format_id,
        'outtmpl': outtmpl,
        'noplaylist': True,
        'concurrent_fragment_downloads': 10,
        'ffmpeg_location': 'ffmpeg', # Vercel automatically provides FFmpeg in the PATH
        'merge_output_format': 'mp4',
    }

    if format_id.startswith("bestaudio"):
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Find the downloaded file
            filename = ydl.prepare_filename(info)
            if format_id.startswith("bestaudio"):
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            elif not filename.endswith('.mp4'):
                filename = filename.rsplit('.', 1)[0] + '.mp4'

        # Stream the file to the user's browser
        return send_file(
            filename,
            as_attachment=True,
            download_name=f"{info.get('title', 'video')}.{filename.split('.')[-1]}"
        )
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500