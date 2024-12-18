import time
import threading
import sys
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import os
import hashlib
import requests


class HTTP_handler(BaseHTTPRequestHandler):
    def do_GET(self):
        s = self.path
        global database

        if s.startswith('/SET?'):
            # Extraction des paramètres
            params = parse_qs(s[5:])
            key: str = params.get('key', [None])[0]
            value: str = params.get('value', [None])[0]
            sync = int(params.get('sync', [0])[0])


            # Validation des paramètres
            if key is None or value is None:
                self._send_response({"result": "0", "error": "Missing key or value"})
                return

            # Insertion dans la base de données
            if any(block["key"] == key for block in database):  # Vérification si la clé existe déjà
                self._send_response({"result": "0", "error": "Key already exists"})
            else:
                index = str(len(database))
                prev = database[-1]["id"] if database else "none"
                new_block = {
                    "index": index,
                    "key": key,
                    "value": value,
                    "prev": prev,
                }
                new_block["id"] = calculate_id(new_block)

                database.append(new_block)
                self._send_response({"result": "1", "block": new_block})

                save_data()

                if sync == 0:
                    for server in servers.values():
                        try:
                            url = f'http://{server["host"]}:{server["port"]}/SET?key={key}&value={value}&sync=1'
                            response = requests.get(url, timeout=5)
                            print(
                                f'Blockchain synchronisée avec le serveur {server["host"]}:{server["port"]} - Réponse: {response.status_code}')
                        except requests.exceptions.RequestException as e:
                            print(
                                f'Erreur lors de la synchronisation avec le serveur {server["host"]}:{server["port"]}: {e}')


        elif s.startswith('/GET?'):
            # Extraction des paramètres
            params = parse_qs(s[5:])
            key = params.get('key', [None])[0]

            # Validation des paramètres
            if key is None:
                self._send_response({"result": "0", "error": "Missing key"})
                return

            # Recherche du bloc correspondant dans la blockchain
            for block in database:
                if block["key"] == key:
                    self._send_response({"result": "1", "block": block})
                    return

            self._send_response({"result": "0", "error": "Key not found"})


        elif s.startswith('/SERVER?'):
            print("### /server a été appellée ###")
            # Extraction des paramètres pour l'annonce du nouveau serveur
            params = parse_qs(s[8:])
            host = params.get('host', [None])[0]
            port = params.get('port', [None])[0]
            sync = int(params.get('sync', [0])[0])

            server_key = f"{host}:{port}"

            # Validation des paramètres
            if host is None or port is None:
                self._send_response({"result": "0", "error": "Missing host or port"})
                return

            if server_key in servers:
                self._send_response({"result": "0", "error": "Server already exists"})
                return

            for server in servers.values():
                if server["host"] == host and server["port"] == port:
                    self._send_response({"result": "0", "error": "Server already exists"})
                    return

            if sync == 0:
                filtered_servers = {k: v for k, v in servers.items() if v["host"] != host or v["port"] != port}
                filtered_servers[str(len(filtered_servers))] = {"host": host_value, "port": port_value}
                try:
                    payload = {
                        "database": database,
                        "servers": filtered_servers
                    }
                    url = f"http://{host}:{port}/SYNC"
                    response = requests.get(url, json=payload)  # Envoyer les données blockchain actuelles
                    print(f"Sync {host}:{port} - Réponse: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"error during synchronization of {host}:{port}: {e}")

                for server in servers.values():
                    try:
                        url = f'http://{server["host"]}:{server["port"]}/SERVER?host={host}&port={port}&sync=1'
                        response = requests.get(url, timeout=5)
                        print(f'{server["host"]}:{server["port"]} adding {host}:{port} - Réponse: {response.status_code}')
                    except requests.exceptions.RequestException as e:
                        print(f"Error while adding {host}:{port}: {e}")

            servers[len(servers)] = {"host": host, "port": port}
            self._send_response({"result": "1", "message": "Server added successfully"})

            save_config()


        elif s.startswith('/KEYS'):
            blocks_data = [
                {"index": block["index"], "key": block["key"], "value": block["value"], "prev": block["prev"],
                 "id": block["id"]} for
                block in database]
            self._send_response({"result": "1", "blocks": blocks_data})


        elif s.startswith('/SYNC'):
            print("### /SYNC a été appellée ###")

            # Lecture des données reçues en POST
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            try:
                payload = json.loads(post_data.decode('utf-8'))  # Charger les données JSON
                new_database = payload.get("database", [])
                new_servers = payload.get("servers", {})
            except json.JSONDecodeError:
                self._send_response({"result": "0", "error": "Invalid JSON format"})
                return

            if len(database) == 0:
                database = new_database
            else:
                self._send_response({"result": "0", "error": "Current database is not empty"})

            # Mise à jour de la liste des serveurs
            for server_id, server_info in new_servers.items():
                if server_info not in servers.values():
                    servers[len(servers)] = server_info

            # Sauvegarder les nouvelles données dans le fichier
            save_data()
            save_config()
            self._send_response({"result": "1", "message": "Blockchain data synchronized successfully"})


        elif s.startswith('/LAST'):
            if database:
                last_entry = database[-1]
                self._send_response({"result": 1, "last_entry": last_entry})
            else:
                self._send_response({"result": 0, "error": "No entries in the database"})



        elif s.startswith('/REC?'):
            params = parse_qs(s[5:])
            idx = params.get("idx", [None])[0]
            if idx and idx.isdigit():
                idx = int(idx)
                if 0 <= idx < len(database):
                    entry = database[idx]
                    self._send_response({"result": 1, "entry": entry})
                else:
                    self._send_response({"result": 0, "error": "Index out of range"})
            else:
                self._send_response({"result": 0, "error": "Invalid index"})

        else:
            # Si la requête n'est ni un SET ni un GET
            self._send_response({"result": "0", "error": "Invalid endpoint"})

    def _send_response(self, response_data):
        """Helper method to send JSON response."""
        response_json = json.dumps(response_data)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(response_json.encode())


class Thread(threading.Thread):
    def __init__(self, ip, port):
        threading.Thread.__init__(self)
        self.daemon = True
        self.ip = ip
        self.port = port
        self.start()

    def run(self):
        load_data()
        httpd = HTTPServer((self.ip, self.port), HTTP_handler)
        print(f"Server running on {self.ip}:{self.port}")

        print("Servers Pairs:")
        for server_id, server_info in servers.items():
            print(f" - {server_info['host']}:{server_info['port']}")
        httpd.serve_forever()


def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py <config.json>")
        sys.exit(1)

    global config_file, data_file, host_value, port_value
    config_file = sys.argv[1]
    data_file = sys.argv[2]
    print(f"Loading config from {config_file}")

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            host_value = config.get('host', '0.0.0.0')
            port_value = config.get('port', 6660)
            port = int(port_value)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Erreur de lecture ou parsing du fichier JSON : {e}")
        sys.exit(1)
    except ValueError as ve:
        print(f"Erreur de validation du JSON : {ve}")
        sys.exit(1)

    try:
        threads = [Thread(host_value, port) for _ in range(1)]
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        save_data()
        save_config()
        print("Serveur interrompu par l'utilisateur, données sauvegardées.")
        sys.exit()


def load_data():
    global database, config, servers

    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            try:
                content = f.read().strip()
                database = json.loads(content) if content else []
            except json.JSONDecodeError:
                print("Fichier JSON corrompu, initialisation d'une base de données vide.")
                database = []
    else:
        database = []

    # Charger la liste des serveurs pairs à partir de la configuration
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            try:
                config = json.load(f)
                servers = config.get("pairs", {})
            except json.JSONDecodeError:
                print("Erreur dans la lecture du config file")
                servers = {}
    else:
        config = {}
        servers = {}


def save_data():
    with open(data_file, "w") as f:
        json.dump(database, f, indent=4)

def save_config():
    with open(config_file, "w") as f:
        config["pairs"] = servers  # Mettre à jour la liste des serveurs dans la config
        json.dump(config, f, indent=4)


def calculate_id(block):
    concat = block["index"] + block["key"] + block["value"] + block["prev"]
    return hashlib.sha224(concat.encode()).hexdigest()


def _broadcast_new_block(block):
    for server in servers.values():
        host = server["host"]
        port = server["port"]
        url = f"http://{host}:{port}/SET?key={block['key']}&value={block['value']}"
        try:
            response = requests.get(url)
            print(f"Notified server {host}:{port} about new block.")
        except requests.exceptions.RequestException as e:
            print(f"Error notifying server {host}:{port}: {e}")


if __name__ == "__main__":
    main()
