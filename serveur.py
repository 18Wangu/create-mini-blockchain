import time
import threading
import sys
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

# Chemin du fichier de données
DATA_FILE = "data.blockchain.json"

# Base de données en mémoire
database = []

class HTTP_handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path
        response = {}
        
        # Gestion des requêtes /SET et /GET
        if path.startswith('/SET?'):
            params = parse_qs(path[5:])
            key = params.get('key', [None])[0]
            value = params.get('value', [None])[0]
            
            if key and value:
                # Vérifie si la clé existe déjà
                if any(entry["key"] == key for entry in database):
                    response = {"result": "0", "message": "Key already exists"}
                else:
                    # Ajoute un nouveau bloc à la base
                    new_block = {
                        "index": len(database),
                        "key": key,
                        "value": value
                    }
                    database.append(new_block)
                    response = {"result": "1", "message": "Key-Value pair added"}
            else:
                response = {"result": "0", "message": "Invalid parameters"}
        
        elif path.startswith('/GET?'):
            params = parse_qs(path[5:])
            key = params.get('key', [None])[0]
            
            if key:
                # Recherche de la clé
                result = next((entry for entry in database if entry["key"] == key), None)
                if result:
                    response = {"result": "1", "data": result}
                else:
                    response = {"result": "0", "message": "Key not found"}
            else:
                response = {"result": "0", "message": "Invalid parameters"}
        
        else:
            # Si la requête n'est ni /SET ni /GET
            response = {"result": "0", "message": "Invalid endpoint"}
        
        # Envoie la réponse JSON
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

class Thread(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.daemon = True
        self.host = host
        self.port = port
        self.start()

    def run(self):
        httpd = HTTPServer((self.host, self.port), HTTP_handler)
        print(f"Server running on {self.host}:{self.port}")
        httpd.serve_forever()

def load_config(config_file):
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
            host = config.get("host", "127.0.0.1")
            port = int(config.get("port", 6660))
            return host, port
    except FileNotFoundError:
        print(f"Configuration file {config_file} not found. Using defaults.")
        return "127.0.0.1", 6660
    except json.JSONDecodeError:
        print(f"Error parsing JSON configuration file {config_file}. Using defaults.")
        return "127.0.0.1", 6660

def load_data():
    """Charge les données depuis le fichier JSON s'il existe."""
    global database
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as file:
                database = json.load(file)
                print(f"Loaded {len(database)} records from {DATA_FILE}")
        except json.JSONDecodeError:
            print(f"Error loading data from {DATA_FILE}, starting with an empty database.")
    else:
        print(f"No data file found, starting with an empty database.")

def save_data():
    """Sauvegarde les données dans le fichier JSON."""
    try:
        with open(DATA_FILE, 'w') as file:
            json.dump(database, file, indent=4)
            print(f"Data saved to {DATA_FILE}")
    except IOError as e:
        print(f"Error saving data to {DATA_FILE}: {e}")

def main():
    # Charge la configuration et les données au démarrage
    config_file = "config.json"
    host, port = load_config(config_file)
    load_data()
    
    # Démarre le serveur
    threads = [Thread(host, port) for _ in range(1)]
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit, OSError):
        print('KeyboardInterrupt detected. Saving data and shutting down.')
        save_data()
        sys.exit()

if __name__ == "__main__":
    main()
