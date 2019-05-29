import Plotly from 'plotly'; // plotly core only
import core from 'mathjs'; // mathjs core only
import {Spinner} from 'spin.js';

const math = core.create();
math.import(require('../../../../../../node_modules/mathjs/lib/function/arithmetic/log10.js'));

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var api_url = window.api['host'] + 'projects/carrier_transport/graph';
var graph = document.getElementById('graph');
var layout = {
    grid: {rows: 1, columns: 2, xgap: 0.3, pattern: 'independent'},
    margin: {l: 60, b: 50, t: 20}, showlegend: false,
    xaxis: {title: 'σ [(Ωms)⁻¹]', exponentformat: "power", type: 'log'},
    yaxis: {title: 'S [μV/K]'},
    xaxis2: {type: 'log', title: 'doping level [cm⁻³]', exponentformat: "power"},
    yaxis2: {title: 'temperature [K]'}
}

$.get({
    url: api_url, data: {'columns': '<σ>.p,<S>.p,<S²σ>.p'}, // TODO n-doping
    headers: window.api['headers']
}).done(function(r) {
    var data = [{
        x: r[0]['y'], y: r[1]['y'], text: r[2]['text'],
        mode: 'markers', type: 'scatter', marker: {
            color: math.log10(r[2]['y']), colorscale: 'Viridis',
            colorbar: {title: 'log(<S²σ>)', xanchor: "left", x: 0.45}
        }
    }];
    Plotly.plot(graph, data, layout);
    graph.on('plotly_click', function(data){
        var cid = data.points[0].text;
        var url = '/explorer/' + cid;
        window.open(url, '_blank');
    });
    spinner_plot.stop();
});

// $(".backgrid > tbody > tr:first > td:nth-child(6)").click()
