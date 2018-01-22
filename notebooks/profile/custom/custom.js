console.log('executing custom.js ...');
requirejs.config({
  baseUrl: '/flaskproxy/tschaume/ingester/static/js/lib',
  paths: {
    underscore: 'underscore-min',
    backbone: "backbone-min",
    plotly: "plotly.min",
    "backgrid-paginator": "backgrid.paginator"
  },
  shim: {
    underscore: {exports: '_'},
    "backgrid-paginator": { deps: ['backgrid'] },
    "backgrid-filter": { deps: ['backgrid'] },
    "backgrid-grouped-columns": { deps: ['backgrid', 'backgrid-patch'] },
  }
});
require(['json.human']);
require([
    'backbone', 'backgrid', 'backgrid-paginator',
    'backgrid-filter', 'backgrid-grouped-columns'
]);
require(['plotly']);
console.log('DONE');
