import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
from contextlib import closing
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DB = os.environ.get("MIN_DB", str(ROOT / "inventario.db"))
ROLES = ("Administrador", "Gerente", "Técnico")
SESSIONS = {}

def password(value, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), bytes.fromhex(salt), 200000)
    return salt + ":" + digest.hex()

def database():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init():
    with closing(database()) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, hash TEXT, role TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS parts(code TEXT PRIMARY KEY, name TEXT, category TEXT, qty INTEGER CHECK(qty>=0), location TEXT, minimum INTEGER, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, user TEXT, code TEXT, name TEXT, qty INTEGER, reason TEXT, status TEXT DEFAULT 'Pendiente', reviewer TEXT, date TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS moves(id INTEGER PRIMARY KEY, code TEXT, delta INTEGER, balance INTEGER, actor TEXT, reason TEXT, date TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        for name, role in zip(("admin", "gerente", "tecnico"), ROLES):
            db.execute("INSERT INTO users(name,hash,role) VALUES(?,?,?)", (name,password("Demo2026!"),role))
        with (ROOT / "piezas.csv").open(encoding="utf-8") as catalog:
            for p in csv.DictReader(catalog):
                db.execute("INSERT INTO parts(code,name,category,qty,location,minimum) VALUES(?,?,?,?,?,?)", tuple(p.values()))
                if int(p["qty"]):
                    move(db,p["code"],int(p["qty"]),int(p["qty"]),"admin","Carga inicial")

def move(db, code, delta, balance, actor, reason):
    db.execute("INSERT INTO moves(code,delta,balance,actor,reason) VALUES(?,?,?,?,?)",(code,delta,balance,actor,reason))

def required(value, message):
    if not value:
        raise ValueError(message)

def field(data, key):
    value = data[key].strip()
    required(0 < len(value) <= 160, "Completa los campos de texto (máximo 160 caracteres).")
    return value

def number(data, key, minimum=0):
    value = int(data[key])
    required(minimum <= value <= 1000000, "Cantidad fuera de rango.")
    return value

def rows(db, sql, args=()):
    return [dict(row) for row in db.execute(sql,args)]

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, kind="application/json", headers=None):
        if kind == "application/json":
            payload = json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type",kind+"; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        for key,value in (headers or {}).items():
            self.send_header(key,value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        files = {"/":("index.html","text/html"),"/style.css":("style.css","text/css"),"/ui.js":("ui.js","text/javascript")}
        if path in files:
            filename,kind = files[path]
            return self.reply(200,(ROOT/"web"/filename).read_bytes(),kind)
        self.api(path)

    def do_POST(self):
        self.api(urlsplit(self.path).path)

    def api(self, path):
        cookies = SimpleCookie(self.headers.get("Cookie",""))
        token = cookies["sid"].value if "sid" in cookies else ""
        try:
            with closing(database()) as db, db:
                if self.command == "POST":
                    required(self.headers.get_content_type()=="application/json", "Formato inválido.")
                    size = int(self.headers.get("Content-Length","0"))
                    required(0 < size <= 16000, "Tamaño de solicitud inválido.")
                    data = json.loads(self.rfile.read(size))
                    db.execute("BEGIN IMMEDIATE")
                if path == "/api/login" and self.command == "POST":
                    user = db.execute("SELECT * FROM users WHERE name=? AND active=1",(field(data,"name").lower(),)).fetchone()
                    if not user or not hmac.compare_digest(user["hash"],password(data["password"],user["hash"].split(":")[0])):
                        return self.reply(401,{"error":"Usuario o contraseña incorrectos."})
                    sid = secrets.token_urlsafe(32)
                    SESSIONS.pop(token,None)
                    SESSIONS[sid] = user["name"]
                    return self.reply(200,{},headers={"Set-Cookie":f"sid={sid}; HttpOnly; SameSite=Strict; Path=/"})
                user = db.execute("SELECT name,role FROM users WHERE name=? AND active=1",(SESSIONS.get(token),)).fetchone()
                if not user:
                    return self.reply(401,{"error":"Inicia sesión."})
                actor, role = user
                if path == "/api/state" and self.command == "GET":
                    requests = rows(db,"SELECT * FROM requests WHERE user=? ORDER BY id DESC",(actor,)) if role=="Técnico" else rows(db,"SELECT * FROM requests ORDER BY id DESC")
                    return self.reply(200,{"me":dict(user),"parts":rows(db,"SELECT * FROM parts WHERE active=1 ORDER BY code"),"requests":requests,"moves":rows(db,"SELECT * FROM moves ORDER BY id DESC") if role!="Técnico" else [],"users":rows(db,"SELECT name,role,active FROM users ORDER BY name") if role=="Administrador" else []})
                if path == "/api/report" and self.command == "GET" and role=="Gerente":
                    out = io.StringIO()
                    writer = csv.writer(out)
                    writer.writerow(["Código","Pieza","Categoría","Existencias","Ubicación","Mínimo"])
                    for p in db.execute("SELECT code,name,category,qty,location,minimum FROM parts WHERE active=1 ORDER BY code"):
                        writer.writerow(["'"+v if isinstance(v,str) and v.startswith(("=","+","-","@")) else v for v in p])
                    return self.reply(200,out.getvalue().encode("utf-8-sig"),"text/csv",{"Content-Disposition":"attachment; filename=inventario.csv"})
                if self.command != "POST":
                    return self.reply(404,{"error":"Ruta no disponible."})
                if path == "/api/logout":
                    SESSIONS.pop(token,None)
                    return self.reply(200,{},headers={"Set-Cookie":"sid=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
                permissions = {"part":"Administrador","archive":"Administrador","stock":"Administrador","user":"Administrador","request":"Técnico","review":"Gerente"}
                action = path.removeprefix("/api/")
                if permissions.get(action)!=role:
                    return self.reply(403,{"error":"Tu perfil no tiene permiso para esta acción."})
                self.change(db,action,data,actor)
                db.commit()
                self.reply(200,{})
        except (ValueError, KeyError, TypeError, AttributeError) as err:
            self.reply(400,{"error":str(err) or "Datos inválidos."})
        except sqlite3.IntegrityError:
            self.reply(409,{"error":"El código o usuario ya existe."})

    def change(self,db,action,d,actor):
        if action == "user":
            name = field(d,"name").lower()
            role = field(d,"role")
            required(role in ROLES,"Perfil inválido.")
            active = number(d,"active")
            required(active in (0,1),"Estado inválido.")
            current = db.execute("SELECT 1 FROM users WHERE name=?",(name,)).fetchone()
            require_password = not current or d.get("password")
            if require_password:
                required(8 <= len(d["password"]) <= 128,"La contraseña debe tener entre 8 y 128 caracteres.")
            required(name != actor or (active and role=="Administrador"),"Conserva activa tu cuenta administradora.")
            if current and not require_password:
                db.execute("UPDATE users SET role=?,active=? WHERE name=?",(role,active,name))
            else:
                db.execute("INSERT INTO users VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET hash=excluded.hash,role=excluded.role,active=excluded.active",(name,password(d["password"]),role,active))
            if current and (require_password or not active):
                for sid in [key for key,value in SESSIONS.copy().items() if value==name and name!=actor]:
                    SESSIONS.pop(sid,None)
            return
        if action == "review":
            req = db.execute("SELECT * FROM requests WHERE id=?",(number(d,"id",1),)).fetchone()
            required(req and req["status"]=="Pendiente","La solicitud ya fue resuelta o no existe.")
            status = field(d,"status")
            required(status in ("Aprobada","Rechazada"),"Resolución inválida.")
            if status=="Aprobada":
                qty = db.execute("UPDATE parts SET qty=qty-? WHERE code=? AND active=1 AND qty>=? RETURNING qty",(req["qty"],req["code"],req["qty"])).fetchone()
                required(qty,"Existencias insuficientes para aprobar la solicitud.")
                move(db,req["code"],-req["qty"],qty[0],actor,f"Solicitud SOL-{req['id']:03d} de {req['user']}")
            db.execute("UPDATE requests SET status=?,reviewer=? WHERE id=?",(status,actor,req["id"]))
            return
        code = field(d,"code").upper()
        part = db.execute("SELECT * FROM parts WHERE code=? AND active=1",(code,)).fetchone()
        if action=="part":
            fields = (field(d,"name"),field(d,"category"),field(d,"location"),number(d,"minimum"))
            if d.get("editing"):
                required(part,"Pieza no disponible.")
                db.execute("UPDATE parts SET name=?,category=?,location=?,minimum=? WHERE code=?",(*fields,code))
            else:
                qty = number(d,"qty")
                db.execute("INSERT INTO parts(code,name,category,location,minimum,qty) VALUES(?,?,?,?,?,?)",(code,*fields,qty))
                if qty:
                    move(db,code,qty,qty,actor,"Alta de pieza")
            return
        required(part,"Pieza no disponible.")
        if action=="archive":
            required(not db.execute("SELECT 1 FROM requests WHERE code=? AND status='Pendiente'",(code,)).fetchone(),"Resuelve primero las solicitudes pendientes de esta pieza.")
            db.execute("UPDATE parts SET active=0,qty=0 WHERE code=?",(code,))
            if part["qty"]:
                move(db,code,-part["qty"],0,actor,"Baja de pieza")
        if action=="stock":
            qty = number(d,"qty",1)
            balance = part["qty"]+qty
            db.execute("UPDATE parts SET qty=? WHERE code=?",(balance,code))
            move(db,code,qty,balance,actor,field(d,"reason"))
        if action=="request":
            qty = number(d,"qty",1)
            required(qty<=part["qty"],"La cantidad supera las existencias disponibles.")
            db.execute("INSERT INTO requests(user,code,name,qty,reason) VALUES(?,?,?,?,?)",(actor,code,part["name"],qty,field(d,"reason")))

if __name__ == "__main__":
    init()
    port = int(os.environ.get("MIN_PORT","8000"))
    print(f"Abre http://127.0.0.1:{port}",flush=True)
    ThreadingHTTPServer(("127.0.0.1",port),Handler).serve_forever()
