FROM node:22-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/* \
 && npm install --global @qloo/qloo-harness
WORKDIR /srv
COPY app app
COPY static static
ENV PORT=8080 QLOO_TRANSPORT=rest QLOO_BASE_URL=https://hackathon.api.qloo.com QLOO_TRUSTED_BASE_URL=https://hackathon.api.qloo.com
EXPOSE 8080
CMD ["python3", "-m", "app.server"]
