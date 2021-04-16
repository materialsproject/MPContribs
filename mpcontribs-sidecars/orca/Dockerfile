FROM quay.io/plotly/orca:873b958271e919b371e89045bc790b48dd173f2d

ENV BUILD_DIR "/var/www/image-exporter/build"
ENV PLOTLYJS_ARG "--plotlyJS $BUILD_DIR/plotly-bundle.js"

RUN mkdir -p $BUILD_DIR && \
  wget --tries=1 --no-check-certificate -O $BUILD_DIR/plotly-bundle.js \
  "https://plot.ly/static/plotlyjs/build/plotlyjs-bundle.js"
