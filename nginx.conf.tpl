upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name _;

    # 客户端请求体大小限制
    client_max_body_size 10M;

    # API 网关 - OpenAI 格式 (${LTM_BASE_PATH}/v1/)
    location ${LTM_BASE_PATH}/v1/ {
        proxy_pass http://backend/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 流式响应支持
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 86400s;
    }

    # 后端管理 API (${LTM_BASE_PATH}/api/)
    location ${LTM_BASE_PATH}/api/ {
        proxy_pass http://backend/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 健康检查
    location ${LTM_BASE_PATH}/health {
        proxy_pass http://backend/health;
        proxy_set_header Host $host;
    }

    # API 文档（生产环境可注释掉）
    location ${LTM_BASE_PATH}/docs {
        proxy_pass http://backend/docs;
        proxy_set_header Host $host;
    }

    location ${LTM_BASE_PATH}/redoc {
        proxy_pass http://backend/redoc;
        proxy_set_header Host $host;
    }

    location ${LTM_BASE_PATH}/openapi.json {
        proxy_pass http://backend/openapi.json;
        proxy_set_header Host $host;
    }

    # 前端静态文件 (${LTM_BASE_PATH}/)
    location ${LTM_BASE_PATH}/ {
        alias /usr/share/nginx/html/;
        index index.html;
        try_files $uri $uri/ ${LTM_BASE_PATH}/index.html;

        # 静态资源缓存
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # /ltm 无尾斜杠重定向到 /ltm/
    location = ${LTM_BASE_PATH} {
        return 301 ${LTM_BASE_PATH}/;
    }

    # 根路径重定向
    location = / {
        return 301 ${LTM_BASE_PATH}/;
    }

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml;
}
