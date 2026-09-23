from __future__ import annotations
import hashlib, json, os, subprocess, tarfile, tempfile
from pathlib import Path
from flask import Flask, jsonify, request, send_file

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=700*1024*1024
TOKEN=os.environ.get("MOONLIT_WORKER_TOKEN","").strip()
if not TOKEN:
    try: TOKEN=Path("/etc/secrets/moonlit_worker_token").read_text().strip()
    except Exception: TOKEN=""
PROFILES={
    "morning":(-18.0,-2.0,7,"anull"),
    "afternoon":(-19.0,-2.2,7,"anull"),
    "night":(-21.0,-2.8,8,"equalizer=f=3200:t=q:w=1.2:g=-1.4,highshelf=f=5200:g=3.2:w=0.8"),
    "short":(-17.0,-2.0,6,"equalizer=f=3200:t=q:w=1.2:g=-1.0,highshelf=f=5200:g=4.0:w=0.8"),
}

def run(args):
    return subprocess.run(args,check=True,text=True,capture_output=True)

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def authorized():
    if not TOKEN:return False
    return request.headers.get("Authorization","")==f"Bearer {TOKEN}"

@app.get("/health")
def health():
    return jsonify(status="ok",worker="moonlit-media-worker-v1",ffmpeg=True)

@app.post("/render")
def render():
    if not authorized():return jsonify(error="unauthorized"),401
    mode=str(request.form.get("mode","")).lower()
    profile=str(request.form.get("profile","")).lower()
    premastered=str(request.form.get("premastered","0")).lower() in {"1","true","yes"}
    try: duration=int(float(request.form.get("duration","0")))
    except Exception:return jsonify(error="bad duration"),400
    if mode not in {"short","long"} or profile not in PROFILES:return jsonify(error="bad mode/profile"),400
    if duration<5 or duration>10800:return jsonify(error="duration out of range"),400
    audio=request.files.get("audio"); image=request.files.get("image")
    if not audio or not image:return jsonify(error="audio and image required"),400
    td=Path(tempfile.mkdtemp(prefix="moonlit_"))
    src=td/"input_audio"; art=td/"image.png"
    audio.save(src); image.save(art)
    master=td/"master.flac"; video=td/"video.mp4"
    try:
        if premastered:
            run(["ffmpeg","-y","-loglevel","error","-i",str(src),"-ar","48000","-ac","2","-c:a","flac",str(master)])
        else:
            target,tp,lra,tone=PROFILES[profile]
            af=f"highpass=f=45,lowpass=f=16500,{tone},loudnorm=I={target}:TP={tp}:LRA={lra}"
            run(["ffmpeg","-y","-loglevel","error","-i",str(src),"-af",af,"-ar","48000","-ac","2","-c:a","flac","-compression_level","8",str(master)])
        aac=td/"audio.m4a"
        run(["ffmpeg","-y","-loglevel","error","-i",str(master),"-vn","-c:a","aac","-b:a","192k","-ar","48000","-ac","2",str(aac)])
        if mode=="short":
            vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0012,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,format=yuv420p"
            run(["ffmpeg","-y","-loglevel","error","-loop","1","-i",str(art),"-stream_loop","-1","-i",str(aac),"-t",str(duration),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","25","-c:a","copy","-shortest",str(video)])
        else:
            seg=td/"segment.mp4"
            vf="scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p"
            run(["ffmpeg","-y","-loglevel","error","-loop","1","-framerate","1","-i",str(art),"-t","60","-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","26","-tune","stillimage","-r","1","-an",str(seg)])
            run(["ffmpeg","-y","-loglevel","error","-stream_loop","-1","-i",str(seg),"-stream_loop","-1","-i",str(aac),"-t",str(duration),"-map","0:v:0","-map","1:a:0","-c","copy","-movflags","+faststart","-shortest",str(video)])
        manifest={"schema":"MOONLIT_REMOTE_MEDIA_V1","status":"PASS","mode":mode,
                  "duration":duration,"profile":profile,"premastered_input":premastered,
                  "master_sha256":sha256(master),"video_sha256":sha256(video)}
        (td/"manifest.json").write_text(json.dumps(manifest,indent=2))
        archive=td/"result.tar.gz"
        with tarfile.open(archive,"w:gz") as tf:
            tf.add(master,arcname="master.flac")
            tf.add(video,arcname="video.mp4")
            tf.add(td/"manifest.json",arcname="manifest.json")
        return send_file(archive,mimetype="application/gzip",as_attachment=True,download_name="moonlit-result.tar.gz")
    except subprocess.CalledProcessError:
        return jsonify(error="media_processing_failed"),500
    except Exception as e:
        return jsonify(error=type(e).__name__),500
