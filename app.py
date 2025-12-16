
from flask import Flask, render_template, request, jsonify, send_file
import io, pandas as pd
from db import init_db, get_conn
from worker import start_bg, STOP

app = Flask(__name__)
init_db()

@app.route("/", methods=["GET","POST"])
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    url = request.form["url"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM crawl_state")
    cur.execute("INSERT INTO crawl_state VALUES ('running')")
    conn.commit()
    conn.close()
    start_bg(url)
    return "",204

@app.route("/stop", methods=["POST"])
def stop():
    import worker
    worker.STOP = True
    return "",204

@app.route("/status")
def status():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM recipes")
    count = cur.fetchone()[0]
    cur.execute("SELECT status FROM crawl_state")
    s = cur.fetchone()
    conn.close()
    return jsonify(status=s[0] if s else "idle", count=count)

@app.route("/download/<fmt>")
def download(fmt):
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM recipes", conn)
    conn.close()
    if fmt=="csv":
        return send_file(io.BytesIO(df.to_csv(index=False).encode()), as_attachment=True, download_name="recipes.csv")
    text="\n".join(df.url)
    return send_file(io.BytesIO(text.encode()), as_attachment=True, download_name="recipes.txt")

if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000)
