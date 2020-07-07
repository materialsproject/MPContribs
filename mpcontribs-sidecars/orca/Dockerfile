FROM quay.io/plotly/orca:6f4b8a5481d366ba4c7d9d6abe9ea6509089e839

ENV BUILD_DIR "/var/www/image-exporter/build"
ENV PLOTLYJS_ARG "--plotlyJS $BUILD_DIR/plotly-bundle.js"

RUN mkdir -p $BUILD_DIR && \
  wget --tries=1 --no-check-certificate -O $BUILD_DIR/plotly-bundle.js \
  "https://plot.ly/static/plotlyjs/build/plotlyjs-bundle.js"
