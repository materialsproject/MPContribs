FROM jupyter/scipy-notebook:d4cbf2f80a2a

WORKDIR work

RUN pip install --no-cache-dir mpcontribs-client==1.5.7 mpcontribs-io==1.5.9

RUN mkdir -p mpcontribs-webtzite/webtzite
COPY mpcontribs-webtzite/webtzite/package.json mpcontribs-webtzite/webtzite/
COPY package.json .
RUN npm install 2>&1
COPY mpcontribs-webtzite/webtzite/assets mpcontribs-webtzite/webtzite/assets
COPY webpack-binder.config.js webpack.config.js
COPY binder/binder.js .
RUN npm run webpack 2>&1

RUN mkdir /home/jovyan/.jupyter/custom && \
    mv -v /home/jovyan/work/dist /home/jovyan/.jupyter/custom/js
COPY binder/custom.js /home/jovyan/.jupyter/custom/
COPY binder/*.ipynb .

USER root
RUN chown -R ${NB_UID} ${HOME}/work
USER ${NB_USER}

RUN rm -f binder.js package-lock.json package.json webpack.config.js
RUN rm -rf node_modules
RUN rm -rf mpcontribs-webtzite

#ENV NODE_ENV development
#ENV SETUPTOOLS_SCM_PRETEND_VERSION 1.5.9
#COPY mpcontribs-io /tmp/mpcontribs-io
#RUN cd /tmp/mpcontribs-io && pip install --no-cache-dir -e .
