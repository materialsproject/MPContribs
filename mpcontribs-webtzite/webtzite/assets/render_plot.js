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
        $.get({
            url: window.api['host'] + 'tables/' + props.tid + '?mask=data&per_page=200',
            headers: window.api['headers']
        }).done(function(response) {
            var columns = math.transpose(response['data']);
            for (var i = 1; i < columns.length; i++) {
                var update = {x: [columns[0]], y: [columns[i]]};
                Plotly.restyle(props.divid, update, [i-1]);
            }
            spinner_plot.stop();
        });
    }
}
