import Plotly from 'plotly';

var api_url = window.api['host'] + 'projects/jarvis_dft/graph';
var graph = document.getElementById('graph');
var layout = {
    margin: {t: 0, r: 0, l: 40, b: 25},
    yaxis: {title: 'Exfoliation Energy Eₓ [eV]', type: 'log', autorange: true},
    xaxis: {showticklabels: false},
    legend: {x: 0.05, y: 0.95},
    barmode: 'group'
};

var columns = ['NUS.Eₓ', 'JARVIS.Eₓ'];

$.get({
    url: api_url, data: {'columns': columns.join(',')},
    headers: window.api['headers']
}).done(function() {
    var data = arguments[0];
    $.each(data, function(idx, trace) {
        trace['type'] = 'bar';
        trace['name'] = columns[idx].split('.')[0];
    });
    Plotly.plot(graph, data, layout);
});
