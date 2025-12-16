from flask import Flask, render_template, request, send_file
import pandas as pd
import io

from crawler import CrawlOptions, crawl_for_recipes

app = Flask(__name__)
LAST_DF = None


@app.route("/", methods=["GET", "POST"])
def index():
    global LAST_DF
    results = None
    summary = None

    if request.method == "POST":
        url = request.form.get("url", "").strip()

        if url:
            opts = CrawlOptions(
                max_pages=int(request.form.get("max_pages", 25)),
                max_candidates=int(request.form.get("max_candidates", 300)),
                same_domain_only="same_domain_only" in request.form,
                verify_recipes="verify_recipes" in request.form,
            )

            rows = crawl_for_recipes(url, opts)
            df = pd.DataFrame(rows)
            df = df.sort_values(
                by=["is_recipe", "is_candidate"],
                ascending=[False, False],
            )

            LAST_DF = df
            results = df.to_dict(orient="records")
            summary = {
                "rows": len(df),
                "candidates": int(df["is_candidate"].sum()),
                "recipes": int(df["is_recipe"].sum()),
            }

    return render_template("index.html", results=results, summary=summary)


@app.route("/download/csv")
def download_csv():
    if LAST_DF is None:
        return "", 404

    buf = io.StringIO()
    LAST_DF.to_csv(buf, index=False)
    buf.seek(0)

    return send_file(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="recipes.csv",
    )


@app.route("/download/txt")
def download_txt():
    if LAST_DF is None:
        return "", 404

    urls = LAST_DF[LAST_DF["is_recipe"] == True]["url"].dropna().tolist()
    text = "\n".join(urls) + ("\n" if urls else "")

    return send_file(
        io.BytesIO(text.encode("utf-8")),
        mimetype="text/plain",
        as_attachment=True,
        download_name="recipes.txt",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
