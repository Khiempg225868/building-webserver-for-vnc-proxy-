import os
import uuid
import time
import threading
import socket
from urllib import parse as urlparse
from http import HTTPStatus
import copy
from http import cookies as Cookie
import logging

import websockify
from websockify import websockifyserver
from websockify import ProxyRequestHandler, WebSocketProxy
from flask import Flask, request, jsonify, abort

# Thiết lập logging
logging.basicConfig(level=logging.DEBUG)

VM_INFO = {
    'vm1': {'host': 'localhost', 'port': 5900},
    'vm2': {'host': 'localhost', 'port': 5901},
}

# Lưu trữ token: dict {token: {'vm_id': str, 'expires': timestamp}}
TOKENS = {}
TOKEN_EXPIRATION = 3600  # 1 giờ

app = Flask(__name__)

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
    
    # Lưu token với expiration
    TOKENS[token] = {
        'vm_id': node_id,
        'expires': time.time() + TOKEN_EXPIRATION
    }
    
    return jsonify({'token': token})

# API access: Đây là endpoint cho WebSocket, nhưng vì dùng Flask, chúng ta sẽ dùng nó để validate trước khi proxy
# Thực tế, websockify sẽ handle WebSocket, nên chúng ta tích hợp sau
@app.route('/access')
def access():
    server_id = request.args.get('serverID')
    token = request.args.get('token')
    
    if not server_id or not token:
        abort(400, 'Missing serverID or token')
    
    if token not in TOKENS:
        return 'Disconnected: Invalid token', 403
    
    token_info = TOKENS[token]
    if time.time() > token_info['expires']:
        del TOKENS[token]
        return 'Disconnected: Token expired', 403
    
    if token_info['vm_id'] != server_id:
        return 'Disconnected: Token does not match serverID', 403
    
    # Nếu đúng, ở đây chúng ta có thể redirect hoặc serve NoVNC page, nhưng để proxy WebSocket,
    # chúng ta sẽ dùng websockify ở phần dưới. API này chỉ validate cho demo.
    # Trong thực tế, /access sẽ là path cho WebSocket handshake.
    return 'Connected: Access granted to VNC of ' + server_id

# Lớp handler tương tự NovaProxyRequestHandler, đơn giản hóa cho local
class LocalVNCProxyRequestHandler(ProxyRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def new_websocket_client(self):
        # Lấy token và serverID từ path query
        parsed = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(parsed.query)
        token = query.get('token', [''])[0]
        server_id = query.get('serverID', [''])[0]

        if not token or not server_id:
            raise Exception("Missing token or serverID")

        if token not in TOKENS:
            self.send_close()
            raise Exception("Invalid token")

        token_info = TOKENS[token]
        if time.time() > token_info['expires']:
            del TOKENS[token]
            self.send_close()
            raise Exception("Token expired")

        if token_info['vm_id'] != server_id:
            print(f"Token vm_id: {token_info['vm_id']} does not match serverID: {server_id}")
            self.send_close()
            raise Exception("Token does not match serverID")

        # Lấy host/port từ VM_INFO
        if server_id not in VM_INFO:
            raise Exception("Invalid serverID")

        host = VM_INFO[server_id]['host']
        port = VM_INFO[server_id]['port']

        # Kết nối đến VNC socket
        tsock = socket.create_connection((host, port))

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

# Lớp proxy tương tự NovaWebSocketProxy
class LocalVNCWebSocketProxy(WebSocketProxy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def get_logger():
        # Có thể dùng logging, nhưng đơn giản print
        def logger():
            pass
        return logger

# Chạy server
def run_proxy():
    # Chạy websockify server trên port 6080, target là dynamic dựa trên handler
    server = WebSocketProxy(
        RequestHandlerClass=LocalVNCProxyRequestHandler,
        listen_host='0.0.0.0',
        listen_port=6080,
        target_host=None,  # Để handler tự xử lý
        target_port=None,
    )
    server.start_server()

if __name__ == '__main__':
    # Chạy Flask cho API trên port 5000
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5000}).start()
    
    # Chạy proxy WebSocket
    run_proxy()