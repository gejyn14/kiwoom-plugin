# 도커와 포드먼 모두에서 그대로 빌드됩니다 (podman build -f Dockerfile .).
# BuildKit 전용 문법을 쓰지 않습니다 — 포드먼 호환을 위해서입니다.
# 빌드 컨텍스트는 이 server/ 디렉터리입니다.
FROM python:3.13-slim

ARG VERSION="0.1.0"

LABEL org.opencontainers.image.title="kiwoom-mcp" \
      org.opencontainers.image.description="MCP server for Kiwoom Securities REST API" \
      org.opencontainers.image.source="https://github.com/gejyn14/kiwoom-plugin" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # 실수로 실거래에 붙는 것보다 안전한 방향.
    KIWOOM_DOMAIN=mock

# 루트로 돌리지 않는다. HOME을 주어야 ~/.kiwoom이 해석된다.
RUN useradd --create-home --uid 1000 kiwoom

WORKDIR /src
COPY . /src
# server의 의존성(kiwoom-cli, mcp)은 전부 PyPI에 있으므로 git이 필요 없습니다.
RUN pip install --no-cache-dir /src && rm -rf /src/* /src/.git

USER kiwoom
WORKDIR /home/kiwoom
EXPOSE 8765

# 컨테이너는 키체인이 없으므로 토큰을 주입해 씁니다. 호스트에서
# `kiwoom auth login`으로 발급한 토큰을 -e KIWOOM_TOKEN으로 넘기세요.
ENTRYPOINT ["kiwoom-mcp"]
# 컨테이너 안에서 0.0.0.0 바인드는 정상입니다. 비루프백이므로 서버가
# KIWOOM_MCP_AUTH_TOKEN을 요구하며, 호스트 노출은 -p 127.0.0.1:8765:8765로
# 제한하세요. stdio로 쓰려면 이 CMD를 덮습니다:
#   docker run -i --rm kiwoom-mcp --transport stdio
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
