import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/scatterternary')
]);

function makeAxis(title, tickangle) {
    return {
        title: title, titlefont: { size: 20 },
        tickangle: tickangle, tickfont: { size: 15 },
        tickcolor: 'rgba(0,0,0,0)', ticklen: 5,
        showline: true, showgrid: true
    }
};

$(document).ready(function () {
    var graph = document.getElementById('graph_custom');
    var target = document.getElementById('spinner_graph_custom');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);

    var layout = {
        hovermode: 'closest', height: 900,
        title: 'In-plane Coercive Field Maps',
        xaxis1: {
            title: 'Percent V [at%]',
            domain: [0, 0.45], anchor: 'y1'
        },
        yaxis1: {
            title: 'Film Thickness [nm]',
            domain: [0.6, 1], anchor: 'x1'
        },
        xaxis2: {
            title: 'Percent V [at%]',
            domain: [0.55, 1], anchor: 'y2'
        },
        yaxis2: { domain: [0.6, 1], anchor: 'x2' },
        ternary: {
            aaxis: makeAxis('Fe', 0),
            baxis: makeAxis('<br>Co', 45),
            caxis: makeAxis('<br>V', -45),
            sum: 100, domain: {x: [0, 0.25], y: [0, 0.45]}
        },
        ternary2: {
            aaxis: makeAxis('Fe', 0),
            baxis: makeAxis('<br>Co', 45),
            caxis: makeAxis('<br>V', -45),
            sum: 100, domain: {x: [0.375, 0.625], y: [0, 0.45]}
        },
        ternary3: {
            aaxis: makeAxis('Fe', 0),
            baxis: makeAxis('<br>Co', 45),
            caxis: makeAxis('<br>V', -45),
            sum: 100, domain: {x: [0.75, 1], y: [0, 0.45]}
        },
        showlegend: false,
    };

    var graph_columns = [
        ['V', 'thickness', 'Hc|MOKE'],
        ['V', 'thickness', 'Hc|VSM'],
        ['Fe', 'Co', 'V', 'BH|max'],
        ['Fe', 'Co', 'V', 'Hc|MOKE'],
        ['Fe', 'Co', 'V', 'Hc|VSM']
    ];
    var colorbars = [[0.45, 0.8], [1, 0.8], [0.25, 0.3], [0.625, 0.3], [1, 0.3]]

    var fields = ['identifier', 'id'].concat(
        $.map(['Fe', 'Co', 'V', 'thickness', 'Hc|MOKE', 'Hc|VSM', 'BH|max'], function(col) {
            return 'data.' + col + '.value';
        })
    );
    var gets = [
        $.get({
            url: window.api['host'] + 'contributions/', headers: window.api['headers'], data: {
                '_fields': fields.join(','), 'project': project
            }
        })
    ];

    $.when.apply($, gets).done(function() {
        var data = [];
        $.each(arguments, function(index, response) {
            var r = response[0]['data'];
            if (index < 2) {
                data.push({
                    name: graph_columns[index][2],
                    x: r[0]['y'], // V
                    y: r[1]['y'], // thickness
                    xaxis: 'x'+(index+1), yaxis: 'y'+(index+1),
                    text: r[2]['text'], // cid
                    mode: 'markers', type: 'scatter', showlegend: false,
                    marker: {
                        size: 16, colorscale: 'Jet', showscale: true,
                        color: r[2]['y'],  // Hc|MOKE and Hc|VSM
                        colorbar: {
                            title: graph_columns[index][2],
                            xanchor: "left", len: 0.4,
                            x: colorbars[index][0], y: colorbars[index][1]
                        }
                    }
                });
            } else {
                data.push({
                    type: 'scatterternary', mode: 'markers',
                    a: r[0]['y'], b: r[1]['y'], c: r[2]['y'],
                    name: graph_columns[index][3],
                    subplot: 'ternary'+(index-1),
                    text: r[0]['text'], // cid
                    marker: {
                        symbol: 0, showscale: true, colorscale: 'Jet', size: 12,
                        color: r[3]['y'], colorbar: {
                            title: graph_columns[index][3],
                            xanchor: "left", len: 0.35,
                            x: colorbars[index][0], y: colorbars[index][1]
                        }
                    }
                });
            }
        });
        Plotly.plot(graph, data, layout, {displayModeBar: true, responsive: true});
        graph.on('plotly_click', function(d){
            var cid = d.points[0].text;
            var url = '/' + cid;
            window.open(url, '_blank');
        });
        spinner_plot.stop();
    });
});
