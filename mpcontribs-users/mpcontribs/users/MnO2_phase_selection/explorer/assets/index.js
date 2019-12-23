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
        margin: {l: 10, t: 5, b: 30, r: 0}, barmode: 'group',
        xaxis: {type: 'category', showticklabels: false, ticks: ''},
        legend: {orientation: 'h', x: 0, y: 1}, type: 'category'
    };

    $.get({
        url: api_url, headers: window.api['headers'], data: {
            '_fields': 'identifier,id,data.ΔH.value,data.ΔH|hyd.value',
            'project': 'MnO2_phase_selection',
            '_order_by': 'data__ΔH__value', '_limit': 80
        }
    }).done(function(response) {
        var data = [
            {'x': [], 'y': [], 'text': [], 'name': 'ΔH [eV/mol]', 'type': 'bar'},
            {'x': [], 'y': [], 'text': [], 'name': 'ΔH|hyd [eV/mol]', 'type': 'bar'}
        ]
        $.each(response['data'], function(idx, contrib) {
            data[0]['x'].push(contrib['identifier']);
            data[0]['y'].push(contrib['data']['ΔH']['value']);
            data[0]['text'].push(contrib['id']);
            var hyd = contrib['data']['ΔH|hyd'];
            if (typeof hyd !== 'undefined') {
                data[1]['x'].push(contrib['identifier']);
                data[1]['y'].push(hyd['value']);
                data[1]['text'].push(contrib['id']);
            }
        });
        Plotly.plot(graph, data, layout, {displayModeBar: true, responsive: true});
        spinner_plot.stop();
    });
});
