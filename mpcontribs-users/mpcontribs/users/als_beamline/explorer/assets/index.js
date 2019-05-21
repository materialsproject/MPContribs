import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var api_url = window.api['host'] + 'projects/als_beamline/graph';
var graph = document.getElementById('graph');

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/scatterternary')
]);

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
    grid: {rows: 2, columns: 2, ygap: 0.3},
    hovermode: 'closest', height: 900,
    showlegend: false,
};

$.each(["", "2", "3", "4"], function(index, istr) {
    layout["ternary"+istr] = {
        sum: 100,
        domain: {row: Math.floor(index/2), column: Math.floor(index%2)},
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
var colorbars = [[0.4, 0.85], [0.95, 0.85], [0.4, 0.25], [0.95, 0.25]];
var mp_ids = ['mp-28', 'mp-30', 'mp-54', 'mp-21708', 'mp-1112', 'mp-2801'];

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
                    xanchor: "left", len: 0.4,
                    x: colorbars[index][0], y: colorbars[index][1]
                }
            }
        });
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
    spinner_plot.stop();
});

//graph1.on('plotly_hover', function(eventdata){
//    var spectra_graphs = document.getElementsByClassName('plotly-graph-div js-plotly-plot')
//    XASgraph  = spectra_graphs[0]
//    XMCDgraph = spectra_graphs[1]
//    var update = {
//        opacity: 0.2,
//    }
//    var hoverdata = eventdata.points[0]
//    var hoverUpdate = {
//        opacity: 1,
//    };
//    cn = hoverdata.curveNumber
//
//    if (cn != 0 && cn != 1) {
//        Plotly.restyle(XASgraph, update);
//        Plotly.restyle(XMCDgraph, update);
//
//        pn = hoverdata.pointNumber
//        Plotly.restyle(XASgraph, hoverUpdate, pn)
//        Plotly.restyle(XMCDgraph, hoverUpdate, pn)
//    };
//
//});
