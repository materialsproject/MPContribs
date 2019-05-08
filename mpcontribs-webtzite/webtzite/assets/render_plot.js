import Plotly from 'plotly';
import math from 'mathjs';

window.PLOTLYENV=window.PLOTLYENV || {};
window.PLOTLYENV.BASE_URL='https://plot.ly';

window.render_plot = function(props) {
    Plotly.newPlot(props.divid, props.data, props.layout, props.config);
    if (typeof props.tid !== 'undefined') {
        var ajax = $.get({
            url: window.api['host'] + 'tables/' + props.tid + '?mask=data&per_page=200',
            headers: window.api['headers']
        }).done(function(response) {
            var columns = math.transpose(response['data']);
            for (var i = 1; i < columns.length; i++) {
                var update = {x: [columns[0]], y: [columns[i]]};
                Plotly.restyle(props.divid, update, [i-1]);
            }
        });
    }
}
