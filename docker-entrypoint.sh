#!/bin/bash
# 容器入口：保持运行，等待 solve.sh 修复后再由 test.sh 调用启动服务
echo "[entrypoint] 容器已启动，等待部署..."
exec sleep infinity
