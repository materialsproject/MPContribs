import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var SQMAX = 33.7; var MASSMAX = 1.5;
var xmin = 0; var xmax = 1.65;
var ymin = 0; var ymax = 37.0;

var graph = document.getElementById('graph');
var layout = {
    grid: {rows: 1, columns: 2, xgap: 0.02, subplots:[['xy','x2y']]},
    margin: {l: 60, b: 50, t: 50, r: 5}, hovermode: 'closest', showlegend: false,
    xaxis: {
        title: 'mᵉ [mₑ]', range: [xmin, xmax], linewidth: 3, linecolor: 'black',
        showgrid: false, ticks: 'inside', tickwidth: 2, ticklen: 8, mirror: true
    },
    xaxis2: {
        title: 'mʰ [mₑ]', range: [xmin, xmax], linewidth: 3, linecolor: 'black',
        showgrid: false, ticks: 'inside', tickwidth: 2, ticklen: 8, mirror: 'all'
    },
    yaxis: {
        title: 'SLME|1000nm [%]', range: [ymin, ymax], linewidth: 3,
        linecolor: 'black', showgrid: false, ticks: 'inside', tickwidth: 2,
        ticklen: 8, mirror: 'all'
    },
    font: {family: 'Arial, sans-serif', size: 18},
    annotations: [
        {x: MASSMAX/2, y: SQMAX+1, xref: 'x1', text: '<b>S–Q limit</b>', showarrow: false, font: {color: '#960000'}},
        {x: MASSMAX/2, y: SQMAX+1, xref: 'x2', text: '<b>S–Q limit</b>', showarrow: false, font: {color: '#960000'}},
        {x: MASSMAX+0.05, y: SQMAX/2, xref: 'x1', text: '<b>effective mass screen</b>', showarrow: false, font: {color: '#005078'}, textangle: -90},
        {x: MASSMAX+0.05, y: SQMAX/2, xref: 'x2', text: '<b>effective mass screen</b>', showarrow: false, font: {color: '#005078'}, textangle: -90},
        {x: 0.25, y: 1.05, xref: 'paper', yref: 'paper', text: '<b>SLME vs. electron effective mass<b>', showarrow: false, xanchor: 'center', yanchor: 'middle'},
        {x: 0.75, y: 1.05, xref: 'paper', yref: 'paper', text: '<b>SLME vs. hole effective mass<b>',     showarrow: false, xanchor: 'center', yanchor: 'middle'}
	]
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
    var gets_args = arguments;
    var gets2 = $.map(gets_args, function(response) {
        var identifiers = response[0][0]['x'];
        return $.get({
            url: window.api['host'] + 'contributions/', data: {
                'projects': 'screening_inorganic_pv',
                'identifiers': identifiers.join(','),
                'per_page': identifiers.length,
                'mask': 'content.data'
            }, headers: window.api['headers']
        });
    });
    $.when.apply($, gets2).done(function() {
        var data = [];
        $.each(arguments, function(index, response) {
            var r = gets_args[index][0];
            var text = $.map(response[0], function(d) {
                var cid = d['id'];
                var s = cid + '<br>' + JSON.stringify(d['content']['data'], null, 2);
                var s = s.replace(/"/g, '').replace(/,/g, '<br>');
                return s.replace(/{/g, '<br>').replace(/}/g, '');
            });
            data.push({
                x: r[0]['y'], y: r[1]['y'], text: text, hoverlabel: {'align': 'left'},
                name: names[index], mode: 'markers', type: 'scatter',
                marker: markers[index], xaxis: 'x'+(index+1), yaxis: 'y'
            });
            data.push({
                x: [xmin, xmax], y: [SQMAX, SQMAX],
                name: 'SQ limit', mode: 'lines',
                line: {color: '#960000', dash: 'dot'},
                showlegend: false, hoverinfo: 'none',
                xaxis: 'x'+(index+1), yaxis: 'y'
            });
            data.push({
                x: [MASSMAX, MASSMAX], y: [ymin, ymax],
                mode: 'lines', line: {color: '#005078', dash: 'dot'},
                showlegend: false, hoverinfo: 'none',
                xaxis: 'x'+(index+1), yaxis: 'y'
            });

        });
        Plotly.plot(graph, data, layout, {displayModeBar: true});
        graph.on('plotly_click', function(d){
            var cid = d.points[0].text.split('<br>')[0];
            var url = '/explorer/' + cid;
            window.open(url, '_blank');
        });
        spinner_plot.stop();
    });
});
