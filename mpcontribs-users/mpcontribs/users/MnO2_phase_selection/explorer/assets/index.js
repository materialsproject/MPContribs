import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/bar')
]);

var api_url = window.api['host'] + 'projects/MnO2_phase_selection/graph';
var graph = document.getElementById('graph');
var layout = {
    margin: {l: 40, t: 0, b: 25, r: 0},
    xaxis: {type: 'category', showticklabels: false, ticks: ''},
    yaxis: {title: 'Formation Enthalpy [eV/mol]'}
};

$.get({
    url: api_url, data: {'columns': 'ΔH'}, headers: window.api['headers']
}).done(function(response) {
    response[0]['type'] = 'bar';
    Plotly.plot(graph, response, layout);
    graph.on('plotly_click', function(data){
        var cid = data.points[0].text;
        var url = '/explorer/' + cid;
        window.open(url, '_blank');
    });
    spinner_plot.stop();
});
