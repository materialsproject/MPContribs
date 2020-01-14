import 'underscore';
import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';
import t from 'typy';

Plotly.register([
    require('../../../node_modules/plotly.js/lib/bar')
]);

window.render_overview = function(project, grid) {
    var graph = document.getElementById('graph');
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);

    var columns_ranges = $('#graph').data('ranges');
    var column_groups = {};
    $.each(columns_ranges, function(col, ranges) {
        if (col.endsWith(']')) {
            var unit = col.split(' ')[1];
            if (typeof column_groups[unit] === 'undefined') {
                column_groups[unit] = [col];
            } else {
                column_groups[unit].push(col);
            }
        }
    });

    if (t(column_groups).isEmptyObject) { spinner_plot.stop(); return; }
    var columns = [].concat.apply([], Object.values(column_groups));

    // TODO replace with layouts from API -> https://plot.ly/javascript/layout-template/
    var units = Object.keys(column_groups);
    var nrows = Math.ceil(units.length / 2);
    var ncols = (units.length > 1) + 1;
    var layout = {
        margin: {l: 30, t: 60, b: 30, r: 10},
        barmode: 'group',
        legend: {orientation: 'h', x: 0, y: 1.1},
        grid: {rows: nrows, columns: ncols, pattern: 'independent'}
    };

    $.each(columns, function(idx, col) {
        var unit = col.split(' ')[1];
        var j = units.indexOf(unit) + 1;
        layout['xaxis'+j] = {type: 'category', showticklabels: false, ticks: ''};
    });

    var nsteps = 10;
    var ops = [' ≥ ', ' ≤ '];
    layout['sliders'] = [];
    $.each(columns, function(i, column) {
        var range = _.map(columns_ranges[column], Number);
        var interval = (range[1] - range[0]) / nsteps;
        if (interval > 0.) {
            var steps = $.map(_.range(11), function(n) {
                var step = range[0] + n*interval;
                return {label: step.toFixed(2), method: 'skip'}
            });
            $.each(ops, function(j, op) {
                layout['sliders'].push({
                    len: 0.45, steps: steps, pad: {t: 20, b: 20},
                    x: j*0.55, y: -i*0.2, active: j*nsteps, name: column,
                    currentvalue: {prefix: column+op}
                });
            })
        }
    })

    layout['height'] = 375 * nrows + layout['sliders'].length * 75;

    var fields = ['identifier', 'id'].concat(
        $.map(columns, function(col) { return 'data.' + col.split(' ')[0] + '.value'; })
    );
    var data = $.map(columns, function(col) {
        var unit = col.split(' ')[1];
        var j = units.indexOf(unit) + 1;
        return {'x': [], 'y': [], 'xaxis': 'x'+j, 'yaxis': 'y'+j, 'text': [], 'name': col, 'type': 'bar'}
    });

    $.get({
        url: window.api['host'] + 'contributions/', headers: window.api['headers'], data: {
            '_fields': fields.join(','), 'project': project,
        }
    }).done(function(response) {
        $.each(response['data'], function(contrib_idx, contrib) {
            $.each(columns, function(idx, col) {
                var value = t(contrib, fields[idx+2]).safeObject;
                if (typeof value !== 'undefined') {
                    data[idx]['x'].push(contrib['identifier']);
                    data[idx]['y'].push(value);
                    data[idx]['text'].push(contrib['id']);
                }
            });
        });
        Plotly.plot(graph, data, layout, {displayModeBar: true, responsive: true});
        graph.on('plotly_sliderend', function(data) {
            spinner_plot.spin(target);
            // get filters
            var filters = {};
            $.each(layout['sliders'], function(slider_idx, slider) {
                var active = slider['active'];
                var upper = slider_idx%2;
                if ((upper && active !== nsteps) || (!upper && active !== 0)) {
                    var col = slider['name'].split(' ')[0].replace('.', '__');
                    var op = upper ? 'lte' : 'gte';
                    var val = slider['steps'][active]['label'];
                    var filter = ['data', col, 'value', op].join('__');
                    filters[filter] = val;
                }
            });
            // update table
            //'_order_by': ['data', columns[0].split(' ')[0].replace('.', '__'), 'value'].join('__'),
            // TODO couple graph update to table pagination, search, and order
            grid.collection.fetch({data: filters});
            // update graph
            var params = Object.assign({'_fields': fields.join(','), 'project': project}, filters);
            $.get({
                url: window.api['host'] + 'contributions/', headers: window.api['headers'], data: params
            }).done(function(response) {
                $.each(columns, function(idx, col) {
                    var update = {'x': [[]], 'y': [[]], 'text': [[]]};
                    $.each(response['data'], function(contrib_idx, contrib) {
                        var value = t(contrib, fields[idx+2]).safeObject;
                        if (typeof value !== 'undefined') {
                            update['x'][0].push(contrib['identifier']);
                            update['y'][0].push(value);
                            update['text'][0].push(contrib['id']);
                        }
                    });
                    Plotly.restyle(graph, update, idx);
                });
                spinner_plot.stop();
            });
        });
        spinner_plot.stop();
    });
}
