import 'underscore';
import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/bar')
]);

var columns_ranges = {'C': [0, 4.2], 'ΔE-QP.indirect': [0.1, 16], 'ΔE-QP.direct': [0.1, 16.1]};
var columns = Object.keys(columns_ranges);
var nsteps = 10;
var ops = [' ≥ ', ' ≤ '];

var sliders = [];
$.each(columns, function(i, column) {
    var range = columns_ranges[column];
    var interval = (range[1] - range[0]) / nsteps;
    var steps = $.map(_.range(11), function(n) {
        var step = range[0] + n*interval;
        return {label: step.toFixed(2), method: 'skip'}
    });
    $.each(ops, function(j, op) {
        sliders.push({
            len: 0.45, steps: steps, pad: {t: 20, b: 20},
            x: j*0.55, y: -i*0.2, active: j*nsteps, name: column,
            currentvalue: {prefix: column+op, suffix: ' eV'}
        });
    })
})

var layout = {
    margin: {t: 0, r: 0, l: 40}, barmode: 'stack', height: 900,
    xaxis: {type: 'category', showticklabels: false, ticks: ''},
    yaxis: {title: 'Energy (eV)'}, legend: {x: 0.05, y: 0.95},
    sliders: sliders
};

$(document).ready(function () {
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);
    var api_url = window.api['host'] + 'projects/dtu/graph';
    var graph = document.getElementById('graph');

    $.get({
        url: api_url, data: {'columns': columns.join(',')},
        headers: window.api['headers']
    }).done(function(response) {
        $.each(response['data'], function(idx, trace) {
            trace['type'] = 'bar';
            trace['name'] = columns[idx];
        })
        Plotly.plot(graph, response['data'], layout, {displayModeBar: true, responsive: true});
        graph.on('plotly_click', function(data){
            var cid = data.points[0].text;
            var url = '/' + cid;
            window.open(url, '_blank');
        });
        graph.on('plotly_sliderend', function(data) {
            var target = document.getElementById('spinner_graph');
            spinner_plot.spin(target);
            var filters = [];
            $.each(sliders, function(idx, slider) {
                var active = slider['active'];
                var upper = idx%2;
                if ((upper && active !== nsteps) || (!upper && active !== 0)) {
                    var col = slider['name'];
                    var op = upper ? 'lte' : 'gte';
                    var val = slider['steps'][active]['label'];
                    var filter = col + '__' + op + ':' + val;
                    filters.push(filter);
                }
            });
            $.get({
                url: api_url, data: {'columns': columns.join(','), 'filters': filters.join(',')},
                headers: window.api['headers']
            }).done(function(response) {
                var graph = document.getElementById('graph');
                $.each(response['data'], function(idx, data) {
                    $.each(data, function(axis, array) {
                        Plotly.restyle(graph, axis, [array], idx);
                    })
                })
                // TODO also update table?
                spinner_plot.stop();
            });
        });
        spinner_plot.stop();
    });
});
