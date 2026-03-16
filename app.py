from flask import Flask, render_template, request, jsonify
from database import get_all_jobs, set_applied

app = Flask(__name__)


@app.route("/")
def index():
    jobs = get_all_jobs()
    return render_template("index.html", jobs=jobs)


@app.route("/apply", methods=["POST"])
def apply():
    data = request.get_json()
    set_applied(data["id"], data["applied"])
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
