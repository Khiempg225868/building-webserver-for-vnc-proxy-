# building-webserver-for-vnc-proxy-

server1: 10.10.10.231
server2: 10.10.10.178
server3: 10.10.10.19
VIP ip : 10.10.10.244 (keepalived)

## Cấu trúc thư mục

```
.
├── ansible/              # Chứa các Playbook để tự động hóa triển khai
│   ├── compose-playbook.yaml
│   └── inventory.yaml
├── haproxy/              # Cấu hình cho HAProxy
│   └── haproxy.cfg
├── keepalived/           # Cấu hình và script cho Keepalived
│   ├── scripts/
│   │   └── check_ha.sh
│   ├── 10.10.10.19.conf
│   ├── 10.10.10.178.conf
│   ├── 10.10.10.231.conf
│   └── ...
├── noVNC/                # Thư mục chứa mã nguồn noVNC
│   └── ...
├── requirements.txt      # Thư viện Python yêu cầu cho ứng dụng
├── vnc_proxy.py          # Mã nguồn ứng dụng Python
├── Dockerfile            # Dockerfile của dự án
├── docker-compose.yaml   # Docker compose
└── README.md             # file hướng dẫn thực hiện
```

## Build Docker Image

1. **Build Docker image**

```bash
docker build -t khiempg225868/vnc-proxy-v2:2.2.2 .
```

2. **Push Docker image lên Docker Hub**

```bash
docker push khiempg225868/vnc-proxy-v2:2.2.2
```

3. **Chạy Ansible Playbook để triển khai**

- Sử dụng lệnh sau để chạy playbook để triển khai docker và docker compose, file cấu hình haproxy và cấu hình keepalived cho server:
  ```bash
  ansible-playbook -i ansible/inventory.yaml ansible/compose-playbook.yaml
  ```

## Chạy Ứng dụng

1. **Tạo mới token bằng lệnh curl**

```bash
curl -X POST -H "Content-Type: application/json" -d '{"nodeId": "vm2"}' http://10.10.10.244:5000/gentoken
```

**Ví dụ kết quả trả về:**

```json
{
  "token": "8f7d1e73-8df6-4c20-b3d4-018455a18e98"
}
```

2. **Truy cập ứng dụng qua trình duyệt**

Truy cập địa chỉ sau để sử dụng VNC qua web(thay serverID và token thực tế):

```
http://10.10.10.244:8080/vnc_lite.html?host=10.10.10.244&port=6080&path=access%3FserverID%3Dvm2%26token%3D8f7d1e73-8df6-4c20-b3d4-018455a18e98
```

## Minh họa kết quả

![Kết quả triển khai VNC Proxy](img/image.png)
