import Plotly from 'plotly'; // plotly core only
import core from 'mathjs'; // mathjs core only
import {Spinner} from 'spin.js';

const math = core.create();
math.import(require('../../../../../../node_modules/mathjs/lib/type/matrix/index'));
math.import(require('../../../../../../node_modules/mathjs/lib/function/matrix/transpose'));

$(document).ready(function () {
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);

    var tid = '5cca3b57e7004456f9ba72cc';
    var api_url = window.api['host'] + 'tables/' + tid + '?per_page=200';
    var graph = document.getElementById('graph');
    var spinner_plot = new Spinner({scale: 0.5});
    var target = document.getElementById('spinner_graph');
    spinner_plot.spin(target);

    var layout = {
        height: 900, margin: { b: 20, t: 1, l: 1, r: 1 },
        grid: {columns: 1, pattern: 'independent', roworder: 'bottom to top'},
        annotations: []
    }
    var colors = ['#EC3323', '#001DF5', '#E08244', '#70FBFD', '#4CAD5B', '#4BAEEA', '#EB3CF7']
    var annotations = [ // TODO move these into MPFile where they belong
        '<b>5.1±0.8 ps</b>', '<b>2.7±0.6 ps</b>', '<b>1.9±0.5 ps</b>', '<b>1.4±0.4 ps</b>',
        '<b>1.3±0.3 ps</b>', '<b>1.6±0.4 ps</b>', '<b>3.4±0.6 ps</b>'
    ]

    $.get({
        url: api_url, headers: window.api['headers']
    }).done(function(response) {
        var columns = math.transpose(response['data']);
        var data = [];
        layout.grid.rows = columns.length-1;
        for (var i = 1; i < columns.length; i++) {
            data.push({
                x: columns[0], y: columns[i], name: response['columns'][i],
                xaxis: 'x'+i, yaxis: 'y'+i,
                type: 'scatter', mode: 'lines+markers',
                line: { color: colors[i-1], width: 3 },
                marker: {
                    symbol: 'circle', size: 4, color: '#fff',
                    line: { color: '#444', width: 1 }
                }
            });
            layout['xaxis'+i] = {
                showline: true, showgrid: false, zeroline: false,
                mirror: true, ticks: 'inside'
            };
            layout['yaxis'+i] = {
                showline: true, showgrid: false, zeroline: false,
                mirror: true, ticks: 'inside', showticklabels: false
            };
            layout.annotations.push({
                text: annotations[i-1], xref: 'x'+i, x: 17, yref: 'y'+i, y: 1e-6,
                showarrow: false, font: { size: 14, color: colors[i-1] }
            });
        }
        Plotly.plot(graph, data, layout, {displayModeBar: false, responsive: true});
        spinner_plot.stop();
    });
});

