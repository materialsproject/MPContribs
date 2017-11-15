console.log('executing custom.js ...');
requirejs.config({
  baseUrl: '/flaskproxy/tschaume/ingester/static/js/lib',
  paths: {
    backbone: "backbone-min",
    plotly: "plotly.min",
    "backgrid-paginator": "backgrid.paginator"
  }
});
require(['json.human']);
require(['backbone', 'backgrid', 'backgrid-paginator', 'backgrid-filter']);
require(['plotly']);
console.log('DONE');
