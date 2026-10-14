FROM python:3.12-slim
WORKDIR /srv
COPY app app
COPY static static
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "app.server"]
