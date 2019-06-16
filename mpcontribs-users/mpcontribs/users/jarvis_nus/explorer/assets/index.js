import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/bar')
]);

var api_url = window.api['host'] + 'projects/jarvis_nus/graph';
var graph = document.getElementById('graph');
var layout = {
    margin: {t: 0, r: 0, l: 40, b: 25},
    yaxis: {title: 'Exfoliation Energy Eₓ [eV]', autorange: true},
    xaxis: {showticklabels: false},
    legend: {x: 0.05, y: 0.95},
    barmode: 'group'
};

var columns = ['NUS.Eₓ', 'JARVIS.Eₓ'];

$.get({
    url: api_url, data: {'columns': columns.join(',')},
    headers: window.api['headers']
}).done(function(data) {
    $.each(data, function(idx, trace) {
        trace['type'] = 'bar';
        trace['name'] = columns[idx].split('.')[0];
    });
    Plotly.plot(graph, data, layout, {displayModeBar: true, responsive: true});
    graph.on('plotly_click', function(d){
        var cid = d.points[0].text;
        var url = '/explorer/' + cid;
        window.open(url, '_blank');
    });
    spinner_plot.stop();
});
