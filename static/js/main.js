requirejs.config({
    paths: {
        jquery: 'components/jquery/dist/jquery',
        backbone: 'components/backbone/backbone',
        backgrid: 'components/backgrid/lib/backgrid',
        bootstrap: 'components/bootstrap/dist/js/bootstrap',
        filestyle: 'components/bootstrap-filestyle/src/bootstrap-filestyle',
        chosen: 'components/chosen/chosen.jquery',
        toggle: 'components/bootstrap-toggle/js/bootstrap-toggle',
        underscore: 'components/underscore/underscore',
        lunr: 'components/lunr.js/lunr',
        plotly: 'components/plotlyjs/plotly',
        'backgrid-select-all': 'components/backgrid-select-all/backgrid-select-all',
        'backgrid-filter': 'components/backgrid-filter/backgrid-filter',
        'backbone.paginator': 'components/backbone.paginator/lib/backbone.paginator',
        'backgrid-paginator': 'components/backgrid-paginator/backgrid-paginator',
        'backgrid-grouped-columns': 'components/backgrid-grouped-columns/backgrid-grouped-columns',
        'bootstrap-slider': 'components/seiyria-bootstrap-slider/dist/bootstrap-slider',
        'json.human': 'components/json-human/src/json.human',
        'js-cookie': 'components/js-cookie/src/js.cookie',
        'jupyter-widget-chemview': 'components/chemview/js/src/embed.js',
        'jquery.spin': 'components/spin.js/jquery.spin',
        'spin': 'components/spin.js/spin',
        'linkify': 'components/linkifyjs/linkify.amd',
        'linkify-element': 'components/linkifyjs/linkify-element.amd'
        //waitfor: 'jquery.waitFor',
        //thebe: 'main-built',
    },
    shim: {
        jquery: {exports: '$'},
        backbone: {deps: ['underscore', 'jquery'], exports: 'Backbone'},
        backgrid: {deps: ['backbone'], exports: 'Backgrid'},
        bootstrap: {deps: ['jquery']},
        filestyle: {deps: ['bootstrap']},
        chosen: { deps: ['jquery', 'bootstrap']},
        underscore: {exports: '_'},
        toggle: {deps: ['jquery', 'bootstrap']},
        'backgrid-select-all': {deps: ['backgrid']},
        'backgrid-filter': {deps: ['backgrid']},
        'backbone.paginator': {deps: ['backbone']},
        'backgrid-paginator': {deps: ['backgrid', 'backbone.paginator']},
        'backgrid-grouped-columns': {deps: ['backgrid']},
        'bootstrap-slider': {deps: ['jquery', 'bootstrap']},
        'jquery.spin': {deps: ['jquery']},
        'linkify-element': {deps: ['linkify']}
        //waitfor: {deps: ['jquery']},
        //sandbox: {deps: ['archieml']},
    }
});

requirejs(['bootstrap', 'bootstrap-slider'], function() {
    console.log('bootstrap loaded');
});
requirejs(['jquery', 'underscore'], function() {
    $(document).ready(function () {
        require(['js-cookie'], function(Cookies) {
            function csrfSafeMethod(method) {
                // these HTTP methods do not require CSRF protection
                return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
            }
            $.ajaxSetup({
                beforeSend: function(xhr, settings) {
                    if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                        var csrftoken = Cookies.get('csrftoken');
                        xhr.setRequestHeader("X-CSRFToken", csrftoken);
                    }
                }
            });
            $("#keygen").click(function(){
                chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXTZabcdefghiklmnopqrstuvwxyz'.split('');
                key = _.sample(chars, 16).join("");
                var saveData = $.ajax({
                    type: 'POST',
                    url: $('#dashboard_url').val(),
                    data: {'apikey': key},
                    dataType: "text",
                    success: function(data, textStatus, jqXHR) { $("#key").text(key); },
                    error: function(jqXHR, textStatus, errorThrown) { $("#key").text('ERROR'); }
                });
            });
        });
    });
});
