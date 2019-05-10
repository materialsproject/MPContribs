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

//var key = 'ΔE|optB88vdW [meV/atom]';
//var layout_jarvis = {
//    margin: {t: 0, r: 0, l: 40},
//    yaxis: {title: key}, showlegend: false
//};
//var data_jarvis = [{x: [], y: [], type: 'bar'}];
//for (i = 0; i < table_jarvis['rows'].length; i++) {
//    var row = table_jarvis['rows'][i];
//    if (row[key]) {
//        data_jarvis[0]['x'].push(row['formula']);
//        data_jarvis[0]['y'].push(row[key]);
//    }
//}
