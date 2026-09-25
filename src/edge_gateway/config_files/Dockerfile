FROM nginx:latest

# Remove default config so it doesn't conflict
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy your custom config to where nginx actually reads it
COPY nginx_conf_edge_gateway.conf /etc/nginx/nginx.conf


COPY certs/ca.crt       /etc/nginx/certs/ca.crt
COPY certs/edge_gateway.crt  /etc/nginx/certs/edge_gateway.crt
COPY certs/edge_gateway.key  /etc/nginx/certs/edge_gateway.key


EXPOSE 80 7777 8443

CMD ["nginx", "-g", "daemon off;"]