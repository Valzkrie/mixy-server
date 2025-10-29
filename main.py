"""
Python Multi-User Hosting + FTP + Web Hosting (Per User Fixed Port)
By Rerize4 © 2025

Fitur:
1. FTP Server (Port 2121, multi-user) auto reload user.
2. Web Hosting per user:
   - Port fix tiap user.
   - Support index.html dan index.php via php-cgi.
3. CLI Interaktif:
   - Tampilkan user (rapi dengan detail)
   - Tambah user
   - Hapus user
   - Ganti password
4. CLI Rapi + Warna
5. Copyright Rerize4
"""

import os
import json
import threading
import subprocess
from pathlib import Path
from flask import Flask, send_from_directory, abort, Response
from colorama import Fore, init

# FTP imports
try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except Exception:
    DummyAuthorizer = None

# Init Colorama
init(autoreset=True)

# ========== CONFIG ==========
CONFIG = {
    "FTP_HOST": "0.0.0.0",
    "FTP_PORT": 2121,
    "USERS_FILE": "users.json",
    "BASE_DIR": os.path.abspath(os.getcwd()),
    "START_PORT": 8081
}

# Default user data
DEFAULT_USERS = {
    "alice": {
        "password": "alicepass",
        "home": "users/alice",
        "perm": "elradfmwM",
        "port": 1111
    },
    "bob": {
        "password": "bobpass",
        "home": "users/bob",
        "perm": "elradfmwM",
        "port": 1112
    }
}

ftp_server_instance = None

# ========== USER MANAGEMENT ==========
def ensure_user_dirs(users_dict):
    for u, v in users_dict.items():
        home = Path(CONFIG['BASE_DIR']) / v['home']
        www = home / 'www'
        os.makedirs(www, exist_ok=True)
        index_file = www / 'index.html'
        if not index_file.exists():
            index_file.write_text(f"<html><head><title>{u}</title></head><body><h2>Website milik {u}</h2></body></html>")

def load_users():
    fn = Path(CONFIG['USERS_FILE'])
    if not fn.exists():
        with fn.open('w') as f:
            json.dump(DEFAULT_USERS, f, indent=2)
        users = DEFAULT_USERS
    else:
        with fn.open() as f:
            users = json.load(f)

    used_ports = [info.get("port") for info in users.values() if "port" in info]
    next_port = CONFIG["START_PORT"] if not used_ports else max(used_ports) + 1

    for u, v in users.items():
        if "port" not in v:
            v["port"] = next_port
            next_port += 1

    ensure_user_dirs(users)
    save_users(users)
    return users

def save_users(users):
    with open(CONFIG['USERS_FILE'], "w") as f:
        json.dump(users, f, indent=2)

def get_next_port(users):
    if not users:
        return CONFIG["START_PORT"]
    used_ports = [info.get("port", CONFIG["START_PORT"]) for info in users.values()]
    return max(used_ports) + 1

def add_user(username, password):
    users = load_users()
    if username in users:
        print(Fore.RED + f"User {username} sudah ada!")
        return
    next_port = get_next_port(users)
    users[username] = {
        "password": password,
        "home": f"users/{username}",
        "perm": "elradfmwM",
        "port": next_port
    }
    ensure_user_dirs(users)
    save_users(users)
    print(Fore.GREEN + f"User {username} berhasil ditambahkan (Port: {next_port}).")
    restart_ftp_server()

def delete_user(username):
    users = load_users()
    if username not in users:
        print(Fore.RED + f"User {username} tidak ditemukan!")
        return
    del users[username]
    save_users(users)
    print(Fore.YELLOW + f"User {username} berhasil dihapus.")
    restart_ftp_server()

def change_password(username, new_password):
    users = load_users()
    if username not in users:
        print(Fore.RED + f"User {username} tidak ditemukan!")
        return
    users[username]["password"] = new_password
    save_users(users)
    print(Fore.GREEN + f"Password user {username} berhasil diganti.")
    restart_ftp_server()

# ========== FTP SERVER ==========
def start_ftp_server_dynamic(host, port):
    global ftp_server_instance
    if DummyAuthorizer is None:
        print(Fore.RED + "⚠️ pyftpdlib belum terinstall!")
        return

    users = load_users()
    authorizer = DummyAuthorizer()
    for username, info in users.items():
        homedir = os.path.join(CONFIG['BASE_DIR'], info['home'])
        authorizer.add_user(username, info['password'], homedir, perm=info.get('perm', 'elradfmwM'))

    handler = FTPHandler
    handler.authorizer = authorizer
    address = (host, port)
    ftp_server_instance = FTPServer(address, handler)

    print(Fore.CYAN + f"[FTP] Running FTP on {host}:{port}")
    try:
        ftp_server_instance.serve_forever()
    except Exception as e:
        print("[FTP] Stopped:", e)

def restart_ftp_server():
    global ftp_server_instance
    if ftp_server_instance:
        try:
            ftp_server_instance.close_all()
        except Exception:
            pass
    threading.Thread(target=start_ftp_server_dynamic, args=(CONFIG['FTP_HOST'], CONFIG['FTP_PORT']), daemon=True).start()

# ========== HTTP PER USER ==========
def create_user_app(username):
    app = Flask(username)
    base = Path(CONFIG['BASE_DIR']) / USERS[username]['home'] / "www"

    @app.route('/')
    @app.route('/<path:filename>')
    def serve_user(filename="index.html"):
        safe_path = os.path.normpath(filename)
        if safe_path.startswith(".."):
            abort(403)
        file_path = base / safe_path
        if not file_path.exists():
            abort(404)

        if file_path.suffix == ".php":
            env = os.environ.copy()
            env["SCRIPT_FILENAME"] = str(file_path)
            env["REDIRECT_STATUS"] = "200"
            proc = subprocess.Popen(
                ["php-cgi"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate()
            output = stdout.decode(errors="ignore")
            if "\r\n\r\n" in output:
                _, body = output.split("\r\n\r\n", 1)
            elif "\n\n" in output:
                _, body = output.split("\n\n", 1)
            else:
                body = output
            return Response(body, mimetype="text/html")

        return send_from_directory(base, safe_path)

    return app

def start_user_http(username, port):
    app = create_user_app(username)
    print(Fore.MAGENTA + f"[HTTP] User {username} → http://0.0.0.0:{port}/")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ========== CLI INFO ==========
def print_user_info(users):
    print("\n" + Fore.CYAN + "="*80)
    print(Fore.YELLOW + "           🚀 Multi-User Hosting Server 🚀")
    print(Fore.CYAN + "="*80)
    for u, v in users.items():
        print(Fore.CYAN + " "*80)
        print(Fore.CYAN + "-"*80)
        print(Fore.YELLOW + f"💻 {u}")
        print(Fore.CYAN + "-"*80)
        print(Fore.CYAN + f"👤 User       : {u}")
        print(Fore.CYAN + f"🔑 Password   : {v['password']}")
        print(Fore.CYAN + f"📡 Host       : {CONFIG['FTP_HOST']}")
        print(Fore.CYAN + f"🔌 Port       : {CONFIG['FTP_PORT']}")
        print(Fore.CYAN + f"📂 Home       : {v['home']}")
        print(Fore.CYAN + f"🔐 Server     : ftp://{CONFIG['FTP_HOST']}:{CONFIG['FTP_PORT']}")
        print(Fore.CYAN + " "*80)
        print(Fore.CYAN + "-"*80)
        print(Fore.CYAN + f"🌐 IP         : {CONFIG['FTP_HOST']}")
        print(Fore.CYAN + f"🔌 PORT       : {v['port']}")
        print(Fore.CYAN + f"🌍 URL        : http://{CONFIG['FTP_HOST']}:{v['port']}/")
        print(Fore.CYAN + "-" * 80)

    print(Fore.YELLOW + "© 2025 Rerize4 Hosting\n")

# ========== MENU OPSI ==========
def cli_menu():
    while True:
        print(Fore.CYAN + "\n===== MENU OPSI =====")
        print("1. Tampilkan user")
        print("2. Tambah user")
        print("3. Hapus user")
        print("4. Ganti password user")
        print("5. Keluar")
        choice = input(Fore.YELLOW + "Pilih opsi: ")

        if choice == "1":
            print_user_info(load_users())
        elif choice == "2":
            username = input("Masukkan username: ")
            password = input("Masukkan password: ")
            add_user(username, password)
        elif choice == "3":
            username = input("Masukkan username yang mau dihapus: ")
            delete_user(username)
        elif choice == "4":
            username = input("Masukkan username: ")
            newpass = input("Masukkan password baru: ")
            change_password(username, newpass)
        elif choice == "5":
            print(Fore.RED + "Keluar menu.")
            break
        else:
            print(Fore.RED + "Pilihan tidak valid!")

# ========== RUN ==========
def main():
    global USERS
    USERS = load_users()

    restart_ftp_server()

    for u, v in USERS.items():
        t = threading.Thread(target=start_user_http, args=(u, v["port"]), daemon=True)
        t.start()

    print_user_info(USERS)
    cli_menu()

if __name__ == '__main__':
    main()
