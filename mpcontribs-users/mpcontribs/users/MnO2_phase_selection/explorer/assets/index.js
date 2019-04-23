import Plotly from 'plotly';

var xvals = []; var yvals = [];
for (var t = 0; t < window.tables.length; t++) {
    var table = window.tables[t];
    for (var i = 0; i < table['rows'].length; i++) {
        var row = table['rows'][i];
        var mpid_split = row['mp-id'].split('/');
        var mpid = mpid_split[mpid_split.length-1];
        xvals.push(mpid);
        var value = parseFloat(row['ΔH [eV/mol]'].split(' ')[0]);
        yvals.push(value);
    }
}
var graph = document.getElementById('graph');
var layout = {
    margin: {l: 40, t: 0, b: 25, r: 0},
    xaxis: {type: 'category', showticklabels: false, ticks: ''},
    yaxis: {title: 'Formation Enthalpy [eV/mol]'}
};
var data = [{x: xvals, y: yvals, type: 'bar'}];
Plotly.plot(graph, data, layout);
