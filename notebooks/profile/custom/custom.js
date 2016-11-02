console.log('executing custom.js ...');
requirejs.config({
  baseUrl: '/flaskproxy/tschaume/ingester/static/js/lib',
  paths: {
    backbone: "backbone-min",
    plotly: "plotly.min",
  }
});
require(['json.human']);
require(['backbone']);
require(['plotly']);
console.log('DONE');
