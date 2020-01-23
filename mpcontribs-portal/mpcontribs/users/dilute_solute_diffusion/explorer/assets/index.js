import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js/spin';

var layout = {
    grid: {rows: 1, columns: 3, pattern: 'independent'},
    margin: {l: 60, b: 60, t: 30, r: 5}, hovermode: 'closest', showlegend: false,
    xaxis: {title: '1000/T [K⁻¹]'},
    yaxis: {title: 'diffusivity', type: 'log', exponentformat: "power"},
    xaxis2: {title: 'Z'}, yaxis2: {title: 'D₀ [cm²/s]'},
    xaxis3: {title: 'Z'}, yaxis3: {title: 'Q [eV]'}
};

var columns = $.map(['Z', 'Solute', 'D₀ [cm²/s]', 'Q [eV]'], function(col) {
    return {'name': col, 'cell': 'string', 'nesting': [], 'editable': 0};
});

$(document).ready(function () {
    var graph = document.getElementById('graph');
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);

    var data = [];

    var tables = $('div[id^=table_]');
    $.each(tables, function(index, element) {
        var id_split = element.id.split('_');
        var cid = id_split[1]; var host = id_split[2];
        var config = {cid: cid, name: 'D₀_Q', per_page: 5, total_records: 20, ncols: columns.length};
        config['uuids'] = $.map(['filter', 'grid', 'pagination', 'colmanage'], function(prefix) {
            return prefix + '_' + cid;
        });
        var grid = render_table({table: {columns: columns}, config: config});
        if ( host === 'Al' || host === 'Cu' ) {
            grid.collection.on('sync', function() {
                data.push({ // D0
                    x: [], y: [], name: host, xaxis: 'x2', yaxis: 'y2',
                    connectgaps: true, mode: 'lines+markers'
                });
                data.push({ // Q
                    x: [], y: [], name: host, xaxis: 'x3', yaxis: 'y3',
                    connectgaps: true, mode: 'lines+markers'
                });
                var idx = data.length-2;
                this.each(function(model) {
                    var Z = model.get('Z');
                    var solute = model.get('Solute');
                    var D0 = model.get("D₀ [cm²/s]");
                    var Q = model.get("Q [eV]");
                    data[idx].x.push(Z);
                    data[idx].y.push(D0);
                    data[idx+1].x.push(Z);
                    data[idx+1].y.push(Q);
                    var trace = {
                        x: [], y: [], xaxis: 'x1', yaxis: 'y1',
                        mode: 'lines', name: host+'-'+solute
                    };
                    for (var j=0; j<40; j++) {
                        trace.x.push(j*0.1);
                        trace.y.push(D0*Math.exp(-Q/0.08617*j*0.1));
                    }
                    data.push(trace);
                });
                if (data.length == 14) {
                    Plotly.newPlot(graph, data, layout, {displayModeBar: true, responsive: true});
                    $('.backgrid-filter').hide(); // hide search
                    $('.columnmanager-visibilitycontrol').hide(); // hide column manager
                    spinner_plot.stop();
                }
            });
        }
    });

    $("#toggle_panels").on("click", function() {
        $('.col-md-3').toggleClass('hidden');
    });

    $("#clear_all").on("click", function() {
    });
});
