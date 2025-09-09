import os 
import uuid
import time
import threading
import socket
from urllib import parse as urlparse
from http import HTTPStatus
import logging

from websockify import ProxyRequestHandler, WebSocketProxy
from flask import Flask, request, jsonify
from pymongo import MongoClient

# Setup logging
# logging.basicConfig(level=logging.DEBUG)

VM_INFO = {
    'vm1': {'host': '10.10.10.24', 'port': 5901},
    'vm2': {'host': '10.10.10.24', 'port': 5902},
    'vm3': {'host': '10.10.10.24', 'port': 5905},
}

TOKEN_EXPIRATION = 3600  # 1 hour

app = Flask(__name__)
MONGO_URI = "mongodb://10.10.10.19:27017,10.10.10.231:27017,10.10.10.178:27017/?replicaSet=rs0"
client = MongoClient(MONGO_URI)
db = client["token_db"]
tokens_collection = db["tokens"] 

# API to generate token
@app.route('/gentoken', methods=['POST'])
def gentoken():
    data = request.json
    if not data or 'nodeId' not in data:
        return jsonify({'error': 'Missing nodeId'}), 400
    
    node_id = data['nodeId']
    if node_id not in VM_INFO:
        return jsonify({'error': 'Invalid nodeId'}), 404
    
    # Generate token UUID
    token = str(uuid.uuid4())
    
    # Save token with expiration time
    expires_timestamp = time.time() + TOKEN_EXPIRATION
    
    # Save token to MongoDB
    tokens_collection.insert_one({'token': token, 'vm_id': node_id, 'expires': int(expires_timestamp)})
    
    return jsonify({'token': token})



class LocalVNCProxyRequestHandler(ProxyRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    print("websocket connected")
    def new_websocket_client(self):
        print("Handling new websocket client")
        # Get token and serverID from path query
        parsed = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(parsed.query)
        token = query.get('token', [''])[0]
        server_id = query.get('serverID', [''])[0]

        if not token or not server_id:
            raise Exception("Missing token or serverID")

        # --- TOKEN VALIDATION LOGIC ---
        # Check token in the database
        token_info_db = tokens_collection.find_one({'token': token})

        if not token_info_db:
            self.send_close()
            raise Exception("Invalid or expired token")
        else: 
            token_info = {
                'vm_id': token_info_db['vm_id'],
                'expires': token_info_db['expires']
            }
        # Final check for validity and expiration
        if not token_info or time.time() > token_info['expires']:
            self.send_close()
            raise Exception("Invalid or expired token")
        
        if token_info['vm_id'] != server_id:
           print(f"Token vm_id: {token_info['vm_id']} does not match serverID: {server_id}")
           self.send_close()
           raise Exception("Token does not match serverID")
        
        # Get host/port from VM_INFO
        if server_id not in VM_INFO:
            raise Exception("Invalid serverID")

        host = VM_INFO[server_id]['host']
        port = VM_INFO[server_id]['port']
        tsock = socket.create_connection((host, port))

        # Function to watch for token expiration and close connection if needed
        def token_expiry_watcher(handler, token, tsock):
            while True:
                time.sleep(5) # Check every 5 seconds
                
                db_token = tokens_collection.find_one({'token': token})
                if not db_token or db_token['expires'] < time.time():
                    print("Token expired in DB, closing connection.")
                    try:
                        handler.send_close()
                        tsock.close()
                    except Exception:
                        pass
                    break
                

        # Start the token expiration watcher thread
        watcher_thread = threading.Thread(target=token_expiry_watcher, args=(self, token, tsock), daemon=True)
        watcher_thread.start()

        # Start the proxy
        try:
            self.do_proxy(tsock)
        except Exception:
            if tsock:
                tsock.close()
            raise

    def send_head(self):
        # Similar to Nova, handle directory if needed
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            parts = urlparse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                if self.path.startswith('//'):
                    self.send_error(HTTPStatus.BAD_REQUEST, "URI must not start with //")
                    return None
        return super().send_head()

# Run server
def run_proxy():
    # Run websockify server on port 6081, target is dynamic based on the handler
    server = WebSocketProxy(
        RequestHandlerClass=LocalVNCProxyRequestHandler,
        listen_host='0.0.0.0',
        listen_port=6081,
        target_host=None,  # Let the handler manage it
        target_port=None,
    )
    server.start_server()

if __name__ == '__main__':
    # Run Flask API on port 5001
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5001}).start()
    
    # Run WebSocket