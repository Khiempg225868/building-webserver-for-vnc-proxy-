# building-webserver-for-vnc-proxy-

## Giới thiệu

Dự án này cung cấp một WebSocket proxy cho phép truy cập VNC của máy ảo được tạo bằng virtual machine manager qua trình duyệt web (tương thích với noVNC). Proxy xác thực truy cập bằng token và chuyển tiếp dữ liệu giữa client và VNC server.

## Yêu cầu

- Python 3.8+
- Các thư viện: `websockify`, `flask`, `threading`, v.v.
- Máy ảo phải bật VNC server (mở port 5900, 5901...)

## Cài đặt thư viện (nếu chưa có)

```sh
pip install flask websockify
```

## Hướng dẫn chạy

### 1. Khởi động proxy và API

```sh
python vnc_proxy.py
```

- Proxy WebSocket sẽ chạy trên cổng `6080`.
- API Flask sẽ chạy trên cổng `5000`.

### 2. Lấy token truy cập cho máy ảo

Truy cập trình duyệt hoặc dùng curl:

```
http://localhost:5000/gentoken?nodeId=vm1
```

- Thay `vm1` bằng ID máy ảo bạn muốn truy cập.
- Kết quả trả về:
  ```json
  { "token": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" }
  ```

### 3. Chạy noVNC để truy cập VNC qua web

- Nếu chưa có noVNC, hãy clone về bằng lệnh:

  ```sh
  git clone https://github.com/novnc/noVNC.git
  ```

- Di chuyển vào thư mục chứa `vnc.html` của noVNC:
  ```sh
  cd noVNC
  python3 -m http.server 8080
  ```
- Mở trình duyệt truy cập:
  ```
  http://localhost:8080/vnc.html
  ```
- Trong phần **Settings** của noVNC, nhập:
  - **Host:** `localhost`
  - **Port:** `6080`
  - **Path:**
    ```
    access?serverID=vm1&token=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    ```
    (thay đúng serverID và token vừa lấy)

### 4. Kết nối và sử dụng

- Nhấn **Connect** trên noVNC để truy cập console VNC của máy ảo.

## Lưu ý

- Nếu thay đổi code hoặc restart proxy, hãy lấy lại token mới.
- Đảm bảo VNC server của máy ảo đang chạy và mở port.
- Có thể chỉnh sửa file `.gitignore` để loại trừ các file không muốn commit.

## Debug

- Kiểm tra log terminal nơi chạy proxy để xem thông báo xác thực token, kết nối VNC, lỗi, v.v.
- Nếu gặp lỗi "Invalid token", hãy lấy lại token mới và thử lại.
  **Chúc bạn thành công!**
