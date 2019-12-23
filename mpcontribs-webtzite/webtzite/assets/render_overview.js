import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';
import t from 'typy';

Plotly.register([
    require('../../../node_modules/plotly.js/lib/bar')
]);

window.render_overview = function(project) {
    var target = document.getElementById('spinner_graph');
    var spinner_plot = new Spinner({scale: 0.5});
    spinner_plot.spin(target);

    $.get({
        url: window.api['host'] + 'projects/' + project + '/',
        headers: window.api['headers'], data: {'_fields': 'columns'}
    }).done(function(response) {
        var column_groups = {};
        $.each(response['columns'], function(idx, col) {
            if (col.endsWith(']')) {
                var unit = col.split(' ')[1];
                if (typeof column_groups[unit] === 'undefined') {
                    column_groups[unit] = [col];
                } else {
                    column_groups[unit].push(col);
                }
            }
        });

        // TODO replace with layouts from API -> https://plot.ly/javascript/layout-template/
        var units = Object.keys(column_groups);
        var nrows = Math.ceil(units.length / 2);
        var ncols = (units.length > 1) + 1;
        var layout = {
            margin: {l: 30, t: 40, b: 30, r: 0}, barmode: 'group',
            legend: {orientation: 'h', x: 0, y: 1.1},
            grid: {rows: nrows, columns: ncols, pattern: 'independent'}
        };

        var columns = [].concat.apply([], Object.values(column_groups));
        $.each(columns, function(idx, col) {
            var unit = col.split(' ')[1];
            var j = units.indexOf(unit) + 1;
            layout['xaxis'+j] = {type: 'category', showticklabels: false, ticks: ''};
        });

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
                //'_order_by': ['data', columns[0].split(' ')[0].replace('.', '__'), 'value'].join('__'),
                // TODO couple graph update to table pagination, search, and order
            }
        }).done(function(response) {
            $.each(response['data'], function(idx, contrib) {
                $.each(columns, function(idx, col) {
                    var value = t(contrib, fields[idx+2]).safeObject;
                    if (typeof value !== 'undefined') {
                        data[idx]['x'].push(contrib['identifier']);
                        data[idx]['y'].push(value);
                        data[idx]['text'].push(contrib['id']);
                    }
                });
            });
            Plotly.plot('graph', data, layout, {displayModeBar: true, responsive: true});
            spinner_plot.stop();
        });
    });
}
