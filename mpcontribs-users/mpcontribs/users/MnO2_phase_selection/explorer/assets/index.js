import Plotly from 'plotly';

var api_url = window.api['host'] + 'projects/MnO2_phase_selection/graph';
var graph = document.getElementById('graph');
var layout = {
    margin: {l: 40, t: 0, b: 25, r: 0},
    xaxis: {type: 'category', showticklabels: false, ticks: ''},
    yaxis: {title: 'Formation Enthalpy [eV/mol]'}
};

$.get({
    url: api_url, data: {'columns': 'ΔH'}, headers: window.api['headers']
}).done(function() {
    arguments[0][0]['type'] = 'bar';
    Plotly.plot(graph, arguments[0], layout);
});
