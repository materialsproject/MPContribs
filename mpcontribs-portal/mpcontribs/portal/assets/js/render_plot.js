import Plotly from 'plotly'; // plotly core only
import {create, createTranspose} from 'mathjs';
import {Spinner} from 'spin.js/spin';

window.PLOTLYENV=window.PLOTLYENV || {};
window.PLOTLYENV.BASE_URL='https://plot.ly';
var spinner_plot = new Spinner({scale: 0.5});

const transpose = create(createTranspose);

window.render_plot = function(props) {
    props.config['responsive'] = true;
    Plotly.newPlot(props.divid, props.data, props.layout, props.config);
    if (typeof props.tid !== 'undefined') {
        var target = document.getElementById('spinner_graph');
        spinner_plot.spin(target);
        var gets = []; var nmax = 1;
        for (var i = 0; i < nmax; i++) { // max `nmax` request = nmax*1000 table rows
            var page = i+1;
            gets.push($.get({
                url: window.api['host'] + 'tables/' + props.tid + '/?_fields=_all&data_per_page=1000&data_page=' + page,
                headers: window.api['headers']
            }));
        }
        $.when.apply($, gets).done(function() {
            var gets_args = (nmax < 2) ? [arguments] : arguments;
            var update = []; // list of traces
            var ntraces = -1;
            $.each(gets_args, function(index, response) {
                if ( 'data' in response[0] ) {
                    var columns = transpose(response[0]['data']);
                    if (ntraces < 0) { ntraces = columns.length; }
                    if ( update.length == 0 ) { // init update
                        for (var i = 1; i < columns.length; i++) {
                            update.push({x: [[]], y: [[]]});
                        }
                    }
                    for (var i = 1; i < columns.length; i++) {
                        Array.prototype.push.apply(update[i-1]['x'][0], columns[0]);
                        Array.prototype.push.apply(update[i-1]['y'][0], columns[i]);
                    }
                }
                if ( index+1 == nmax ) { // update graph on last request
                    for (var i = 1; i < ntraces; i++) {
                        Plotly.restyle(props.divid, update[i-1], [i-1]);
                    }
                }
            });
            spinner_plot.stop();
        });
    }
}
