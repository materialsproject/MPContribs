import Plotly from 'plotly'; // plotly core only
import core from 'mathjs'; // mathjs core only
import {Spinner} from 'spin.js';

const math = core.create();
math.import(require('../../../../../../node_modules/mathjs/lib/type/matrix/index'));
math.import(require('../../../../../../node_modules/mathjs/lib/function/matrix/transpose'));

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var graph = document.getElementById('graph');
var layout = {
    margin: {l: 70, b: 50, t: 50, r: 5}, hovermode: 'closest',
    yaxis: {type: 'log', title: 'Current density [mA/cm²]', range: [-6, 1]},
    xaxis: {title: 'Voltage [V]'},
};
var api_url = window.api['host'] + 'tables/5d12c8d57be0d62e9aca5d14';
var colors = ['rgb(0,127,0)', 'rgb(60,60,60)', 'rgb(159,201,54)']

$.get({
    url: api_url, data: {'per_page': 50}, headers: window.api['headers']
}).done(function(response) {
    var columns = math.transpose(response['data']);
    var data = [];
    for (var i = 1; i < columns.length; i++) {
        var idx = Math.floor((i-1)/2);
        var dash = ((i-1)%2) ? 'dot' : 'solid';
        data.push({
            x: columns[0], y: columns[i],
            name: response['columns'][i],
            line: {color: colors[idx], dash: dash}
        });
    }
    Plotly.plot(graph, data, layout, {displayModeBar: false, responsive: true});
    spinner_plot.stop();
});
