upstream backend_servers {
    server 192.168.5.199:8000 weight=20;
    server 192.168.5.201:8000 weight=30;
    server 192.168.5.202:8000 weight=15;
    server 192.168.5.203:8000 weight=1;
}

server {
    listen 80;
    server_name pricinggame.ca www.pricinggame.ca;

    location /static/ {
        root /home/cooneycw/PycharmProjects/PricingProject/;
    }
    location /media/ {
        root /home/cooneycw/PycharmProjects/PricingProject/;
    }
    location / {
    proxy_pass http://backend_servers;
    proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

   proxy_connect_timeout 1s;
   proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
    }
}
