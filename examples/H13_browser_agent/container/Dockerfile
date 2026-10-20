FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive DISPLAY=:99 AGENT_BROWSER_CONFIG=/run/h13/browser_connection.json
# 系统依赖与桌面分别缓存，失败时复用下载文件。 / Cache system and desktop dependencies separately, retaining downloads on failure.
RUN --mount=type=cache,id=domainservice-apt,target=/var/cache/apt,sharing=locked rm -f /etc/apt/apt.conf.d/docker-clean && printf '%s\n' 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 install -y python3 python3-venv iproute2 dnsutils dnsmasq-base ca-certificates curl
RUN --mount=type=cache,id=domainservice-apt,target=/var/cache/apt,sharing=locked rm -f /etc/apt/apt.conf.d/docker-clean && printf '%s\n' 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 install -y xvfb x11-utils x11vnc novnc openbox fonts-noto-cjk
RUN python3 -m venv /opt/venv
COPY agent/requirements.txt /opt/agent/requirements.txt
# 源码变化不会触发依赖重装；pip 下载保留在构建缓存。 / Source changes do not reinstall dependencies; retain pip downloads in build cache.
RUN --mount=type=cache,id=domainservice-pip,target=/root/.cache/pip,sharing=locked /opt/venv/bin/pip install --retries 3 --timeout 30 -r /opt/agent/requirements.txt
RUN --mount=type=cache,id=domainservice-apt,target=/var/cache/apt,sharing=locked rm -f /etc/apt/apt.conf.d/docker-clean && printf '%s\n' 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache && /opt/venv/bin/playwright install-deps chromium
RUN /opt/venv/bin/playwright install chromium
COPY agent/ /opt/agent/
COPY start.sh launch_browser.js egress_urls.txt /opt/h13/
WORKDIR /opt/agent
ENTRYPOINT ["bash", "/opt/h13/start.sh"]
