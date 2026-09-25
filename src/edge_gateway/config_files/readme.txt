Folder contains needed nginx conf file and needed Dockerfile for Building the Nginx docker image.


Some descriptions below:

FROM nginx:latest //Pulls official latest nginx base image from repo

# Remove default config so it doesn't conflict
RUN rm -f /etc/nginx/conf.d/default.conf  //shit gpt advice to remove default conf file, not sure if reasonable to do but whatever

# Copy your custom config to where nginx actually reads it
COPY nginx_conf_edge_gateway.conf /etc/nginx/nginx.conf //copy your config from the physical machine to dockers "virtual" machine 


COPY certs/ca.crt       /etc/nginx/certs/ca.crt // copy all certs and keys like this from your machine to dockers folder where 						// nginx configuration expects them
COPY certs/edge_gateway.crt  /etc/nginx/certs/edge_gateway.crt //same here
COPY certs/edge_gateway.key  /etc/nginx/certs/edge_gateway.key //same here


EXPOSE 80 7777 8443		//tell image that these ports are to be open, you must do this also when you spool up the container
			
CMD ["nginx", "-g", "daemon off;"] //launch parameters when the container starts (imagine launching Program from cmd, bash, etc.)