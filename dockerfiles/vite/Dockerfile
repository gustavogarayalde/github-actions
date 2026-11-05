FROM nginx:1.27-alpine

RUN apk add --no-cache jq

COPY ./dist /usr/share/nginx/html
COPY ./start.sh /docker-entrypoint.d/40-runtime-environment.sh
RUN chmod +x /docker-entrypoint.d/40-runtime-environment.sh

RUN cat > /etc/nginx/conf.d/default.conf <<'EOF'
server {
    listen 3000;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location = /environment.json {
        default_type application/json;
        add_header Cache-Control "no-store" always;
        try_files $uri =404;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }
}
EOF

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
