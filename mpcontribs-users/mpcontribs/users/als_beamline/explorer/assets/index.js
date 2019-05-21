import Plotly from 'plotly'; // plotly core only
import core from 'mathjs'; // mathjs core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var api_url = window.api['host'] + 'projects/als_beamline/graph';
var graph = document.getElementById('graph');

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/scatterternary')
]);

const math = core.create();
math.import(require('../../../../../../node_modules/mathjs/lib/type/matrix/index'));
math.import(require('../../../../../../node_modules/mathjs/lib/function/matrix/transpose'));

function makeAxis(title, tickangle) {
    return {
        title: title, titlefont: { size: 20 },
        tickangle: tickangle, tickfont: { size: 15 },
        tickcolor: 'rgba(0,0,0,0)', ticklen: 5,
        showline: true, showgrid: true,
        linewidth: 2, linecolor: 'black'
    }
};

var layout = {
    grid: {rows: 2, columns: 3, ygap: 0, xgap: 0.3, pattern: 'independent'},
    hovermode: 'closest', height: 900,
    showlegend: false, margin: {l: 0, t: 0, b: 0, r: 0},
    xaxis6: {title: 'Energy [eV]'},
};

$.each(["", "2", "3", "4"], function(index, istr) {
    var i = Math.floor(index/2);
    var j = Math.floor(index%2);
    layout["ternary"+istr] = {
        sum: 100, domain: {row: i, column: j},
        aaxis: makeAxis('Co', 0),
        baxis: makeAxis('<br>Cu', 45),
        caxis: makeAxis('<br>Ce', -45),
    };
});

var graph_columns = [
    ['composition.Co', 'composition.Cu', 'composition.Ce', 'XAS.min'],
    ['composition.Co', 'composition.Cu', 'composition.Ce', 'XAS.max'],
    ['composition.Co', 'composition.Cu', 'composition.Ce', 'XMCD.min'],
    ['composition.Co', 'composition.Cu', 'composition.Ce', 'XMCD.max'],
];
var colorbars = [[0.27, 0.82], [0.63, 0.82], [0.27, 0.3], [0.63, 0.3]];
var mp_ids = ['mp-28', 'mp-30', 'mp-54', 'mp-21708', 'mp-1112', 'mp-2801'];
var curveNumbers = [2, 5, 8, 11];

var gets = $.map(graph_columns, function(columns) {
    return $.get({
        url: api_url, data: {'columns': columns.join(',')},
        headers: window.api['headers']
    });
})

gets.push($.get({
    url: window.api['host'] + 'contributions/?projects=als_beamline&mask=content.tables',
    headers: window.api['headers']
}))

$.when.apply($, gets).done(function() {
    var data = [];
    $.each(arguments, function(index, response) {
        var r = response[0];
        if (index < 4) {
            data.push({
                type: 'scatterternary', mode: 'lines',
                a: [100, 0, 66.667, 0],
                b: [0, 83.333, 0, 66.667],
                c: [0, 16.667, 33.333, 33.333],
                name: 'MP Phase Diagram',
                line: {color: 'black'},
                subplot: 'ternary'+(index+1),
                hoverinfo: 'skip'
            });
            data.push({
                type: 'scatterternary', mode: 'markers',
                a: [0, 0, 100, 0, 66.667, 0],
                b: [0, 100, 0, 83.333, 0, 66.667],
                c: [100, 0, 0, 16.667, 33.333, 33.333],
                text: mp_ids, name: 'MP Stable Phases',
                subplot: 'ternary'+(index+1),
                marker: {symbol: 0, size: 14, color: 'grey'}
            });
            data.push({
                type: 'scatterternary', mode: 'markers',
                a: r[0]['y'], b: r[1]['y'], c: r[2]['y'],
                name: graph_columns[index][3],
                subplot: 'ternary'+(index+1),
                text: r[0]['text'], // cid
                marker: {
                    symbol: 0, showscale: true, colorscale: 'Jet', size: 12,
                    color: r[3]['y'], colorbar: {
                        title: graph_columns[index][3],
                        xanchor: "left", len: 0.2,
                        x: colorbars[index][0], y: colorbars[index][1]
                    }
                }
            });
        } else {
            var tgets = $.map(response[0], function(contrib) {
                var tid = contrib.content.tables[0];
                return $.get({
                    url: window.api['host'] + 'tables/' + tid + '?mask=identifier,data&per_page=200',
                    headers: window.api['headers']
                });
            });
            $.when.apply($, tgets).done(function() {
                var traces = [];
                $.each(arguments, function(index, response) {
                    var identifier = response[0]['identifier'];
                    var columns = math.transpose(response[0]['data']);
                    for (var i = 1; i < columns.length; i++) {
                        traces.push({
                            x: columns[0], y: columns[i], name: identifier,
                            xaxis: 'x'+3*i, yaxis: 'y'+3*i
                        });
                    }
                });
                Plotly.addTraces(graph, traces);
                spinner_plot.stop();
            });
        }
    });
    Plotly.plot(graph, data, layout);
    graph.on('plotly_click', function(d){
        var cid_or_mpid = d.points[0].text;
        var url = '/explorer/';
        if (cid_or_mpid.indexOf('mp-') !== -1) {
            url = 'https://materialsproject.org/materials/';
        }
        url += cid_or_mpid;
        window.open(url, '_blank');
    });
    graph.on('plotly_hover', function(eventdata){
        var hoverdata = eventdata.points[0];
        var cn = hoverdata.curveNumber; // data array index
        if (!curveNumbers.includes(cn)) { return; }
        var nr = hoverdata.data.a.length;
        var pn = hoverdata.pointNumber; // = trace index for spectra
        var update = {opacity: 0.2};
        var hoverUpdate = {opacity: 1};
        var start = 12;
        var range = _.range(start, start+2*nr);
        Plotly.restyle(graph, update, range);
        var index = start+2*pn;
        Plotly.restyle(graph, hoverUpdate, [index, index+1]);
    });
});
