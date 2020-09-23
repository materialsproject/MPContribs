FROM quay.io/plotly/orca:a47c8b9ab8c1c3bbb957c340da220441de21b871

ENV BUILD_DIR "/var/www/image-exporter/build"
ENV PLOTLYJS_ARG "--plotlyJS $BUILD_DIR/plotly-bundle.js"

RUN mkdir -p $BUILD_DIR && \
  wget --tries=1 --no-check-certificate -O $BUILD_DIR/plotly-bundle.js \
  "https://plot.ly/static/plotlyjs/build/plotlyjs-bundle.js"
