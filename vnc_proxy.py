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

# Thiết lập logging
# logging.basicConfig(level=logging.DEBUG)

VM_INFO = {
    'vm1': {'host': '10.10.10.24', 'port': 5901},
    'vm2': {'host': '10.10.10.24', 'port': 5902},
    'vm3': {'host': '10.10.10.24', 'port': 5905},
}

TOKEN_EXPIRATION = 3600  # 1 giờ

app = Flask(__name__)
MONGO_URI = "mongodb://10.10.10.19:27017,10.10.10.231:27017,10.10.10.178:27017/?replicaSet=rs0"
client = MongoClient(MONGO_URI)
db = client["token_db"]
tokens_collection = db["tokens"] # Đổi tên biến để tránh nhầm lẫn với dict TOKENS

# API để generate token
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
    
    # Lưu token vào bộ nhớ với thời gian hết hạn
    expires_timestamp = time.time() + TOKEN_EXPIRATION
    
    # Lưu token vào MongoDB
    tokens_collection.insert_one({'token': token, 'vm_id': node_id, 'expires': int(expires_timestamp)})
    
    # r.setex(f"TOKEN:{token}", TOKEN_EXPIRATION, json.dumps(token_data)) # <- ĐÃ XÓA
    return jsonify({'token': token})


# Lớp handler tương tự NovaProxyRequestHandler, đơn giản hóa cho local
class LocalVNCProxyRequestHandler(ProxyRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    print("websocket connected")
    def new_websocket_client(self):
        print("Handling new websocket client")
        # Lấy token và serverID từ path query
        parsed = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(parsed.query)
        token = query.get('token', [''])[0]
        server_id = query.get('serverID', [''])[0]

        if not token or not server_id:
            raise Exception("Missing token or serverID")

        # --- LOGIC XÁC THỰC TOKEN MỚI ---
        # 1. Kiểm tra trong bộ nhớ trước
        token_info_db = tokens_collection.find_one({'token': token})

        if not token_info_db:
            self.send_close()
            raise Exception("Invalid or expired token")
        else: 
            token_info = {
                'vm_id': token_info_db['vm_id'],
                'expires': token_info_db['expires']
            }
        # 3. Kiểm tra lần cuối
        if not token_info or time.time() > token_info['expires']:
            self.send_close()
            raise Exception("Invalid or expired token")
        
        if token_info['vm_id'] != server_id:
           print(f"Token vm_id: {token_info['vm_id']} does not match serverID: {server_id}")
           self.send_close()
           raise Exception("Token does not match serverID")
        
        # Lấy host/port từ VM_INFO
        if server_id not in VM_INFO:
            raise Exception("Invalid serverID")

        host = VM_INFO[server_id]['host']
        port = VM_INFO[server_id]['port']
        tsock = socket.create_connection((host, port))

        # Hàm kiểm tra token hết hạn và đóng kết nối nếu cần
        def token_expiry_watcher(handler, token, tsock):
            while True:
                time.sleep(5) # Kiểm tra mỗi 5 giây
                
                db_token = tokens_collection.find_one({'token': token})
                if not db_token or db_token['expires'] < time.time():
                    print("Token expired in DB, closing connection.")
                    try:
                        handler.send_close()
                        tsock.close()
                    except Exception:
                        pass
                    break
                

        # Khởi động thread kiểm tra token hết hạn
        watcher_thread = threading.Thread(target=token_expiry_watcher, args=(self, token, tsock), daemon=True)
        watcher_thread.start()

        # Bắt đầu proxy
        try:
            self.do_proxy(tsock)
        except Exception:
            if tsock:
                tsock.close()
            raise

    def send_head(self):
        # Tương tự Nova, xử lý directory nếu cần
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            parts = urlparse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                if self.path.startswith('//'):
                    self.send_error(HTTPStatus.BAD_REQUEST, "URI must not start with //")
                    return None
        return super().send_head()

# Chạy server
def run_proxy():
    # Chạy websockify server trên port 6081, target là dynamic dựa trên handler
    server = WebSocketProxy(
        RequestHandlerClass=LocalVNCProxyRequestHandler,
        listen_host='0.0.0.0',
        listen_port=6081,
        target_host=None,  # Để handler tự xử lý
        target_port=None,
    )
    server.start_server()

if __name__ == '__main__':
    # Chạy Flask cho API trên port 5001
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5001}).start()
    
    # Chạy proxy WebSocket
    run_proxy()