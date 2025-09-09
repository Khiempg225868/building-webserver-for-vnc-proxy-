#!/bin/sh

PORTS_TO_CHECK="5000 8080 6080"

for PORT in $PORTS_TO_CHECK; do
  

  if ! nc -z -w1 localhost "$PORT"; then
    # Nếu một cổng không mở, ghi log và thoát với mã lỗi ngay lập tức.
    log_msg "ERROR: Port $PORT is not listening"
    exit 1
  fi
done

exit 0