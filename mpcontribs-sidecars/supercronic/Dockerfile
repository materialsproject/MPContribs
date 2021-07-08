FROM alpine:3.14.0

ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.1.12/supercronic-linux-amd64 \
    SUPERCRONIC=supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=048b95b48b708983effb2e5c935a1ef8483d9e3e \
    WAITFORIT=https://raw.githubusercontent.com/vishnubob/wait-for-it/3f4f2de63c4646f8496ad085009ec8ca52b66f24/wait-for-it.sh \
    API_HOSTS="localhost:5000 localhost:5002 localhost:5003"

RUN apk --update add --no-cache curl bash coreutils \
 && curl -fsSLO "$SUPERCRONIC_URL" \
 && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
 && chmod +x "$SUPERCRONIC" \
 && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
 && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic \
 && curl -o /usr/local/bin/wait-for-it.sh $WAITFORIT && \
    chmod +x /usr/local/bin/wait-for-it.sh

WORKDIR /app
COPY start.sh .
CMD wait-for-it.sh $API_HOSTS -s -t 60 -- ./start.sh
