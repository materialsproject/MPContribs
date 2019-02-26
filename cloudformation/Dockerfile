FROM kong:0.15.0-alpine

RUN luarocks install kong-oidc
RUN luarocks install kong-oidc-consumer

#CMD ["kong", "migrations", "bootstrap"] # TODO find better solution - only needs to run once
#CMD ["kong", "migrations", "up"]
