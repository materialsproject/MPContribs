import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner_graph');
var spinner_plot = new Spinner({scale: 0.5});
spinner_plot.spin(target);

var columns = $.map(['Solute', 'D₀ [cm²/s]', 'Q [eV]'], function(col) {
    return {'name': col, 'cell': 'string', 'nesting': [], 'editable': 0};
})

$.each($('div[id^=table_]'), function(idx, element) {
    var cid = element.id.split('_')[1];
    var config = {cid: cid, name: 'D₀_Q', per_page: 5, total_records: 20, ncols: columns.length};
    config['uuids'] = $.map(['filter', 'grid', 'pagination', 'colmanage'], function(prefix) {
        return prefix + '_' + cid;
    });
    render_table({table: {columns: columns}, config: config});
});

$('.backgrid-filter').hide(); // hide search
$('.columnmanager-visibilitycontrol').hide(); // hide column manager

var graph = document.getElementById('graph');
//var ranges = {{ ranges|safe }};
var layout = {
    grid: {rows: 1, columns: 3, xgap: 0.02},
    margin: {l: 60, b: 50, t: 50, r: 5},
    hovermode: 'closest', showlegend: false,
    xaxis: {title: '1000/T [K⁻¹]'},
    yaxis: {title: 'diffusivity', type: 'log', exponentformat: "power"},
    xaxis2: {title: 'Z'},//, range: ranges['Z']},
    yaxis2: {title: 'D₀ [cm²/s]'},//, range: ranges['D₀ [cm²/s]']},
    xaxis3: {title: 'Z'},//, range: ranges['Z']},
    yaxis3: {title: 'Q [eV]'},//, range: ranges['Q [eV]']}
};

// var selection = {};
//var data = {};
//data['graphDif'] = []; data['graphD0'] = []; data['graphQ'] = [];
//panels.each(function(index) {
//    if (selection.length == 2) { return false; } // only show two hosts
//    var host = $('.panel-heading .panel-title a span:nth-child(2)', this).text();
//    if ( host === 'Al' || host === 'Cu' ) {
//        selection[index] = [];
//        var rows = $('.panel-collapse table.backgrid tbody tr', this);
//        data['graphD0'].push({x: [], y: [], name: host, connectgaps: true, mode: 'lines+markers'});
//        data['graphQ'].push({x: [], y: [], name: host, connectgaps: true, mode: 'lines+markers'});
//        var idx = data['graphD0'].length-1
//        for (var i = 0; i < window.tables[index]["rows"].length; i++) {
//            var row = window.tables[index]["rows"][i];
//            var Z = row['Z'];
//            if (Z > 20 && Z < 30) { // only show subset of solutes
//                var D0 = row["D₀ [cm²/s]"];
//                data['graphD0'][idx].x.push(Z);
//                data['graphD0'][idx].y.push(D0);
//                var Q = row["Q [eV]"];
//                data['graphQ'][idx].x.push(Z);
//                data['graphQ'][idx].y.push(Q);
//                var trace = {x: [], y: [], mode: 'lines', name: host+'-'+row['El.']};
//                for (var j=0; j<40; j++) {
//                    trace.x.push(j*0.1);
//                    trace.y.push(D0*Math.exp(-Q/0.08617*j*0.1));
//                }
//                data['graphDif'].push(trace);
//                rows.eq(i).toggleClass('selected');
//                selection[index].push(i);
//            }
//        }
//    }
//});


//// contributions selection (row click)
//var lastChecked = null;
//Backbone.on('cellclicked', function(e) {
//    var row = $(e.currentTarget).parent();
//    row.toggleClass('selected');
//    if ( row.hasClass('selected') ) {
//        var values = row.children('td').map(function() {
//            return this.innerHTML;
//        }).get();
//        //Plotly.addTraces('graphD0', {
//        //    x: xvals, y: yvalsD0, name: formula,
//        //    connectgaps: true, mode: 'lines+markers'
//        //});
//console.log(values);
//} else {
//    console.log('unselect');
//}
////var chbx = row.toggleClass('highlight').find(':checkbox');
////chbx.prop('checked', !chbx.prop('checked')).change();
////if(!lastChecked) { lastChecked = chbx; return; }
////if(e.shiftKey) {
////    var $chkboxes = row.parent().find(':checkbox');
////    var start = $chkboxes.index(chbx);
////    var end = $chkboxes.index(lastChecked);
////    var checked = lastChecked.prop('checked');
////    $chkboxes.slice(Math.min(start,end)+1, Math.max(start,end))
////        .prop('checked', checked).change();
////}
////lastChecked = chbx;
//});

// clear all
//    $("#clear_all").on("click", function() {
//      var tracesD0 = [dummy_trace];
//      var tracesQ = [dummy_trace];
//      var tracesDif = [dummy_trace];
//      var traceDif = { x: xvalsDif, y: yvalsDifNaN };
//      for (var j=0; j<grids.length; j++) {
//        var collection = grids[j].collection;
//        var traceD0 = {
//          x: [], y: [], name: collection.title,
//          connectgaps: true, mode: 'lines+markers'
//        };
//        var traceQ = {
//          x: [], y: [], name: collection.title,
//          connectgaps: true, mode: 'lines+markers'
//        };
//        collection.each(function(model){
//          tracesDif.push(traceDif);
//          traceD0['x'].push(model.get('Z'));
//          traceD0['y'].push(NaN);
//          traceQ['x'].push(model.get('Z'));
//          traceQ['y'].push(NaN);
//        });
//        tracesD0.push(traceD0);
//        tracesQ.push(traceQ);
//      }
//      Plotly.newPlot('graphDif', tracesDif, layoutDif, options);
//      Plotly.newPlot('graphD0', tracesD0, layoutD0, options);
//      Plotly.newPlot('graphQ', tracesQ, layoutQ, options);
//      for (var j=0; j<grids.length; j++) {
//        var selectedModels = grids[j].getSelectedModels();
//        for (var i = 0, l = selectedModels.length; i < l; i++) {
//          var model = selectedModels[i];
//          model.trigger("backgrid:select", model, false);
//        }
//      }
//    })
