import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);
var graph = document.getElementById('graph');
var api_url = window.api['host'] + 'projects/perovskites_diffusion/';

var layout = {
    margin: {l: 70, b: 50, t: 50, r: 5}, hovermode: 'closest', showlegend: false,
};

function assignOptions(options, selector, def) {
    var texts = Object.values(options);
    var values = Object.keys(options);
    for (var i = 0; i < texts.length;  i++) {
        var currentOption = document.createElement('option');
        currentOption.text = texts[i];
        currentOption.value = values[i];
        if ( i == def ) { currentOption.selected = true; }
        document.getElementById(selector).appendChild(currentOption);
    }
}

function plot() {
    spinner_plot.spin(target);
    var axes = $.map(['x', 'y'], function(ax) {
        return document.getElementById(ax+'Choose');
    });
    var columns = $.map(axes, function(ax) { return ax.value; });
    var titles = $.map(axes, function(ax) { return ax.options[ax.selectedIndex].text; });
    $.get({
        url: api_url + 'graph', data: {'columns': columns.join(',')},
        headers: window.api['headers']
    }).done(function() {
        var r = arguments[0]['data'];
        var data = [{
            x : r[0]['y'], y : r[1]['y'], text : r[1]['text'],
            marker: {size: 10}, mode: 'markers'
        }];
        for (var t = 0; t < titles.length; t++) {
            var axis = !t ? 'x' : 'y';
            layout[axis+'axis'] = {'title': titles[t]}
        }
        Plotly.newPlot(graph, data, layout, {displayModeBar: true, responsive: true});
        graph.on('plotly_click', function(d){
            var cid = d.points[0].text;
            var url = '/' + cid;
            window.open(url, '_blank');
        });
        spinner_plot.stop();
    });
}

$.get({
    url: api_url, data: {'_fields': 'other.abbreviations'},
    headers: window.api['headers']
}).done(function() {
    var r = arguments[0]['other']['abbreviations'];
    assignOptions(r, 'xChoose', 11);
    assignOptions(r, 'yChoose', 10);
    plot();
});

document.getElementById('xChoose').addEventListener('change', plot, false);
document.getElementById('yChoose').addEventListener('change', plot, false);
