import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/bar')
]);

$(document).ready(function () {
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);

    var api_url = window.api['host'] + 'contributions/';
    var graph = document.getElementById('graph');
    var layout = {
        margin: {l: 40, t: 0, b: 25, r: 0},
        xaxis: {type: 'category', showticklabels: false, ticks: ''},
        yaxis: {title: 'Formation Enthalpy [eV/mol]'}
    };

    $.get({
        url: api_url, headers: window.api['headers'], data: {
            '_fields': 'identifier,id,data.ΔH.value', 'project': 'MnO2_phase_selection',
            '_order_by': 'data__ΔH__value', '_limit': 80
        }
    }).done(function(response) {
        var data = {'x': [], 'y': [], 'text': [], 'type': 'bar'};
        $.each(response['data'], function(idx, contrib) {
            data['x'].push(contrib['identifier']);
            data['y'].push(contrib['data']['ΔH']['value']);
            data['text'].push(contrib['id']);
        });
        Plotly.plot(graph, [data], layout, {displayModeBar: true, responsive: true});
        spinner_plot.stop();
    });
});
