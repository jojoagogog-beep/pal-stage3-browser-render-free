from __future__ import annotations
import base64, hashlib, json, os, subprocess, tarfile, tempfile, threading, time, uuid
from pathlib import Path
from flask import Flask, jsonify, request, send_file
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=700*1024*1024
PUBLIC_KEY_PEM='''-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA47Tk0F32vcp6TC3+aFqX
jEMCHsLMbZY0Ooq3w9AkVK92Z6KA/xLi3LR38m84hnzwtjNLWsgbwDSwBaOde31v
m51pOp8dzs9NbEO9BYkgMQ+bjvHYIwEtGdBErMZZl/qG3odDAqS13ojcCo1ri7tx
dqcMAvxBGJqlko4Rkq0GOLO4FPgSbS4jlmW+4TSUCp7PjpKIIzCu28Ql7npTED9X
BUM1tpqzrOfbQPPFnSxIEW/9RXrUrMjh0ZUax44H3zIZtKkaKrIA/947UMtvPokS
vlVg2Adj9fcCJqYCLoBhPt+LOw3Ph+Ehp6Rc3/KdeC+Lo4Hdy33OUP0PQ5VY0+By
JwIDAQAB
-----END PUBLIC KEY-----'''
PUBLIC_KEY=serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode())
PROFILES={"morning":(-18.0,-2.0,7,"anull"),"afternoon":(-19.0,-2.2,7,"anull"),
          "night":(-21.0,-2.8,8,"equalizer=f=3200:t=q:w=1.2:g=-1.4,highshelf=f=5200:g=3.2:w=0.8"),
          "short":(-17.0,-2.0,6,"equalizer=f=3200:t=q:w=1.2:g=-1.0,highshelf=f=5200:g=4.0:w=0.8")}
JOBS={}; LOCK=threading.Lock(); WORKER_LOCK=threading.Lock()
def authorized():
    try:
        ts=request.headers.get("X-Moonlit-Timestamp",""); nonce=request.headers.get("X-Moonlit-Nonce","")
        if abs(time.time()-int(ts))>300 or len(nonce)<16:return False
        sig=base64.b64decode(request.headers.get("X-Moonlit-Signature","").encode(),validate=True)
        PUBLIC_KEY.verify(sig,f"{ts}\n{nonce}".encode(),padding.PKCS1v15(),hashes.SHA256())
        return True
    except Exception:return False

def run(args): subprocess.run(args,check=True,text=True,capture_output=True)
def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def update(jid,**kw):
    with LOCK: JOBS.setdefault(jid,{}).update(kw)

@app.get("/health")
def health(): return jsonify(status="ok",worker="moonlit-media-worker-v2",async_jobs=True,auth="rsa")
def process_job(jid,td,mode,profile,premastered,duration):
    with WORKER_LOCK:
        try:
            update(jid,status="RUNNING",started_at=time.time())
            src=td/"input_audio"; art=td/"image.png"; master=td/"master.flac"; video=td/"video.mp4"
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
            manifest={"schema":"MOONLIT_REMOTE_MEDIA_V2","status":"PASS","mode":mode,"duration":duration,
                      "profile":profile,"premastered_input":premastered,
                      "master_sha256":sha256(master),"video_sha256":sha256(video)}
            (td/"manifest.json").write_text(json.dumps(manifest,indent=2))
            archive=td/"result.tar.gz"
            with tarfile.open(archive,"w:gz") as tf:
                tf.add(master,arcname="master.flac")
                tf.add(video,arcname="video.mp4")
                tf.add(td/"manifest.json",arcname="manifest.json")
            update(jid,status="DONE",finished_at=time.time(),result=str(archive))
        except Exception as e:
            update(jid,status="ERROR",finished_at=time.time(),error=type(e).__name__)

@app.post("/jobs")
def create_job():
    if not authorized(): return jsonify(error="unauthorized"),401
    mode=str(request.form.get("mode","")).lower()
    profile=str(request.form.get("profile","")).lower()
    premastered=str(request.form.get("premastered","0")).lower() in {"1","true","yes"}
    try: duration=int(float(request.form.get("duration","0")))
    except Exception:return jsonify(error="bad duration"),400
    audio=request.files.get("audio"); image=request.files.get("image")
    if mode not in {"short","long"} or profile not in PROFILES or duration<5 or duration>10800:
        return jsonify(error="bad request"),400
    if not audio or not image:return jsonify(error="audio and image required"),400
    jid=uuid.uuid4().hex
    td=Path(tempfile.mkdtemp(prefix=f"moonlit_{jid}_"))
    audio.save(td/"input_audio"); image.save(td/"image.png")
    update(jid,status="QUEUED",created_at=time.time())
    threading.Thread(target=process_job,args=(jid,td,mode,profile,premastered,duration),daemon=True).start()
    return jsonify(job_id=jid,status="QUEUED"),202

@app.get("/jobs/<jid>")
def job_status(jid):
    if not authorized(): return jsonify(error="unauthorized"),401
    with LOCK: j=dict(JOBS.get(jid) or {})
    if not j:return jsonify(error="not_found"),404
    return jsonify({k:v for k,v in j.items() if k!="result"})
@app.get("/jobs/<jid>/result")
def job_result(jid):
    if not authorized(): return jsonify(error="unauthorized"),401
    with LOCK: j=dict(JOBS.get(jid) or {})
    if not j:return jsonify(error="not_found"),404
    if j.get("status")!="DONE":
        return jsonify(error="not_ready",status=j.get("status")),409
    p=Path(j["result"])
    if not p.exists():return jsonify(error="result_missing"),410
    return send_file(p,mimetype="application/gzip",as_attachment=True,download_name="moonlit-result.tar.gz")
