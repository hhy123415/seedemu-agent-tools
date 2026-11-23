FROM node:22-bookworm-slim
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates socat python3 python-is-python3 python3-pip xvfb xauth libgl1-mesa-dev libgles2-mesa-dev libosmesa6-dev build-essential libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev libxi-dev libxinerama-dev libxrandr-dev && rm -rf /var/lib/apt/lists/*
COPY patch_mindcraft.py /mindcraft/patch_mindcraft.py
WORKDIR /app
RUN git init . && git remote add origin https://github.com/mindcraft-bots/mindcraft.git && git fetch --depth 1 origin e1c1fc3ffa481506c2445fc639e16dba504b5920 && git checkout --detach e1c1fc3ffa481506c2445fc639e16dba504b5920 && rm -rf .git && python3 /mindcraft/patch_mindcraft.py /app && npm install
COPY region_queries.mjs /app/src/agent/commands/region_queries.mjs
COPY patch_region_queries.py /mindcraft/patch_region_queries.py
RUN python3 /mindcraft/patch_region_queries.py /app
COPY autonomy.mjs /app/src/agent/autonomy.mjs
COPY patch_autonomy.py /mindcraft/patch_autonomy.py
RUN python3 /mindcraft/patch_autonomy.py /app
COPY emuvista_agent /mindcraft/emuvista_agent
COPY packages /mindcraft/packages
COPY tool_runner.py patch_registered_tools.py /mindcraft/
COPY registered_tools.mjs /app/src/agent/commands/registered_tools.mjs
RUN python3 /mindcraft/patch_registered_tools.py /app
COPY semantic_collection.mjs /app/src/agent/library/semantic_collection.mjs
COPY patch_semantic_collection.py /mindcraft/patch_semantic_collection.py
RUN python3 /mindcraft/patch_semantic_collection.py /app
COPY configure.mjs autonomy.mjs start.sh /mindcraft/
ENTRYPOINT ["sh", "/mindcraft/start.sh"]
