requirejs.config({
  baseUrl: 'static/js/lib',
  paths: {
    app: '../app',
    bootstrap: 'bootstrap.min',
    filestyle: 'bootstrap-filestyle.min',
    chosen: 'chosen.jquery.min',
    waitfor: 'jquery.waitFor',
    thebe: 'main-built'
    //"plotly": "plotly.min",
    //"underscore": "underscore-min",
    //"backbone": "backbone-min"
  },
  shim: {
    bootstrap: { deps: ['jquery'] },
    filestyle: { deps: ['bootstrap'] },
    chosen: { deps: ['jquery', 'bootstrap'] },
    waitfor: { deps: ['jquery'] },
    sandbox: { deps: ['archieml'] }
  }
});

//    <script type="text/javascript" charset="utf8" src="{{ url_for('static', filename='js/bootstrap-toggle.js') }}"></script>
//    <script type="text/javascript" charset="utf8" src="{{ url_for('static', filename='js/typedarray.js') }}"></script>
//    <script type="text/javascript" charset="utf8" src="{{ url_for('static', filename='js/plotly.min.js') }}"></script>
