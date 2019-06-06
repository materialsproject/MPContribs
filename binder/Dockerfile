FROM jupyter/scipy-notebook

RUN pip install --no-cache-dir mpcontribs-client==1.5.7 mpcontribs-io==1.5.7
COPY binder/index.ipynb work/

RUN mkdir -p mpcontribs-webtzite/webtzite
COPY mpcontribs-webtzite/webtzite/package.json mpcontribs-webtzite/webtzite/
COPY package.json .
RUN npm install 2>&1

COPY mpcontribs-webtzite/webtzite/assets mpcontribs-webtzite/webtzite/assets

COPY webpack-binder.config.js webpack.config.js
COPY binder/binder.js .
RUN npm run webpack 2>&1

RUN mkdir /home/jovyan/.jupyter/custom && \
    mv -v /home/jovyan/dist /home/jovyan/.jupyter/custom/js
COPY binder/custom.js /home/jovyan/.jupyter/custom/

RUN rm -f binder.js package-lock.json package.json webpack.config.js
RUn rm -rf node_modules
