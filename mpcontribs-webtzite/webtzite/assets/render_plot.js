import Plotly from 'plotly';

window.PLOTLYENV=window.PLOTLYENV || {};
window.PLOTLYENV.BASE_URL='https://plot.ly';

window.render_plot = function(props) {
    Plotly.newPlot(props.divid, props.data, props.layout, props.config);
}
