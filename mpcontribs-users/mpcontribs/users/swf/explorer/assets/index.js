import Plotly from 'plotly';
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var api_url = window.api['host'] + 'projects/swf/graph';
var graph = document.getElementById('graph');
var layout = {
    grid: {rows: 1, columns: 2, pattern: 'independent'},
    hovermode: 'closest',
    title: 'In-plane Coercive Field Maps',
    xaxis1: { title: 'Percent V [at%]' },
    yaxis1: { title: 'Film Thickness [nm]' },
    xaxis2: { title: 'Percent V [at%]' },
    showlegend: false
};

var graph_columns = [
    ['V', 'thickness', 'Hc|MOKE'],
    ['V', 'thickness', 'Hc|VSM']
];
var barx = [0.45, 1]

var gets = $.map(graph_columns, function(columns) {
    return $.get({
        url: api_url, data: {'columns': columns.join(',')},
        headers: window.api['headers']
    });
})

$.when.apply($, gets).done(function() {
    var data = [];
    $.each(arguments, function(index, response) {
        var r = response[0];
        data.push({
            name: graph_columns[index][2],
            x: r[0]['y'], // V
            y: r[1]['y'], // thickness
            xaxis: 'x'+(index+1), yaxis: 'y'+(index+1),
            text: r[2]['y'], // Hc|MOKE and Hc|VSM
            mode: 'markers', type: 'scatter', showlegend: false,
            marker: {
                size: 16, colorscale: 'Jet', showscale: true,
                color: r[2]['y'], colorbar: {
                    title: graph_columns[index][2],
                    x: barx[index], xanchor: "left"
                }
            }
        });
    });
    Plotly.plot(graph, data, layout);
    ////graph.on('plotly_click', function(data){
    ////    var pn = data.points[0].pointNumber
    ////    var url = cids[pn]
    ////    window.open(url, '_blank')
    ////});
    spinner_plot.stop();
});





//function makeAxis(title, tickangle) {
//    return {
//        title: title,
//        titlefont: { size: 20 },
//        tickangle: tickangle,
//        tickfont: { size: 15 },
//        tickcolor: 'rgba(0,0,0,0)',
//        ticklen: 5,
//        showline: true,
//        showgrid: true
//    }
//};
//
//var layout = {
//    'ternary': {
//        'sum': 100,
//        'aaxis': makeAxis('Fe', 0),
//        'baxis': makeAxis('<br>Co', 45),
//        'caxis': makeAxis('<br>V', -45),
//    },
//    showlegend: false,
//    updatemenus: [{
//        a: 100,
//        yanchor: 'top',
//        xanchor: 'center',
//        buttons: [{
//            method: 'restlye',
//            args: ['visible', [false, false, false, true]],
//            label: 'All'
//        }, {
//            method: 'restyle',
//            args: ['visible', [true, false, false, false]],
//            label: 'IP Energy Product Data'
//        }, {
//            method: 'restyle',
//            args: ['visible', [false, true, false, false]],
//            label: 'MOKE Coercive Field Data'
//        }, {
//            method: 'restyle',
//            args: ['visible', [false, false, true, false]],
//            label: 'VSM Coercive Field Data'
//        }]
//    }]
//};
//
//var elements = ['Fe', 'Co', 'V'];
//var data_layers = ['BH|max', 'Hc|MOKE', 'Hc|VSM'];

//var avals = new Array(), bvals = new Array(), cvals = new Array(), cids = new Array(),
//    markercolor = new Array(), a_all = new Array(), b_all = new Array(), c_all = new Array(),
//    color_all = new Array(), cids_all = new Array();
//
//for (j = 0; j < data_layers.length; j++) {
//    avals[j] = new Array(); bvals[j] = new Array(); cvals[j] = new Array();
//    cids[j] = new Array(); markercolor[j] = new Array()
//    for (i = 0; i < table['rows'].length; i++) {
//        row = table['rows'][i];
//        if (row[data_layers[j]] != "") {
//            avals[j].push(row[elements[0]])
//            bvals[j].push(row[elements[1]])
//            cvals[j].push(row[elements[2]])
//            cids[j].push(row['contribution'])
//            markercolor[j].push(row[data_layers[j]])
//            a_all.push(row[elements[0]])
//            b_all.push(row[elements[1]])
//            c_all.push(row[elements[2]])
//            color_all.push(j)
//            cids_all.push(row['contribution'])
//        }
//    };
//};
//var IP_Energy_Product_Data = {
//    type: 'scatterternary',
//    mode: 'markers',
//    a: avals[0],
//    b: bvals[0],
//    c: cvals[0],
//    name: 'IP Energy Product',
//    marker: {
//        symbol: 0,
//        color: markercolor[0],
//        showscale: true,
//        colorscale: 'Electric',
//        size: 12,
//        colorbar: {
//            title: 'IP BHmax (kJ/m3)'
//        }
//    },
//};
//
//var MOKE_IP_Hc_Data = {
//    type: 'scatterternary',
//    mode: 'markers',
//    a: avals[1],
//    b: bvals[1],
//    c: cvals[1],
//    name: 'MOKE IP Hc',
//    marker: {
//        symbol: 0,
//        color: markercolor[1],
//        showscale: true,
//        colorscale: 'Jet',
//        size: 12,
//        colorbar: {
//            title: 'IP-MOKE (G)'
//        }
//    },
//};
//
//var VSM_IP_Hc_Data = {
//    type: 'scatterternary',
//    mode: 'markers',
//    a: avals[2],
//    b: bvals[2],
//    c: cvals[2],
//    name: 'VSM IP Hc',
//    marker: {
//        symbol: 0,
//        color: markercolor[2],
//        showscale: true,
//        colorscale: 'Jet',
//        size: 12,
//        colorbar: {
//            title: 'IP-VSM (G)'
//        }
//    },
//};
//
//var All = {
//    type: 'scatterternary',
//    mode: 'markers',
//    a: a_all,
//    b: b_all,
//    c: c_all,
//    name: 'All',
//    marker: {
//        symbol: 0,
//        color: color_all,
//        showscale: false,
//        colorscale: 'Portland',
//        size: 12
//    },
//};
//
//var data = [IP_Energy_Product_Data, MOKE_IP_Hc_Data, VSM_IP_Hc_Data, All]
//
//Plotly.plot('graph1', data, layout)
//
//var update = {
//    visible: false
//}
//
//Plotly.restyle('graph1', update, [0,1,2]);
//
//graph1.on('plotly_click', function(data){
//    var pn = data.points[0].pointNumber
//    var cn = data.points[0].curveNumber
//    if (cn == 0) {
//        var url = cids[0][pn]
//    } else if (cn == 1) {
//        var url = cids[1][pn]
//    } else if (cn == 2) {
//        var url = cids[2][pn]
//    } else if (cn == 3) {
//        var url = cids_all[pn]
//    }
//    window.open(url, '_blank')
//});

