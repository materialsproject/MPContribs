requirejs.config({
    baseUrl: '/mpcontribs/tschaume/static/js',
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
        'json-human': 'components/json-human/src/json.human',
        'js-cookie': 'components/js-cookie/src/js.cookie'
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
        'backgrid-filter': {deps: ['backgrid']}
        //waitfor: {deps: ['jquery']},
        //sandbox: {deps: ['archieml']},
    }
});

