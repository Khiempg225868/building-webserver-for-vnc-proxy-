import tornado.ioloop
import tornado.web
import tornado.websocket
import hashlib
import time
import json
import logging
import asyncio
from typing import Dict, Optional
import socket
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('vnc-proxy')

class TokenManager:
    """Quản lý token và xác thực"""
    
    def __init__(self):
        # Sử dụng in-memory storage (có thể thay bằng Redis cho production)
        self.tokens = {}
        self.token_expiry = 3600  # 1 giờ
    
    def generate_token(self, node_id: str) -> str:
        """Tạo token cho node"""
        timestamp = str(int(time.time()))
        token_data = f"{node_id}:{timestamp}:{hashlib.sha256(node_id.encode()).hexdigest()}"
        token = hashlib.sha256(token_data.encode()).hexdigest()
        
        # Lưu token
        self.tokens[token] = {
            'node_id': node_id,
            'created_at': timestamp,
            'expires_at': int(time.time()) + self.token_expiry
        }
        
        logger.info(f"Generated token for node {node_id}: {token}")
        return token
    
    def validate_token(self, token: str, node_id: str) -> bool:
        """Xác thực token"""
        if token not in self.tokens:
            logger.warning(f"Token not found: {token}")
            return False
        
        token_info = self.tokens[token]
        
        # Kiểm tra node_id
        if token_info['node_id'] != node_id:
            logger.warning(f"Token node mismatch: expected {node_id}, got {token_info['node_id']}")
            return False
        
        # Kiểm tra expiration
        if time.time() > token_info['expires_at']:
            logger.warning(f"Token expired: {token}")
            del self.tokens[token]
            return False
        
        logger.info(f"Token validated for node {node_id}")
        return True
    
    def revoke_token(self, token: str):
        """Thu hồi token"""
        if token in self.tokens:
            node_id = self.tokens[token]['node_id']
            del self.tokens[token]
            logger.info(f"Revoked token for node {node_id}")

class VNCProxyHandler(tornado.websocket.WebSocketHandler):
    """Handler cho WebSocket proxy đến VNC server"""
    
    def initialize(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self.vnc_socket = None
        self.vnc_thread = None
        self.running = False
    
    def open(self, node_id, token):
        """Kết nối WebSocket được mở"""
        logger.info(f"WebSocket connection attempt for node {node_id}")
        
        # Xác thực token
        if not self.token_manager.validate_token(token, node_id):
            self.close(4001, "Invalid or expired token")
            return
        
        # Map node_id đến VNC port
        vnc_ports = {
            "vm1": 5900,
            "vm2": 5901
        }
        
        if node_id not in vnc_ports:
            self.close(4002, "Unknown node ID")
            return
        
        vnc_port = vnc_ports[node_id]
        vnc_host = "localhost"
        
        # Kết nối đến VNC server
        try:
            self.vnc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.vnc_socket.connect((vnc_host, vnc_port))
            self.running = True
            
            # Khởi động thread để đọc dữ liệu từ VNC
            self.vnc_thread = threading.Thread(target=self._read_from_vnc)
            self.vnc_thread.daemon = True
            self.vnc_thread.start()
            
            logger.info(f"Connected to VNC server {vnc_host}:{vnc_port} for node {node_id}")
            
        except Exception as e:
            logger.error(f"VNC connection error: {e}")
            self.close(4003, f"VNC connection failed: {str(e)}")
    
    def _read_from_vnc(self):
        """Đọc dữ liệu từ VNC server và gửi qua WebSocket"""
        try:
            while self.running:
                data = self.vnc_socket.recv(4096)
                if not data:
                    break
                # Gửi dữ liệu qua WebSocket
                self.write_message(data, binary=True)
        except Exception as e:
            logger.error(f"Error reading from VNC: {e}")
        finally:
            self.running = False
    
    def on_message(self, message):
        """Xử lý message từ client - gửi đến VNC server"""
        try:
            if self.vnc_socket and self.running:
                self.vnc_socket.send(message)
        except Exception as e:
            logger.error(f"Error sending to VNC: {e}")
            self.close()
    
    def on_close(self):
        """Đóng kết nối"""
        self.running = False
        if self.vnc_socket:
            self.vnc_socket.close()
        logger.info("WebSocket connection closed")

class GenerateTokenHandler(tornado.web.RequestHandler):
    """API để generate token"""
    
    def initialize(self, token_manager: TokenManager):
        self.token_manager = token_manager
    
    def post(self):
        """Generate token cho node"""
        try:
            data = json.loads(self.request.body)
            node_id = data.get('nodeId')
            
            if not node_id:
                self.set_status(400)
                self.write({'error': 'nodeId is required'})
                return
            
            token = self.token_manager.generate_token(node_id)
            
            self.write({
                'token': token,
                'nodeId': node_id,
                'expires_in': self.token_manager.token_expiry
            })
            logger.info(f"Generated token for {node_id}")
            
        except Exception as e:
            self.set_status(500)
            self.write({'error': str(e)})
            logger.error(f"Token generation error: {e}")

class AccessHandler(tornado.web.RequestHandler):
    """API để truy cập VNC console"""
    
    def initialize(self, token_manager: TokenManager):
        self.token_manager = token_manager
    
    def get(self):
        """Trả về trang VNC console"""
        server_id = self.get_argument('serverID')
        token = self.get_argument('token')
        
        # Xác thực token
        if not self.token_manager.validate_token(token, server_id):
            self.render("disconnected.html")
            return
        
        # Hiển thị trang VNC
        self.render("vnc_console.html", 
                   server_id=server_id, 
                   token=token,
                   websocket_url=f"/websocket/{server_id}/{token}")

class HealthHandler(tornado.web.RequestHandler):
    """API health check"""
    
    def get(self):
        self.write({'status': 'ok', 'service': 'vnc-proxy'})

def make_app():
    """Tạo Tornado application"""
    token_manager = TokenManager()
    
    return tornado.web.Application([
        (r"/api/gentoken", GenerateTokenHandler, {'token_manager': token_manager}),
        (r"/api/access", AccessHandler, {'token_manager': token_manager}),
        (r"/websocket/([^/]+)/([^/]+)", VNCProxyHandler, {'token_manager': token_manager}),
        (r"/health", HealthHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static"}),
    ], template_path="templates")

def main():
    # Khởi chạy server
    app = make_app()
    app.listen(8888)
    logger.info("VNC Proxy Server started on port 8888")
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
