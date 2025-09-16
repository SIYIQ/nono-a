server {
    listen 8080;
    server_name your_server_ip_or_domain.com; # 请替换成您的IP或域名

    # API 请求转发给 Gunicorn
    location /api/ {
        # 【关键修正】关闭代理缓冲
        # 这是解决流式响应问题的核心！
        proxy_buffering off;
        
        # 【关键修正】强制 Nginx 使用 HTTP/1.1 协议与后端通信
        # 并正确传递 Connection 头，以支持长连接
        proxy_http_version 1.1;
        proxy_set_header Connection "keep-alive";

        # 增加超时时间，防止长思考过程导致连接被切断
        proxy_read_timeout 86400s; # 24 小时
        proxy_send_timeout 86400s;

        # 传递必要的请求头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 将请求转发给 Gunicorn
        proxy_pass http://127.0.0.1:8001;
    }

    # 处理静态文件（例如你的 index.html）
    # 假设你的项目在 /home/sb_test/chat/chat 目录下，并且 index.html 在 templates 子目录
    location / {
        # 直接让 FastAPI/Gunicorn 处理根路径的请求
        # 因为它知道如何从 templates 文件夹渲染模板
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}