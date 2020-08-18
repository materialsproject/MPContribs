FROM quay.io/plotly/orca:159486a94fa49ba68a7a56e84af8a862911f0f31

ENV BUILD_DIR "/var/www/image-exporter/build"
ENV PLOTLYJS_ARG "--plotlyJS $BUILD_DIR/plotly-bundle.js"

RUN mkdir -p $BUILD_DIR && \
  wget --tries=1 --no-check-certificate -O $BUILD_DIR/plotly-bundle.js \
  "https://plot.ly/static/plotlyjs/build/plotlyjs-bundle.js"
