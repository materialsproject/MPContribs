import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var graph = document.getElementById('graph');
var layout = {
    grid: {rows: 1, columns: 2, xgap: 0.1, subplots:[['xy','x2y']]},
    margin: {l: 40, b: 40, t: 30, r: 0},
    showlegend: false, xaxis: {title: 'mᵉ [mₑ]'},
    xaxis2: {title: 'mʰ [mₑ]'}, yaxis: {title: 'SLME|1000nm [%]'},
}

var graph_columns = [['mᵉ', 'SLME|1000nm'], ['mʰ', 'SLME|1000nm']];
var markers = [
    {color: '#B087D6', size: 10, line: {width: 1, color: 'black'}},
    {color: '#538F71', size: 10, line: {width: 1, color: 'black'}},
]
var names = ['SLME vs mᵉ', 'SLME vs mʰ']
var api_url = window.api['host'] + 'projects/screening_inorganic_pv/graph';
var gets = $.map(graph_columns, function(columns) {
    return $.get({
        url: api_url, data: {'columns': columns.join(',')},
        headers: window.api['headers']
    });
})

$.when.apply($, gets).done(function() {
    var data = [];
    $.each(arguments, function(index, response) {
        var r = response[0];
        data.push({
            x: r[0]['y'], y: r[1]['y'], text: r[1]['text'],
            name: names[index], mode: 'markers', type: 'scatter',
            marker: markers[index], xaxis: 'x'+(index+1), yaxis: 'y'
        });
    });
    Plotly.plot(graph, data, layout, {displayModeBar: true});
    graph.on('plotly_click', function(d){
        var cid = d.points[0].text;
        var url = '/explorer/' + cid;
        window.open(url, '_blank');
    });
    spinner_plot.stop();
});
