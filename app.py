from flask import Flask, render_template, request, redirect, url_for
import json
import os
import qrcode
import barcode
from barcode.writer import ImageWriter
from datetime import datetime

app = Flask(__name__)

DATA_FILE = "data/tickets.json"
QR_DIR = "static/qrcodes"
BARCODE_DIR = "static/barcodes"

os.makedirs(QR_DIR, exist_ok=True)
os.makedirs(BARCODE_DIR, exist_ok=True)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_qr(ticket_number):
    url = f"http://localhost:5000/monitor?ticket={ticket_number}"
    qr_path = os.path.join(QR_DIR, f"{ticket_number}.png")
    qrcode.make(url).save(qr_path)
    return f"/static/qrcodes/{ticket_number}.png"

def generate_barcode(ticket_number):
    EAN = barcode.get('code128', str(ticket_number), writer=ImageWriter())
    barcode_path = os.path.join(BARCODE_DIR, f"{ticket_number}.png")
    EAN.save(barcode_path[:-4])
    return f"/static/barcodes/{ticket_number}.png"

@app.route("/")
def home():
    return redirect("/monitor_config")

@app.route("/monitor_config")
def reception():
    data = load_data()
    return render_template("monitor_config.html", data=data)

@app.route("/set", methods=["POST"])
def set_config():
    data = load_data()
    data["reload_interval"] = int(request.form.get("reload_interval", data.get("reload_interval", 10)))
    data["wait_time_unit"] = int(request.form.get("wait_time_unit", data.get("wait_time_unit", 3)))
    save_data(data)
    return redirect(request.referrer or url_for("reception"))

@app.route("/adjust", methods=["POST"])
def adjust_number():
    delta = int(request.form.get("delta"))
    data = load_data()
    data["current_number"] += delta
    if data["current_number"] < 1:
        data["current_number"] = 1
    elif data["current_number"] > 999:
        data["current_number"] = 1
    save_data(data)
    return redirect(url_for("reception"))

@app.route("/issue", methods=["POST"])
def issue_ticket():
    data = load_data()
    data["current_number"] += 1
    if data["current_number"] > 999:
        data["current_number"] = 1
    ticket_number = data["current_number"]
    generate_qr(ticket_number)
    generate_barcode(ticket_number)
    data["tickets"].append({
        "number": ticket_number,
        "status": "受付",
        "scan_count": 0
    })
    save_data(data)
    return redirect(url_for("print_ticket", number=ticket_number))

@app.route("/print/<int:number>")
def print_ticket(number):
    qr_url = f"/static/qrcodes/{number}.png"
    barcode_url = f"/static/barcodes/{number}.png"
    data = load_data()
    return render_template("print_ticket.html", number=number, data=data, qr_url=qr_url, barcode_url=barcode_url)

@app.route("/管理")
def admin():
    data = load_data()
    return render_template("admin.html", data=data)

@app.route("/scan", methods=["POST"])
def scan_ticket():
    scanned_number = int(request.form.get("scanned_number"))
    data = load_data()
    for t in data["tickets"]:
        if t["number"] == scanned_number:
            t["scan_count"] += 1
            if t["scan_count"] == 1:
                t["status"] = "呼び出し"
            elif t["scan_count"] >= 2:
                data["tickets"].remove(t)
            break
    save_data(data)
    return redirect(url_for("admin"))

@app.route("/monitor")
def monitor():
    data = load_data()
    reload_interval = data.get("reload_interval", 10)
    wait_time_unit = data.get("wait_time_unit", 3)
    wait_list = get_waiting_numbers()
    latest = get_latest_number()
    history = sorted(get_called_numbers())[-10:]

    ticket = request.args.get("ticket")
    your_status = None
    if ticket and ticket.isdigit():
        your_status = "呼び出し済み" if int(ticket) in get_called_numbers() else "未呼出"

    return render_template(
        "monitor.html",
        latest=latest,
        history=history,
        your_number=ticket,
        your_status=your_status,
        wait_count=len(wait_list),
        wait_time_unit=wait_time_unit,
        reload_interval=reload_interval,
        store_name=data.get("store_name", "味付け焼肉"),
        update_time=datetime.now().strftime("%Y/%m/%d %H:%M")
    )

@app.route("/handle", methods=["POST"])
def handle_number():
    number = int(request.form.get("number"))
    data = load_data()
    ticket = next((t for t in data["tickets"] if t["number"] == number), None)

    if ticket is None:
        data["tickets"].append({
            "number": number,
            "status": "受付",
            "scan_count": 0
        })
        generate_qr(number)
        generate_barcode(number)
    elif ticket["scan_count"] == 0:
        ticket["scan_count"] = 1
        ticket["status"] = "呼び出し"
    elif ticket["scan_count"] >= 1:
        data["tickets"] = [t for t in data["tickets"] if t["number"] != number]

    save_data(data)
    return redirect(url_for("admin"))

@app.route("/reset", methods=["POST"])
def reset_tickets():
    data = load_data()
    data["tickets"] = []
    data["current_number"] = 0
    save_data(data)
    return redirect(url_for("admin"))

from flask import Flask, render_template, request, redirect, url_for, session
app.secret_key = "your_secret_key_here"  # セッション用の秘密キー

ADMIN_PASSWORD = "niku2929"

@app.route("/monitor_login", methods=["GET", "POST"])
def monitor_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["authenticated"] = True
            return redirect("/monitor_config")
        else:
            return render_template("login.html", error="パスワードが違います")
    return render_template("login.html")

@app.route("/monitor_config")
def monitor_config():
    if not session.get("authenticated"):
        return redirect("/monitor_login")
    data = load_data()
    return render_template("monitor_config.html", data=data)


# ユーティリティ関数
def get_latest_number():
    data = load_data()
    called = [t["number"] for t in data["tickets"] if t["status"] == "呼び出し"]
    return max(called) if called else "---"

def get_called_numbers():
    data = load_data()
    return [t["number"] for t in data["tickets"] if t["status"] == "呼び出し"]

def get_waiting_numbers():
    data = load_data()
    return [t["number"] for t in data["tickets"] if t["status"] == "受付"]

if __name__ == "__main__":
    app.run(debug=True)



