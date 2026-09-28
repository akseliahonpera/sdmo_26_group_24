Folder contains needed nginx conf file and needed Dockerfile for Building the Nginx docker image.

1. Go to Edge_gateway folder.
2. Create certs folder to the Edge_gateway folder if not yet created.
	
	Edge_gateway
		    \
		    |_
		    | \certs
		    |_
		    | \Dockerfile
		    |_
		    | \nginx_conf_edge_gateway.conf
		    |_
		    | \readme.txt

3. Move created cert files to the certs folder. 

	       certs
	            \
		    |_
		    | \ca.crt
		    |_
		    | \edge_gateway.crt
		    |_
		    | \edge_gateway.key


4. Ensure that backend api is running on port localhost:5000!
   Ensure that edge device is calling to port 7878 and depending to your hosts file server_name on line 67 of   
   nginx_conf_edge_gateway.conf should be either your selected domain for localhost or 127.0.0.1/localhost or if hosting to outer net your public ip.

5. Open cmd, powershell, git bash(!), whichever you can use to handle docker from command line in your machine.
Go to Edge_gateway folder with your command line tool.

6. Type "docker build -t test_image ." without the exlamation marks and hit enter.  (notice the last dot, it is important).
-This builds the image to your local docker repo.

7. Go to Docker desktop and run the image in container, remember to set correct ports for opening from extra options, also doable on command line.

Try 
