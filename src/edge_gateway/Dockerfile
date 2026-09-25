FROM nginx:latest

# Remove default config so it doesn't conflict
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy your custom config to where nginx actually reads it
COPY nginx_conf_edge_gateway.conf /etc/nginx/nginx.conf

EXPOSE 80 8443

CMD ["nginx", "-g", "daemon off;"]