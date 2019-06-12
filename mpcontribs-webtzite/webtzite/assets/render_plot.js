import Plotly from 'plotly'; // plotly core only
import core from 'mathjs'; // mathjs core only
import {Spinner} from 'spin.js';

window.PLOTLYENV=window.PLOTLYENV || {};
window.PLOTLYENV.BASE_URL='https://plot.ly';
var spinner_plot = new Spinner({scale: 0.5});

const math = core.create();
math.import(require('../../../node_modules/mathjs/lib/type/matrix/index'));
math.import(require('../../../node_modules/mathjs/lib/function/matrix/transpose'));

window.render_plot = function(props) {
    Plotly.newPlot(props.divid, props.data, props.layout, props.config);
    if (typeof props.tid !== 'undefined') {
        var target = document.getElementById('spinner_graph');
        spinner_plot.spin(target);
        var gets = []; var nmax = 5;
        for (var i = 0; i < nmax; i++) { // max 5 request = 5000 table rows
            var page = i+1;
            gets.push($.get({
                url: window.api['host'] + 'tables/' + props.tid + '?per_page=1000&page=' + page,
                headers: window.api['headers']
            }));
        }
        $.when.apply($, gets).done(function() {
            var gets_args = arguments;
            var update = []; // list of traces
            var ntraces = -1;
            $.each(arguments, function(index, response) {
                if ( 'data' in response[0] ) {
                    var columns = math.transpose(response[0]['data']);
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
