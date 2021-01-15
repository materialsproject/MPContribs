FROM quay.io/plotly/orca:580ce17101d6bcdae188322d68a99daa66d038a6

ENV BUILD_DIR "/var/www/image-exporter/build"
ENV PLOTLYJS_ARG "--plotlyJS $BUILD_DIR/plotly-bundle.js"

RUN mkdir -p $BUILD_DIR && \
  wget --tries=1 --no-check-certificate -O $BUILD_DIR/plotly-bundle.js \
  "https://plot.ly/static/plotlyjs/build/plotlyjs-bundle.js"
