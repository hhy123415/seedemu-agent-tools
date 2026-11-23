FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev iproute2 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir evennia==5.0.1
COPY map-import.json /opt/evennia/map-import.json
COPY start.sh /opt/evennia/start.sh
COPY topology_editor /opt/evennia/topology_editor
COPY install_editor.py /opt/evennia/install_editor.py
WORKDIR /data
EXPOSE 4000 4001 4002
ENTRYPOINT ["sh", "/opt/evennia/start.sh"]
