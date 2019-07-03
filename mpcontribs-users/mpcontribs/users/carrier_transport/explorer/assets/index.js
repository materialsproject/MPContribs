import Plotly from 'plotly'; // plotly core only
import core from 'mathjs'; // mathjs core only
import {Spinner} from 'spin.js';

const math = core.create();
math.import(require('../../../../../../node_modules/mathjs/lib/function/arithmetic/log10.js'));

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/heatmap')
]);

var layout = {
    grid: {rows: 1, columns: 3, xgap: 0.3, pattern: 'independent'},
    margin: {l: 60, b: 60, t: 30}, showlegend: false,
    xaxis: {title: 'σ [(Ωms)⁻¹]', exponentformat: "power", type: 'log'},
    yaxis: {title: 'S [μV/K]'},
    xaxis2: {type: 'log', title: 'doping level [cm⁻³]', exponentformat: "power"},
    yaxis2: {title: 'temperature [K]'}
}

$(document).ready(function () {
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);
    var graph = document.getElementById('graph');

    var gets = [
        $.get({
            url: window.api['host'] + 'projects/carrier_transport/graph',
            data: {'columns': '<σ>.p,<S>.p,<S²σ>.p,<σ>.n,<S>.n,<S²σ>.n'},
            headers: window.api['headers']
        }),
        $.get({
            url: window.api['host'] + 'tables/carrier_transport/mp-27502/S(p)',
            headers: window.api['headers']
        })
    ];

    $.when.apply($, gets).done(function() {
        var data = [];
        $.each(arguments, function(index, response) {
            var r = response[0];
            if (index == 0) {
                data.push({
                    name: 'S²σ',
                    x: r[0]['y'].concat(r[3]['y']),
                    y: r[1]['y'].concat(r[4]['y']),
                    text: r[2]['text'].concat(r[5]['text']),
                    mode: 'markers', type: 'scatter', marker: {
                        color: math.log10(r[2]['y'].concat(r[2]['y'])), colorscale: 'Viridis',
                        colorbar: {title: 'log(<S²σ>)', xanchor: "left", x: 0.45}
                    }
                });
            } else {
                // TODO log for <sigma>
                r['name'] = 'mp-27502';
                r['type'] = 'heatmap';
                r['colorbar'] = {'title': 'S(p)'}
                r['xaxis'] = 'x2';
                r['yaxis'] = 'y2';
                data.push(r);
            }
        });
        Plotly.plot(graph, data, layout, {displayModeBar: true, responsive: true});
        graph.on('plotly_click', function(data){
            var cid = data.points[0].text;
            if (typeof cid !== 'undefined') {
                var url = '/explorer/' + cid;
                window.open(url, '_blank');
            }
        });
        spinner_plot.stop();
    });
});
