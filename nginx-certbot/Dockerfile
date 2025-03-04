FROM nginx-certbot:5.2.1-nginx1.27.0

COPY ./default.conf /etc/nginx/conf.d/default.conf

## Optional - if you have Let's Encryp certificate already issued pre-load it
# COPY ./secrets/privkey.pem /etc/letsencrypt/live/<domain_name>/privkey.pem
# COPY ./secrets/fullchain.pem /etc/letsencrypt/f/live/<domain_name>ullchain.pem
# COPY ./secrets/chain.pem /etc/letsencrypt//live/<domain_name>chain.pem
