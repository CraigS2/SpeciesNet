FROM python:3.11

RUN pip install --upgrade pip

COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY ./speciesnet /app

WORKDIR /app

#RUN apt-get update && \
#    apt-get install -y --no-install-recommends \
#    build-essential \
#    pkg-config \
#    default-libmysqlclient-dev
#    #apt-get clean && \
#    #rm -rf /var/lib/apt/lists/*UN pip install --upgrade pip

# only automated test startup uses the .test.sh file
COPY ./entrypoint.sh /
COPY ./entrypoint.test.sh /

# Dockerfile.test overrides ENTRYPOINT to use entrypoint.test.sh
ENTRYPOINT ["sh", "/entrypoint.sh"]

